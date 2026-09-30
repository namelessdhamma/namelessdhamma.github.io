import http from 'node:http';
import crypto from 'node:crypto';

const BRIDGE_KEY=String(process.env.ND_DRIVE_BRIDGE_TOKEN||process.env.ND_VERCEL_BRIDGE_TOKEN||'').trim();
const EXPECTED_TEAM_ID=String(process.env.ND_VERCEL_TEAM_ID||'team_xmefF5bTs0jLPRMCOZOeHKop').trim();
const GOOGLE_SERVICE_EMAIL=String(process.env.ND_GOOGLE_CLIENT_EMAIL||'').trim();
const GOOGLE_SERVICE_KEY_B64=String(process.env.ND_GOOGLE_PRIVATE_KEY_B64||'').trim();
const GOOGLE_OAUTH_CLIENT_ID=String(process.env.ND_DRIVE_USER_OAUTH_CLIENT_ID||process.env.ND_YOUTUBE_CLIENT_ID||'').trim();
const GOOGLE_OAUTH_CLIENT_SECRET=String(process.env.ND_DRIVE_USER_OAUTH_CLIENT_SECRET||process.env.ND_YOUTUBE_CLIENT_SECRET||'').trim();
const GOOGLE_STORE_PARENT=String(process.env.ND_DRIVE_USER_OAUTH_STORE_PARENT||'15CrPbHWMK2LqOYhBM05Hn1cmzOYA8dKC').trim();
const GOOGLE_DRIVE_OAUTH_STORE='.nd-drive-user-oauth.enc.json';
const VERCEL_OAUTH_STORE='.nd-vercel-oauth.enc.json';
const VERCEL_ISSUER='https://vercel.com';
const VERCEL_CLI_CLIENT_ID='cl_HYyOPBNtFMfHhaUn9L4QPfTZz6TP47bp';
const USER_AGENT='nd-vercel-control/1.0';
const VERCEL_MAINT_TOKEN=String(process.env.ND_VERCEL_MAINT_TOKEN||'').trim();
const HTTP_TIMEOUT_MS=Math.min(120000,Math.max(1000,Number(process.env.ND_VERCEL_CONTROL_HTTP_TIMEOUT_MS||30000)));
async function boundedFetch(url,options={},timeoutMs=HTTP_TIMEOUT_MS){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{return await globalThis.fetch(url,{...options,signal:controller.signal});}
  catch(e){if(controller.signal.aborted){const x=new Error('external_http_timeout_'+timeoutMs);x.cause=e;throw x;}throw e;}
  finally{clearTimeout(timer);}
}
let googleServiceCache=null,googleUserCache=null,googleRefreshCache=null;
let vercelCredentialCache=null,vercelRefreshPromise=null,vercelDiscoveryCache=null;

function safeEqual(a,b){const x=Buffer.from(String(a||'')),y=Buffer.from(String(b||''));return x.length===y.length&&x.length>0&&crypto.timingSafeEqual(x,y);}
function send(res,status,obj){const raw=Buffer.from(JSON.stringify(obj));res.writeHead(status,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});res.end(raw);}
async function readBody(req){const a=[];for await(const c of req)a.push(c);return Buffer.concat(a).toString('utf8');}
function b64u(v){return Buffer.from(v).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function escQ(v){return String(v||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");}
function redact(v){let s=String(v?.message||v||'');for(const x of [BRIDGE_KEY,vercelCredentialCache?.access_token,vercelCredentialCache?.refresh_token])if(x)s=s.split(x).join('[REDACTED]');return s.slice(0,1600);}

function googleServiceCredential(){
  let email=GOOGLE_SERVICE_EMAIL,key='';
  if(!email||!GOOGLE_SERVICE_KEY_B64)throw new Error('google_service_account_env_missing');
  const raw=Buffer.from(GOOGLE_SERVICE_KEY_B64,'base64').toString('utf8');
  try{const o=JSON.parse(raw);email=String(o.client_email||email);key=String(o.private_key||'');}catch{key=raw;}
  key=key.replace(/\\n/g,'\n');
  if(!email||!key.includes('BEGIN PRIVATE KEY'))throw new Error('google_service_account_material_invalid');
  return {email,key};
}
async function googleServiceAccessToken(){
  const {email,key}=googleServiceCredential(),now=Math.floor(Date.now()/1000);
  if(googleServiceCache&&googleServiceCache.email===email&&googleServiceCache.exp>now+90)return googleServiceCache.token;
  const h=b64u(JSON.stringify({alg:'RS256',typ:'JWT'}));
  const p=b64u(JSON.stringify({iss:email,scope:'https://www.googleapis.com/auth/drive',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3500}));
  const unsigned=h+'.'+p;
  const assertion=unsigned+'.'+b64u(crypto.sign('RSA-SHA256',Buffer.from(unsigned),key));
  const form=new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion});
  const r=await boundedFetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:form});
  const t=await r.text();if(!r.ok)throw new Error('google_service_token_http_'+r.status+':'+t.slice(0,400));
  const o=JSON.parse(t||'{}');if(!o.access_token)throw new Error('google_service_access_token_missing');
  googleServiceCache={email,token:o.access_token,exp:now+Number(o.expires_in||3500)};return o.access_token;
}
function driveOauthKey(){if(!BRIDGE_KEY)throw new Error('bridge_key_missing');return crypto.createHash('sha256').update('nd-drive-user-oauth-v1\0'+BRIDGE_KEY).digest();}
function decryptDriveRefresh(o){
  if(!o||o.schema!=='nd-drive-user-oauth-secret-v1')throw new Error('drive_oauth_secret_schema_invalid');
  const d=crypto.createDecipheriv('aes-256-gcm',driveOauthKey(),Buffer.from(o.iv,'base64'));d.setAuthTag(Buffer.from(o.tag,'base64'));
  return Buffer.concat([d.update(Buffer.from(o.ciphertext,'base64')),d.final()]).toString('utf8');
}
async function googleServiceJson(url){
  const token=await googleServiceAccessToken();const r=await boundedFetch(url,{headers:{authorization:'Bearer '+token,accept:'application/json'}});const t=await r.text();
  let o={};try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,600)}}if(!r.ok)throw new Error('google_service_http_'+r.status+':'+t.slice(0,700));return o;
}
async function loadGoogleUserRefresh(){
  if(googleRefreshCache)return googleRefreshCache;
  const q=new URLSearchParams({q:"name = '"+escQ(GOOGLE_DRIVE_OAUTH_STORE)+"' and trashed = false",pageSize:'10',spaces:'drive',fields:'files(id,name,parents)'});
  const list=await googleServiceJson('https://www.googleapis.com/drive/v3/files?'+q.toString());const f=(list.files||[])[0];if(!f)throw new Error('drive_user_oauth_secret_not_found');
  const token=await googleServiceAccessToken();const r=await boundedFetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(f.id)+'?alt=media&supportsAllDrives=true',{headers:{authorization:'Bearer '+token}});const t=await r.text();if(!r.ok)throw new Error('drive_oauth_secret_read_http_'+r.status);
  googleRefreshCache=decryptDriveRefresh(JSON.parse(t));return googleRefreshCache;
}
async function googleUserAccessToken(){
  if(!GOOGLE_OAUTH_CLIENT_ID||!GOOGLE_OAUTH_CLIENT_SECRET)throw new Error('google_user_oauth_client_missing');
  const now=Math.floor(Date.now()/1000);if(googleUserCache&&googleUserCache.exp>now+90)return googleUserCache.token;
  const refresh=await loadGoogleUserRefresh();
  const form=new URLSearchParams({client_id:GOOGLE_OAUTH_CLIENT_ID,client_secret:GOOGLE_OAUTH_CLIENT_SECRET,refresh_token:refresh,grant_type:'refresh_token'});
  const r=await boundedFetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:form});const t=await r.text();if(!r.ok)throw new Error('google_user_oauth_refresh_http_'+r.status+':'+t.slice(0,500));
  const o=JSON.parse(t||'{}');if(!o.access_token)throw new Error('google_user_access_token_missing');googleUserCache={token:o.access_token,exp:now+Number(o.expires_in||3500)};return o.access_token;
}
async function googleUserJson(url,{method='GET',body,headers={}}={}){
  const token=await googleUserAccessToken();const h={authorization:'Bearer '+token,accept:'application/json',...headers};let payload=body;
  if(body!==undefined&&!Buffer.isBuffer(body)&&typeof body!=='string'){payload=JSON.stringify(body);h['content-type']='application/json';}
  const r=await boundedFetch(url,{method,headers:h,body:payload});const t=await r.text();let o={};try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,700)}}if(!r.ok){const e=new Error('google_user_http_'+r.status+':'+t.slice(0,900));e.status=r.status;throw e;}return o;
}
function vercelOauthKey(){if(!BRIDGE_KEY)throw new Error('bridge_key_missing');return crypto.createHash('sha256').update('nd-vercel-oauth-v1\0'+BRIDGE_KEY).digest();}
function encryptVercelCredential(credential){
  const iv=crypto.randomBytes(12),cipher=crypto.createCipheriv('aes-256-gcm',vercelOauthKey(),iv);const plaintext=Buffer.from(JSON.stringify(credential),'utf8');const ciphertext=Buffer.concat([cipher.update(plaintext),cipher.final()]);
  return {schema:'nd-vercel-oauth-secret-v1',iv:iv.toString('base64'),tag:cipher.getAuthTag().toString('base64'),ciphertext:ciphertext.toString('base64')};
}
function decryptVercelCredential(o){
  if(!o||o.schema!=='nd-vercel-oauth-secret-v1')throw new Error('vercel_oauth_secret_schema_invalid');const d=crypto.createDecipheriv('aes-256-gcm',vercelOauthKey(),Buffer.from(o.iv,'base64'));d.setAuthTag(Buffer.from(o.tag,'base64'));return JSON.parse(Buffer.concat([d.update(Buffer.from(o.ciphertext,'base64')),d.final()]).toString('utf8'));
}
async function findUserStoreFile(name){
  const q=new URLSearchParams({q:"name = '"+escQ(name)+"' and '"+escQ(GOOGLE_STORE_PARENT)+"' in parents and trashed = false",pageSize:'10',spaces:'drive',fields:'files(id,name,version,parents)'});const o=await googleUserJson('https://www.googleapis.com/drive/v3/files?'+q.toString());return (o.files||[])[0]||null;
}
async function loadVercelCredential({force=false}={}){
  if(vercelCredentialCache&&!force)return vercelCredentialCache;const f=await findUserStoreFile(VERCEL_OAUTH_STORE);if(!f)throw new Error('vercel_oauth_not_authorized');const token=await googleUserAccessToken();const r=await boundedFetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(f.id)+'?alt=media&supportsAllDrives=true',{headers:{authorization:'Bearer '+token}});const t=await r.text();if(!r.ok)throw new Error('vercel_oauth_secret_read_http_'+r.status);vercelCredentialCache=decryptVercelCredential(JSON.parse(t));return vercelCredentialCache;
}
async function persistVercelCredential(credential){
  const normalized={...credential,updated_at:new Date().toISOString()};const blob=Buffer.from(JSON.stringify(encryptVercelCredential(normalized)),'utf8');const token=await googleUserAccessToken();let f=await findUserStoreFile(VERCEL_OAUTH_STORE);
  if(f){const r=await boundedFetch('https://www.googleapis.com/upload/drive/v3/files/'+encodeURIComponent(f.id)+'?uploadType=media&supportsAllDrives=true',{method:'PATCH',headers:{authorization:'Bearer '+token,'content-type':'application/json'},body:blob});const t=await r.text();if(!r.ok)throw new Error('vercel_oauth_secret_update_http_'+r.status+':'+t.slice(0,500));}
  else{
    const boundary='ndvercel-'+crypto.randomBytes(12).toString('hex'),meta={name:VERCEL_OAUTH_STORE,parents:[GOOGLE_STORE_PARENT]};const body=Buffer.concat([Buffer.from('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+JSON.stringify(meta)+'\r\n--'+boundary+'\r\nContent-Type: application/json\r\n\r\n'),blob,Buffer.from('\r\n--'+boundary+'--\r\n')]);
    const r=await boundedFetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id',{method:'POST',headers:{authorization:'Bearer '+token,'content-type':'multipart/related; boundary='+boundary},body});const t=await r.text();if(!r.ok)throw new Error('vercel_oauth_secret_create_http_'+r.status+':'+t.slice(0,500));
  }
  vercelCredentialCache=normalized;return normalized;
}
async function vercelDiscovery(){
  if(vercelDiscoveryCache)return vercelDiscoveryCache;const r=await boundedFetch(VERCEL_ISSUER+'/.well-known/openid-configuration',{headers:{accept:'application/json','user-agent':USER_AGENT}});const t=await r.text();if(!r.ok)throw new Error('vercel_discovery_http_'+r.status);const o=JSON.parse(t||'{}');for(const k of ['device_authorization_endpoint','token_endpoint','introspection_endpoint'])if(!o[k])throw new Error('vercel_discovery_missing_'+k);vercelDiscoveryCache=o;return o;
}
async function vercelDeviceAuthStart(){
  const d=await vercelDiscovery();const form=new URLSearchParams({client_id:VERCEL_CLI_CLIENT_ID,scope:'openid offline_access'});const r=await boundedFetch(d.device_authorization_endpoint,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded','user-agent':USER_AGENT},body:form});const t=await r.text();if(!r.ok)throw new Error('vercel_device_auth_http_'+r.status+':'+t.slice(0,600));const o=JSON.parse(t||'{}');for(const k of ['device_code','user_code','verification_uri','verification_uri_complete','expires_in','interval'])if(o[k]===undefined)throw new Error('vercel_device_auth_missing_'+k);return {status:'ACTION_REQUIRED',device_code:o.device_code,user_code:o.user_code,verification_uri:o.verification_uri,verification_uri_complete:o.verification_uri_complete,expires_in:o.expires_in,interval:o.interval,expires_at:new Date(Date.now()+Number(o.expires_in)*1000).toISOString()};
}
async function vercelTeamsWithToken(token){
  const u=new URL('https://api.vercel.com/v2/teams');u.searchParams.set('limit','100');const r=await boundedFetch(u,{headers:{authorization:'Bearer '+token,accept:'application/json','user-agent':USER_AGENT}});const t=await r.text();if(!r.ok)throw new Error('vercel_team_verify_http_'+r.status+':'+t.slice(0,700));return JSON.parse(t||'{}');
}
function teamArray(o){if(Array.isArray(o))return o;if(Array.isArray(o?.teams))return o.teams;if(Array.isArray(o?.result?.teams))return o.result.teams;return [];}
async function requireExpectedTeam(token){const o=await vercelTeamsWithToken(token);const teams=teamArray(o);if(EXPECTED_TEAM_ID&&!teams.some(x=>String(x.id||x.uid||'')===EXPECTED_TEAM_ID))throw new Error('vercel_expected_team_not_authorized');return teams;}
async function vercelDeviceAuthPoll(deviceCode){
  const d=await vercelDiscovery();const form=new URLSearchParams({client_id:VERCEL_CLI_CLIENT_ID,grant_type:'urn:ietf:params:oauth:grant-type:device_code',device_code:String(deviceCode||'')});const r=await boundedFetch(d.token_endpoint,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded','user-agent':USER_AGENT},body:form});const t=await r.text();let o={};try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,500)}}
  if(!r.ok){if(o.error==='authorization_pending'||o.error==='slow_down')return {status:'PENDING',error:o.error,retry_after_seconds:o.error==='slow_down'?10:5};if(o.error==='access_denied'||o.error==='expired_token')return {status:'FAILED',error:o.error};throw new Error('vercel_device_token_http_'+r.status+':'+t.slice(0,700));}
  if(!o.access_token)throw new Error('vercel_access_token_missing');await requireExpectedTeam(o.access_token);const cred={access_token:o.access_token,refresh_token:o.refresh_token||null,expires_at:Date.now()+Number(o.expires_in||28800)*1000,scope:o.scope||'openid offline_access',token_type:o.token_type||'Bearer'};await persistVercelCredential(cred);return {status:'AUTHORIZED',team_id:EXPECTED_TEAM_ID,refresh_token_persisted:!!cred.refresh_token,expires_at:new Date(cred.expires_at).toISOString()};
}
async function vercelRefreshCredential(oldCred){
  if(!oldCred?.refresh_token)throw new Error('vercel_refresh_token_missing');const d=await vercelDiscovery();const form=new URLSearchParams({client_id:VERCEL_CLI_CLIENT_ID,grant_type:'refresh_token',refresh_token:oldCred.refresh_token});const r=await boundedFetch(d.token_endpoint,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded','user-agent':USER_AGENT},body:form});const t=await r.text();let o={};try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,500)}}if(!r.ok){const e=new Error('vercel_refresh_http_'+r.status+':'+t.slice(0,700));e.oauth_error=o.error||null;throw e;}if(!o.access_token)throw new Error('vercel_refresh_access_token_missing');const next={access_token:o.access_token,refresh_token:o.refresh_token||oldCred.refresh_token,expires_at:Date.now()+Number(o.expires_in||28800)*1000,scope:o.scope||oldCred.scope||'openid offline_access',token_type:o.token_type||'Bearer'};await persistVercelCredential(next);return next;
}
async function vercelAccessToken(){
  let cred=await loadVercelCredential();if(cred?.access_token&&Number(cred.expires_at||0)>Date.now()+120000)return cred.access_token;
  if(!vercelRefreshPromise)vercelRefreshPromise=(async()=>{let snapshot=await loadVercelCredential({force:true});if(snapshot?.access_token&&Number(snapshot.expires_at||0)>Date.now()+120000)return snapshot;try{return await vercelRefreshCredential(snapshot);}catch(e){if(e.oauth_error==='invalid_grant'){const newer=await loadVercelCredential({force:true});if(newer?.refresh_token&&newer.refresh_token!==snapshot.refresh_token)return vercelRefreshCredential(newer);}throw e;}})().finally(()=>{vercelRefreshPromise=null;});
  cred=await vercelRefreshPromise;return cred.access_token;
}
function normalizeQuery(query={}){const q=new URLSearchParams();for(const [k,v] of Object.entries(query||{})){if(v===undefined||v===null||v==='')continue;if(Array.isArray(v))for(const x of v)q.append(k,String(x));else q.set(k,String(v));}return q;}
function validateApiPath(path){const p=String(path||'').trim();if(!/^\/v\d+\//.test(p)&&!/^\/v\d+$/.test(p))throw new Error('vercel_api_path_must_be_versioned');if(p.includes('://')||p.includes('..'))throw new Error('invalid_vercel_api_path');return p;}
async function vercelRequest(path,{method='GET',query={},body,accessToken}={}){
  const p=validateApiPath(path),token=accessToken||await vercelAccessToken(),u=new URL('https://api.vercel.com'+p),q=normalizeQuery(query);for(const [k,v] of q.entries())u.searchParams.append(k,v);const h={authorization:'Bearer '+token,accept:'application/json','user-agent':USER_AGENT};let payload=body;if(body!==undefined&&!Buffer.isBuffer(body)&&typeof body!=='string'){payload=JSON.stringify(body);h['content-type']='application/json';}
  const r=await boundedFetch(u,{method,headers:h,body:payload});const t=await r.text();let o={};try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,12000)}}if(!r.ok){const e=new Error('vercel_api_http_'+r.status+':'+t.slice(0,1400));e.status=r.status;throw e;}return o;
}
async function status(){try{const projects=await vercelRequest('/v9/projects',{query:{teamId:EXPECTED_TEAM_ID,limit:1}});return {ok:true,authorized:true,team_id:EXPECTED_TEAM_ID,projects_visible:Array.isArray(projects?.projects)?projects.projects.length:null,credential_store:'encrypted_google_drive',runtime_route:'direct_vercel_rest',runtime_profile:'BOUNDED_SYNC',request_timeout_ms:HTTP_TIMEOUT_MS,ambiguous_write:'READBACK_BEFORE_RETRY'};}catch(e){if(String(e.message||e).includes('vercel_oauth_not_authorized'))return {ok:true,authorized:false,team_id:EXPECTED_TEAM_ID,credential_store:'encrypted_google_drive',next:'vercel_auth_start'};throw e;}}

async function invoke(name,a={}){
  if(name==='vercel_auth_start')return vercelDeviceAuthStart();
  if(name==='vercel_auth_poll')return vercelDeviceAuthPoll(String(a.device_code||''));
  if(name==='vercel_status')return status();
  if(name==='vercel_list_teams')return vercelRequest('/v2/teams',{query:{limit:a.limit||100}});
  if(name==='vercel_list_projects')return vercelRequest('/v9/projects',{query:{teamId:a.team_id||EXPECTED_TEAM_ID,limit:a.limit||50,until:a.until}});
  if(name==='vercel_get_project')return vercelRequest('/v9/projects/'+encodeURIComponent(String(a.project_id_or_name||'')),{query:{teamId:a.team_id||EXPECTED_TEAM_ID}});
  if(name==='vercel_update_project')return vercelRequest('/v9/projects/'+encodeURIComponent(String(a.project_id_or_name||'')),{method:'PATCH',query:{teamId:a.team_id||EXPECTED_TEAM_ID},body:a.changes||{}});
  if(name==='vercel_list_deployments')return vercelRequest('/v6/deployments',{query:{teamId:a.team_id||EXPECTED_TEAM_ID,projectId:a.project_id,limit:a.limit||20,target:a.target,state:a.state,branch:a.branch,sha:a.sha,until:a.until,since:a.since}});
  if(name==='vercel_get_deployment')return vercelRequest('/v13/deployments/'+encodeURIComponent(String(a.id_or_url||'')),{query:{teamId:a.team_id||EXPECTED_TEAM_ID}});
  if(name==='vercel_create_deployment')return vercelRequest('/v13/deployments',{method:'POST',query:{teamId:a.team_id||EXPECTED_TEAM_ID,forceNew:a.force_new===true?'1':undefined},body:a.deployment||{}});
  if(name==='vercel_redeploy')return vercelRequest('/v13/deployments',{method:'POST',query:{teamId:a.team_id||EXPECTED_TEAM_ID},body:{name:String(a.project_name||''),project:String(a.project_id_or_name||a.project_name||''),deploymentId:String(a.deployment_id||''),target:a.target||'production'}});
  if(name==='vercel_rollback')return vercelRequest('/v1/projects/'+encodeURIComponent(String(a.project_id||''))+'/rollback/'+encodeURIComponent(String(a.deployment_id||'')),{method:'POST',query:{teamId:a.team_id||EXPECTED_TEAM_ID},body:{}});
  if(name==='vercel_build_logs')return vercelRequest('/v3/deployments/'+encodeURIComponent(String(a.id_or_url||''))+'/events',{query:{teamId:a.team_id||EXPECTED_TEAM_ID,direction:a.direction||'backward',limit:a.limit||100,follow:0,builds:1}});
  if(name==='vercel_request')return vercelRequest(String(a.path||''),{method:String(a.method||'GET').toUpperCase(),query:{...(a.query||{}),...(a.include_team===false?{}:{teamId:(a.query||{}).teamId||a.team_id||EXPECTED_TEAM_ID})},body:a.body});
  throw new Error('tool_not_allowed');
}
const TOOLS=[
 {name:'vercel_status',description:'Check ND Vercel authorization and direct REST control health.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
 {name:'vercel_auth_start',description:'Start Vercel CLI-compatible OAuth device authorization. Returns a one-time verification URL/code; no browser agent is used.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
 {name:'vercel_auth_poll',description:'Poll one Vercel device authorization. On success, verify ND team membership and persist the rotated credential encrypted in Google Drive.',inputSchema:{type:'object',properties:{device_code:{type:'string'}},required:['device_code'],additionalProperties:false}},
 {name:'vercel_list_teams',description:'List Vercel teams visible to the ND-authorized account.',inputSchema:{type:'object',properties:{limit:{type:'integer',minimum:1,maximum:100}},additionalProperties:false}},
 {name:'vercel_list_projects',description:'List projects through direct Vercel REST.',inputSchema:{type:'object',properties:{team_id:{type:'string'},limit:{type:'integer',minimum:1,maximum:100},until:{type:['string','number']}},additionalProperties:false}},
 {name:'vercel_get_project',description:'Read one Vercel project by ID or name.',inputSchema:{type:'object',properties:{project_id_or_name:{type:'string'},team_id:{type:'string'}},required:['project_id_or_name'],additionalProperties:false}},
 {name:'vercel_update_project',description:'Patch a Vercel project using direct REST. Use provider readback after consequential changes.',inputSchema:{type:'object',properties:{project_id_or_name:{type:'string'},team_id:{type:'string'},changes:{type:'object'}},required:['project_id_or_name','changes'],additionalProperties:false}},
 {name:'vercel_list_deployments',description:'List Vercel deployments with common filters.',inputSchema:{type:'object',properties:{team_id:{type:'string'},project_id:{type:'string'},limit:{type:'integer',minimum:1,maximum:100},target:{type:'string'},state:{type:'string'},branch:{type:'string'},sha:{type:'string'},until:{type:['string','number']},since:{type:['string','number']}},additionalProperties:false}},
 {name:'vercel_get_deployment',description:'Read one Vercel deployment by ID or URL.',inputSchema:{type:'object',properties:{id_or_url:{type:'string'},team_id:{type:'string'}},required:['id_or_url'],additionalProperties:false}},
 {name:'vercel_create_deployment',description:'Create a Vercel deployment from a provider-supported deployment request body (Git source or files).',inputSchema:{type:'object',properties:{team_id:{type:'string'},force_new:{type:'boolean'},deployment:{type:'object'}},required:['deployment'],additionalProperties:false}},
 {name:'vercel_redeploy',description:'Redeploy an existing deployment by deployment ID.',inputSchema:{type:'object',properties:{team_id:{type:'string'},project_name:{type:'string'},project_id_or_name:{type:'string'},deployment_id:{type:'string'},target:{type:'string'}},required:['project_name','deployment_id'],additionalProperties:false}},
 {name:'vercel_rollback',description:'Point production traffic to a previous deployment.',inputSchema:{type:'object',properties:{team_id:{type:'string'},project_id:{type:'string'},deployment_id:{type:'string'}},required:['project_id','deployment_id'],additionalProperties:false}},
 {name:'vercel_build_logs',description:'Read bounded Vercel deployment build events/logs.',inputSchema:{type:'object',properties:{team_id:{type:'string'},id_or_url:{type:'string'},direction:{type:'string',enum:['forward','backward']},limit:{type:'integer',minimum:1,maximum:1000}},required:['id_or_url'],additionalProperties:false}},
 {name:'vercel_request',description:'Bounded Vercel REST escape hatch for versioned api.vercel.com paths. Supports GET/POST/PATCH/PUT/DELETE and never accepts an external host. Ambiguous writes require provider readback before retry.',inputSchema:{type:'object',properties:{method:{type:'string',enum:['GET','POST','PATCH','PUT','DELETE']},path:{type:'string'},team_id:{type:'string'},include_team:{type:'boolean'},query:{type:'object'},body:{type:['object','array','string','null']}},required:['method','path'],additionalProperties:false}}
];
function rpcResult(id,result){return {jsonrpc:'2.0',id,result};}
function rpcError(id,code,message){return {jsonrpc:'2.0',id,error:{code,message}};}
async function mcpMessage(msg){
  const id=msg?.id??null,method=String(msg?.method||'');
  if(method==='initialize')return rpcResult(id,{protocolVersion:String(msg?.params?.protocolVersion||'2025-06-18'),capabilities:{tools:{listChanged:false}},serverInfo:{name:'ND Vercel Control',version:'1.0.0'},instructions:'Direct non-browser Vercel REST control with bounded provider I/O. Official Vercel connector failure does not imply capability failure. Consequential writes must be read back before cross-route retry.'});
  if(method==='ping')return rpcResult(id,{});
  if(method==='tools/list')return rpcResult(id,{tools:TOOLS});
  if(method==='tools/call'){
    const name=String(msg?.params?.name||'');if(!TOOLS.some(t=>t.name===name))return rpcResult(id,{content:[{type:'text',text:'tool_denied'}],structuredContent:{ok:false,error:'tool_denied'},isError:true});
    try{const result=await invoke(name,msg?.params?.arguments||{});return rpcResult(id,{content:[{type:'text',text:JSON.stringify(result)}],structuredContent:result,isError:false});}
    catch(e){const m=redact(e);return rpcResult(id,{content:[{type:'text',text:m}],structuredContent:{ok:false,error:m},isError:true});}
  }
  if(method.startsWith('notifications/'))return null;return rpcError(id,-32601,'Method not found');
}
export function createVercelControlHandler(){
  return async function handle(req,res){
    const u=new URL(req.url||'/','http://127.0.0.1');
    if(u.pathname==='/vercel/mcp'){
      if(!safeEqual(req.headers['x-nd-bridge-key'],BRIDGE_KEY))return send(res,401,{ok:false,error:'unauthorized'});
      if(req.method==='GET'){res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});res.write(': nd-vercel\n\n');return res.end();}
      if(req.method!=='POST')return send(res,405,{ok:false,error:'method_not_allowed'});let msg={};try{msg=JSON.parse(await readBody(req)||'{}');}catch{return send(res,400,rpcError(null,-32700,'Parse error'));}const out=await mcpMessage(msg);if(out===null){res.writeHead(202,{'cache-control':'no-store'});return res.end();}return send(res,200,out);
    }
    if(u.pathname==='/vercel/health'&&req.method==='GET'){try{return send(res,200,{...(await status()),service:'ND Vercel Control',tools:TOOLS.length,transport:'streamable-http'});}catch(e){return send(res,503,{ok:false,service:'ND Vercel Control',tools:TOOLS.length,error:redact(e)});}}
    if(u.pathname==='/vercel/auth/start'&&req.method==='GET'){try{return send(res,200,await vercelDeviceAuthStart());}catch(e){return send(res,503,{ok:false,error:redact(e)});}}
    if(u.pathname==='/vercel/auth/poll'&&req.method==='GET'){try{return send(res,200,await vercelDeviceAuthPoll(u.searchParams.get('device_code')||''));}catch(e){return send(res,502,{ok:false,error:redact(e)});}}
    if(u.pathname==='/vercel/maintenance/ltx-rebuild-1295bd3'&&req.method==='POST'){
      try{
        const sha='1295bd37325fe27a906ae5c632548d90db26083a';
        const deployed=await vercelRequest('/v13/deployments',{
          method:'POST',
          query:{teamId:EXPECTED_TEAM_ID},
          body:{
            name:'nd-kaggle-ltx-reserve',
            project:'prj_feTEx5M6ws9uphCQVmrRPhYmLKFq',
            target:'production',
            gitSource:{type:'github',org:'namelessdhamma',repo:'namelessdhamma.github.io',ref:'main',sha}
          }
        });
        return send(res,200,{ok:true,id:deployed?.id||null,url:deployed?.url||null,readyState:deployed?.readyState||deployed?.status||null,sha});
      }catch(e){return send(res,502,{ok:false,error:redact(e)});}
    }
    if(u.pathname==='/vercel/maintenance/deploy-ltx'&&req.method==='POST'){
      if(!VERCEL_MAINT_TOKEN||!safeEqual(req.headers['x-nd-maint-key'],VERCEL_MAINT_TOKEN))return send(res,404,{ok:false,error:'not_found'});
      try{
        const body=JSON.parse(await readBody(req)||'{}');
        const sha=String(body.sha||'').trim();
        const expected='1295bd37325fe27a906ae5c632548d90db26083a';
        if(sha!==expected)return send(res,409,{ok:false,error:'unexpected_sha'});
        const deployed=await vercelRequest('/v13/deployments',{
          method:'POST',
          query:{teamId:EXPECTED_TEAM_ID},
          body:{
            name:'nd-kaggle-ltx-reserve',
            project:'prj_feTEx5M6ws9uphCQVmrRPhYmLKFq',
            target:'production',
            gitSource:{type:'github',org:'namelessdhamma',repo:'namelessdhamma.github.io',ref:'main',sha}
          }
        });
        return send(res,200,{ok:true,id:deployed?.id||null,url:deployed?.url||null,readyState:deployed?.readyState||deployed?.status||null,sha});
      }catch(e){return send(res,502,{ok:false,error:redact(e)});}
    }
    if(u.pathname.startsWith('/vercel/'))return send(res,404,{ok:false,error:'not_found'});
    return false;
  };
}
export function startVercelControlServer(){const port=Number(process.env.PORT||3313),handler=createVercelControlHandler();const server=http.createServer(async(req,res)=>{try{const handled=await handler(req,res);if(handled===false)send(res,404,{ok:false,error:'not_found'});}catch(e){send(res,503,{ok:false,error:redact(e)});}});server.listen(port,'0.0.0.0',()=>console.log('ND_VERCEL_CONTROL_READY '+JSON.stringify({port,team_id:EXPECTED_TEAM_ID,tools:TOOLS.length,credential_store:'encrypted_google_drive'})));return server;}
if(String(process.env.ND_VERCEL_STANDALONE||'').toLowerCase()==='true')startVercelControlServer();
