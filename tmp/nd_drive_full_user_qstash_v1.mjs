import http from 'node:http';
import crypto from 'node:crypto';

const PORT=Number(process.env.PORT||3002);
const BRIDGE_KEY=String(process.env.ND_DRIVE_BRIDGE_TOKEN||'').trim();
const SERVICE_EMAIL=String(process.env.ND_GOOGLE_CLIENT_EMAIL||'').trim();
const SERVICE_KEY_B64=String(process.env.ND_GOOGLE_PRIVATE_KEY_B64||'').trim();
const OAUTH_CLIENT_ID=String(process.env.ND_YOUTUBE_CLIENT_ID||'').trim();
const OAUTH_CLIENT_SECRET=String(process.env.ND_YOUTUBE_CLIENT_SECRET||'').trim();
const STORE_NAME='.nd-drive-user-oauth.enc.json';
const STORE_PARENT='15CrPbHWMK2LqOYhBM05Hn1cmzOYA8dKC';
const SERVICE_SCOPES='https://www.googleapis.com/auth/drive';
let serviceCache=null,userCache=null,refreshCache=null;

function b64u(v){return Buffer.from(v).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function safeEqual(a,b){
  const x=Buffer.from(String(a||'')),y=Buffer.from(String(b||''));
  return x.length===y.length && x.length>0 && crypto.timingSafeEqual(x,y);
}
function serviceCredential(){
  let email=SERVICE_EMAIL,key='';
  if(!email||!SERVICE_KEY_B64) throw new Error('service_account_env_missing');
  const raw=Buffer.from(SERVICE_KEY_B64,'base64').toString('utf8');
  try{const o=JSON.parse(raw);email=String(o.client_email||email);key=String(o.private_key||'');}catch{key=raw;}
  key=key.replace(/\\n/g,'\n');
  if(!email||!key.includes('BEGIN PRIVATE KEY')) throw new Error('service_account_material_invalid');
  return {email,key};
}
async function serviceAccessToken(){
  const {email,key}=serviceCredential(),now=Math.floor(Date.now()/1000);
  if(serviceCache&&serviceCache.email===email&&serviceCache.exp>now+90)return serviceCache.token;
  const h=b64u(JSON.stringify({alg:'RS256',typ:'JWT'}));
  const p=b64u(JSON.stringify({iss:email,scope:SERVICE_SCOPES,aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3500}));
  const unsigned=h+'.'+p;
  const assertion=unsigned+'.'+b64u(crypto.sign('RSA-SHA256',Buffer.from(unsigned),key));
  const form=new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion});
  const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:form});
  const t=await r.text(); if(!r.ok)throw new Error('service_token_http_'+r.status+':'+t.slice(0,300));
  const o=JSON.parse(t||'{}'); if(!o.access_token)throw new Error('service_access_token_missing');
  serviceCache={email,token:o.access_token,exp:now+Number(o.expires_in||3500)}; return o.access_token;
}
function oauthKey(){
  if(!BRIDGE_KEY)throw new Error('oauth_encryption_key_missing');
  return crypto.createHash('sha256').update('nd-drive-user-oauth-v1\0'+BRIDGE_KEY).digest();
}
function decryptRefresh(o){
  if(!o||o.schema!=='nd-drive-user-oauth-secret-v1')throw new Error('oauth_secret_schema_invalid');
  const d=crypto.createDecipheriv('aes-256-gcm',oauthKey(),Buffer.from(o.iv,'base64'));
  d.setAuthTag(Buffer.from(o.tag,'base64'));
  return Buffer.concat([d.update(Buffer.from(o.ciphertext,'base64')),d.final()]).toString('utf8');
}
async function serviceJson(url,opts={}){
  const token=await serviceAccessToken(),headers={authorization:'Bearer '+token,accept:'application/json',...(opts.headers||{})};
  let body=opts.body;
  if(body!==undefined&&!Buffer.isBuffer(body)&&typeof body!=='string'){body=JSON.stringify(body);headers['content-type']='application/json';}
  const r=await fetch(url,{method:opts.method||'GET',headers,body}); const t=await r.text();
  let o={};try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,600)}}
  if(!r.ok){const e=new Error('google_http_'+r.status+':'+t.slice(0,800));e.status=r.status;throw e;} return o;
}
async function loadRefresh(){
  if(refreshCache)return refreshCache;
  const q=new URLSearchParams({q:"name = '"+STORE_NAME+"' and trashed = false",pageSize:'10',spaces:'drive',fields:'files(id,name,parents)'});
  const list=await serviceJson('https://www.googleapis.com/drive/v3/files?'+q.toString());
  const f=(list.files||[])[0]; if(!f)throw new Error('drive_user_oauth_secret_not_found');
  const token=await serviceAccessToken();
  const r=await fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(f.id)+'?alt=media&supportsAllDrives=true',{headers:{authorization:'Bearer '+token}});
  const t=await r.text(); if(!r.ok)throw new Error('oauth_secret_read_http_'+r.status);
  refreshCache=decryptRefresh(JSON.parse(t)); return refreshCache;
}
async function userAccessToken(){
  if(!OAUTH_CLIENT_ID||!OAUTH_CLIENT_SECRET)throw new Error('oauth_client_missing');
  const now=Math.floor(Date.now()/1000); if(userCache&&userCache.exp>now+90)return userCache.token;
  const refresh=await loadRefresh();
  const form=new URLSearchParams({client_id:OAUTH_CLIENT_ID,client_secret:OAUTH_CLIENT_SECRET,refresh_token:refresh,grant_type:'refresh_token'});
  const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:form});
  const t=await r.text(); if(!r.ok)throw new Error('oauth_refresh_http_'+r.status+':'+t.slice(0,500));
  const o=JSON.parse(t||'{}'); if(!o.access_token)throw new Error('oauth_access_token_missing');
  userCache={token:o.access_token,exp:now+Number(o.expires_in||3500)}; return o.access_token;
}
async function gjson(url,{method='GET',body,headers={}}={}){
  const token=await userAccessToken(),h={authorization:'Bearer '+token,accept:'application/json',...headers};let payload=body;
  if(body!==undefined&&!Buffer.isBuffer(body)&&typeof body!=='string'){payload=JSON.stringify(body);h['content-type']='application/json';}
  const r=await fetch(url,{method,headers:h,body:payload});const t=await r.text();let o={};
  try{o=t?JSON.parse(t):{};}catch{o={raw:t.slice(0,1000)}}
  if(!r.ok){const e=new Error('google HTTP '+r.status+': '+t.slice(0,1000));e.status=r.status;throw e;}return o;
}
async function gbytes(url,{method='GET',body,headers={}}={}){
  const token=await userAccessToken();const r=await fetch(url,{method,headers:{authorization:'Bearer '+token,...headers},body});
  const b=Buffer.from(await r.arrayBuffer());if(!r.ok){const e=new Error('google HTTP '+r.status+': '+b.toString('utf8',0,Math.min(900,b.length)));e.status=r.status;throw e;}
  return {buffer:b,headers:r.headers,status:r.status};
}
async function metadata(id){
  const fields=encodeURIComponent('id,name,mimeType,size,createdTime,modifiedTime,version,trashed,md5Checksum,sha1Checksum,sha256Checksum,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive,canAddChildren)');
  return gjson('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?supportsAllDrives=true&fields='+fields);
}
function collect(elements,out){
  for(const el of elements||[]){
    for(const pe of el?.paragraph?.elements||[])if(pe?.textRun?.content)out.push(pe.textRun.content);
    for(const row of el?.table?.tableRows||[])for(const cell of row?.tableCells||[])collect(cell?.content||[],out);
    if(el?.tableOfContents?.content)collect(el.tableOfContents.content,out);
  }
}
function docText(doc){const out=[];const walk=tab=>{collect(tab?.documentTab?.body?.content||[],out);for(const ch of tab?.childTabs||[])walk(ch);};if(Array.isArray(doc.tabs)&&doc.tabs.length)for(const t of doc.tabs)walk(t);else collect(doc?.body?.content||[],out);return out.join('');}
async function docSnapshot(id){const d=await gjson('https://docs.googleapis.com/v1/documents/'+encodeURIComponent(id)+'?includeTabsContent=true');return {document_id:id,title:d.title,revision_id:d.revisionId,text:docText(d)};}
async function docsBatch(id,requests,expected){const body={requests};if(expected)body.writeControl={requiredRevisionId:expected};try{return await gjson('https://docs.googleapis.com/v1/documents/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',body});}catch(e){if(expected&&(e.status===400||e.status===409))throw new Error('REVISION_MISMATCH: '+e.message);throw e;}}
function escQ(s){return String(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");}
async function driveSearch(a={}){
  const clauses=['trashed = false'];const query=String(a.query||'').trim();if(query)clauses.push("(name contains '"+escQ(query)+"' or fullText contains '"+escQ(query)+"')");
  if(a.mime_type)clauses.push("mimeType = '"+escQ(a.mime_type)+"'");if(a.parent_id)clauses.push("'"+escQ(a.parent_id)+"' in parents");
  const q=new URLSearchParams({q:clauses.join(' and '),pageSize:String(Math.max(1,Math.min(50,Number(a.top_n||20)))),orderBy:'modifiedTime desc',spaces:'drive',fields:'files(id,name,mimeType,size,createdTime,modifiedTime,version,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive,canAddChildren))'});
  const o=await gjson('https://www.googleapis.com/drive/v3/files?'+q.toString());return {results:o.files||[]};
}
async function rawRead(a={}){
  const id=String(a.file_id||a.id||'').trim();if(!id)throw new Error('file_id required');const m=await metadata(id);
  if(String(m.mimeType||'').startsWith('application/vnd.google-apps.'))throw new Error('native Google file: use native tool');
  const start=Math.max(0,Number(a.start_byte||0)),max=Math.max(1,Math.min(4194304,Number(a.max_bytes||1048576)));
  const {buffer,headers}=await gbytes('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?alt=media&supportsAllDrives=true',{headers:{Range:'bytes='+start+'-'+(start+max-1)}});
  const textual=/^(text\/|application\/(json|xml|javascript|x-javascript|yaml|x-yaml|csv))/.test(String(m.mimeType||''));const enc=String(a.encoding||'auto')==='auto'?(textual?'utf8':'base64'):String(a.encoding);
  return {file_id:id,name:m.name,mime_type:m.mimeType,drive_version:m.version,start_byte:start,bytes_returned:buffer.length,content_range:headers.get('content-range')||null,encoding:enc,content:enc==='utf8'?buffer.toString('utf8'):buffer.toString('base64')};
}
async function sheetsGet(id){return gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'?includeGridData=false');}
async function sheetsValues(id,range){return gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values/'+encodeURIComponent(range)+'?majorDimension=ROWS');}
async function slidesGet(id){return gjson('https://slides.googleapis.com/v1/presentations/'+encodeURIComponent(id));}
function slideText(p){return (p.slides||[]).map((s,i)=>{const chunks=[];for(const el of s.pageElements||[]){for(const te of el?.shape?.text?.textElements||[])if(te?.textRun?.content)chunks.push(te.textRun.content);for(const row of el?.table?.tableRows||[])for(const cell of row.tableCells||[])for(const te of cell?.text?.textElements||[])if(te?.textRun?.content)chunks.push(te.textRun.content);}return {index:i,object_id:s.objectId,text:chunks.join('')};});}
async function fetchAny(a={}){
  const id=String(a.id||a.file_id||'').trim();if(!id)throw new Error('id required');const m=await metadata(id);
  const meta={id:m.id,name:m.name,mime_type:m.mimeType,size:m.size||null,created_time:m.createdTime,modified_time:m.modifiedTime,drive_version:m.version,parents:m.parents||[],drive_id:m.driveId||null,url:m.webViewLink||null,trashed:!!m.trashed,capabilities:m.capabilities||{}};
  if(m.mimeType==='application/vnd.google-apps.document')return {metadata:meta,document:await docSnapshot(id)};
  if(m.mimeType==='application/vnd.google-apps.spreadsheet')return {metadata:meta,spreadsheet:await sheetsGet(id)};
  if(m.mimeType==='application/vnd.google-apps.presentation'){const p=await slidesGet(id);return {metadata:meta,presentation:{presentation_id:p.presentationId,title:p.title,page_size:p.pageSize,slides:slideText(p)}};}
  if(m.mimeType==='application/vnd.google-apps.folder')return {metadata:meta,children:await driveSearch({parent_id:id,top_n:a.top_n||50})};
  return {metadata:meta,content:await rawRead({file_id:id,max_bytes:a.max_bytes||1048576,encoding:a.encoding||'auto'})};
}
async function ensureEdit(id,{allowTrashed=false}={}){const m=await metadata(id);if(!m?.capabilities?.canEdit||(!allowTrashed&&m.trashed))throw new Error('drive write denied');return m;}
async function ensureParent(id){if(!id)return null;const m=await metadata(id);if(m.mimeType!=='application/vnd.google-apps.folder')throw new Error('parent_id is not folder');if(!m?.capabilities?.canAddChildren&&!m?.capabilities?.canEdit)throw new Error('drive create denied');return m;}
async function createMetadata(name,mime,parent){if(parent)await ensureParent(parent);const body={name:String(name||'').trim(),mimeType:mime};if(!body.name)throw new Error('name required');if(parent)body.parents=[parent];return gjson('https://www.googleapis.com/drive/v3/files?supportsAllDrives=true&fields=id,name,mimeType,size,createdTime,modifiedTime,version,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive,canAddChildren)',{method:'POST',body});}
async function createRaw(a={}){
  const name=String(a.name||'').trim(),mime=String(a.mime_type||'application/octet-stream'),parent=String(a.parent_id||'').trim();if(!name)throw new Error('name required');if(parent)await ensureParent(parent);
  const content=a.content_base64!=null?Buffer.from(String(a.content_base64),'base64'):Buffer.from(String(a.content_text||''),'utf8');
  const boundary='nd-'+crypto.randomBytes(12).toString('hex'),meta={name};if(parent)meta.parents=[parent];
  const body=Buffer.concat([Buffer.from('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+JSON.stringify(meta)+'\r\n--'+boundary+'\r\nContent-Type: '+mime+'\r\n\r\n'),content,Buffer.from('\r\n--'+boundary+'--\r\n')]);
  const token=await userAccessToken();const r=await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,mimeType,size,createdTime,modifiedTime,version,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive)',{method:'POST',headers:{authorization:'Bearer '+token,'content-type':'multipart/related; boundary='+boundary},body});
  const t=await r.text();if(!r.ok)throw new Error('google HTTP '+r.status+': '+t.slice(0,800));return JSON.parse(t||'{}');
}
async function replaceRaw(a={}){
  const id=String(a.file_id||'').trim();const before=await ensureEdit(id);if(String(before.mimeType||'').startsWith('application/vnd.google-apps.'))throw new Error('native Google file: use native tool');
  if(a.expected_drive_version!=null&&String(before.version)!==String(a.expected_drive_version))throw new Error('DRIVE_VERSION_MISMATCH: expected '+a.expected_drive_version+' got '+before.version);
  const mime=String(a.mime_type||before.mimeType||'application/octet-stream'),content=a.content_base64!=null?Buffer.from(String(a.content_base64),'base64'):Buffer.from(String(a.content_text||''),'utf8'),token=await userAccessToken();
  const r=await fetch('https://www.googleapis.com/upload/drive/v3/files/'+encodeURIComponent(id)+'?uploadType=media&supportsAllDrives=true&fields=id,name,mimeType,size,modifiedTime,version,md5Checksum,sha256Checksum',{method:'PATCH',headers:{authorization:'Bearer '+token,'content-type':mime},body:content});
  const t=await r.text();if(!r.ok)throw new Error('google HTTP '+r.status+': '+t.slice(0,800));const after=JSON.parse(t||'{}');return {file_id:id,before_drive_version:before.version,after_drive_version:after.version,size:after.size||null};
}
async function updateMeta(a={}){
  const id=String(a.file_id||'').trim(),before=await ensureEdit(id,{allowTrashed:a.trashed===false});
  if(a.expected_drive_version!=null&&String(before.version)!==String(a.expected_drive_version))throw new Error('DRIVE_VERSION_MISMATCH: expected '+a.expected_drive_version+' got '+before.version);
  const params=new URLSearchParams({supportsAllDrives:'true',fields:'id,name,mimeType,size,createdTime,modifiedTime,version,trashed,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive)'}),body={};
  if(a.name!=null)body.name=String(a.name);if(a.trashed!=null)body.trashed=!!a.trashed;if(a.add_parent_id){await ensureParent(String(a.add_parent_id));params.set('addParents',String(a.add_parent_id));}if(a.remove_parent_id)params.set('removeParents',String(a.remove_parent_id));
  return {before_drive_version:before.version,file:await gjson('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?'+params.toString(),{method:'PATCH',body})};
}
async function del(a={}){const id=String(a.file_id||'').trim(),m=await ensureEdit(id,{allowTrashed:true});if(!m?.capabilities?.canDelete)throw new Error('drive delete denied');const token=await userAccessToken();const r=await fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?supportsAllDrives=true',{method:'DELETE',headers:{authorization:'Bearer '+token}});if(!r.ok){const t=await r.text();throw new Error('google HTTP '+r.status+': '+t.slice(0,600));}return {file_id:id,deleted:true};}
async function invoke(tool,a={}){
  if(tool==='search')return driveSearch(a);
  if(tool==='fetch')return fetchAny(a);
  if(tool==='drive_get_metadata')return metadata(String(a.file_id||''));
  if(tool==='drive_get_currentness_token'){const m=await metadata(String(a.file_id||''));const o={file_id:m.id,name:m.name,mime_type:m.mimeType,drive_version:m.version,modified_time:m.modifiedTime,trashed:!!m.trashed,can_edit:!!m?.capabilities?.canEdit};if(m.mimeType==='application/vnd.google-apps.document')o.docs_revision_id=(await docSnapshot(m.id)).revision_id;return o;}
  if(tool==='drive_read_content')return rawRead(a);
  if(tool==='drive_list_children')return driveSearch({parent_id:String(a.folder_id||''),top_n:a.top_n||50});
  if(tool==='drive_create_folder')return createMetadata(a.name,'application/vnd.google-apps.folder',String(a.parent_id||'')||null);
  if(tool==='drive_create_native_file'){const map={document:'application/vnd.google-apps.document',spreadsheet:'application/vnd.google-apps.spreadsheet',presentation:'application/vnd.google-apps.presentation'};if(!map[String(a.kind||'')])throw new Error('invalid native kind');return createMetadata(a.name,map[a.kind],String(a.parent_id||'')||null);}
  if(tool==='drive_create_raw_file')return createRaw(a);
  if(tool==='drive_replace_content')return replaceRaw(a);
  if(tool==='drive_update_metadata')return updateMeta(a);
  if(tool==='drive_delete_file')return del(a);
  if(tool==='docs_read')return docSnapshot(String(a.document_id||''));
  if(tool==='docs_append'){const id=String(a.document_id||''),before=await docSnapshot(id),expected=String(a.expected_revision_id||before.revision_id||'');await docsBatch(id,[{insertText:{endOfSegmentLocation:{},text:String(a.text||'')}}],expected);const after=await docSnapshot(id);return {document_id:id,before_revision_id:before.revision_id,after_revision_id:after.revision_id,text_length:after.text.length};}
  if(tool==='docs_replace_exact'){const id=String(a.document_id||''),before=await docSnapshot(id),old=String(a.old_text||''),neu=String(a.new_text||''),count=before.text.split(old).length-1;if(!old||count!==1)throw new Error('EXACT_MATCH_REQUIRED: found '+count+' occurrences');const expected=String(a.expected_revision_id||before.revision_id||'');const result=await docsBatch(id,[{replaceAllText:{containsText:{text:old,matchCase:true},replaceText:neu}}],expected);const after=await docSnapshot(id);return {document_id:id,occurrences_changed:result?.replies?.[0]?.replaceAllText?.occurrencesChanged??null,before_revision_id:before.revision_id,after_revision_id:after.revision_id};}
  if(tool==='docs_batch_update'){const id=String(a.document_id||''),before=await docSnapshot(id),expected=String(a.expected_revision_id||before.revision_id||''),result=await docsBatch(id,a.requests||[],expected),after=await docSnapshot(id);return {before_revision_id:before.revision_id,after_revision_id:after.revision_id,result};}
  if(tool==='sheets_get')return sheetsGet(String(a.spreadsheet_id||''));
  if(tool==='sheets_get_values')return sheetsValues(String(a.spreadsheet_id||''),String(a.range||''));
  if(tool==='sheets_update_values'){const id=String(a.spreadsheet_id||''),before=await metadata(id);if(a.expected_drive_version!=null&&String(before.version)!==String(a.expected_drive_version))throw new Error('DRIVE_VERSION_MISMATCH: expected '+a.expected_drive_version+' got '+before.version);const range=String(a.range||'');const q=new URLSearchParams({valueInputOption:String(a.value_input_option||'USER_ENTERED'),includeValuesInResponse:'true'});const result=await gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values/'+encodeURIComponent(range)+'?'+q.toString(),{method:'PUT',body:{range,majorDimension:'ROWS',values:a.values||[]}});const after=await metadata(id),readback=await sheetsValues(id,range);return {before_drive_version:before.version,after_drive_version:after.version,update:result,readback};}
  if(tool==='sheets_batch_update'){const id=String(a.spreadsheet_id||''),before=await metadata(id);if(a.expected_drive_version!=null&&String(before.version)!==String(a.expected_drive_version))throw new Error('DRIVE_VERSION_MISMATCH: expected '+a.expected_drive_version+' got '+before.version);const result=await gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',body:{requests:a.requests||[],includeSpreadsheetInResponse:!!a.include_spreadsheet_in_response}});const after=await metadata(id);return {before_drive_version:before.version,after_drive_version:after.version,result};}
  if(tool==='slides_get'){const p=await slidesGet(String(a.presentation_id||''));return {presentation_id:p.presentationId,title:p.title,page_size:p.pageSize,slides:slideText(p),raw:p};}
  if(tool==='slides_batch_update'){const id=String(a.presentation_id||''),before=await metadata(id);if(a.expected_drive_version!=null&&String(before.version)!==String(a.expected_drive_version))throw new Error('DRIVE_VERSION_MISMATCH: expected '+a.expected_drive_version+' got '+before.version);const result=await gjson('https://slides.googleapis.com/v1/presentations/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',body:{requests:a.requests||[]}});const after=await metadata(id);return {before_drive_version:before.version,after_drive_version:after.version,result};}
  throw new Error('tool_not_allowed');
}
const TOOLS=['search','fetch','drive_get_metadata','drive_get_currentness_token','drive_read_content','drive_list_children','drive_create_folder','drive_create_native_file','drive_create_raw_file','drive_replace_content','drive_update_metadata','drive_delete_file','docs_read','docs_append','docs_replace_exact','docs_batch_update','sheets_get','sheets_get_values','sheets_update_values','sheets_batch_update','slides_get','slides_batch_update'];
function send(res,status,obj){const raw=Buffer.from(JSON.stringify(obj));res.writeHead(status,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});res.end(raw);}
async function readBody(req){const a=[];for await(const c of req)a.push(c);return Buffer.concat(a).toString('utf8');}
const server=http.createServer(async(req,res)=>{
  try{
    const u=new URL(req.url||'/','http://127.0.0.1:'+PORT);
    if(req.method==='GET'&&u.pathname==='/drive/health'){
      const token=await userAccessToken();
      const about=await gjson('https://www.googleapis.com/drive/v3/about?fields=user(emailAddress),storageQuota');
      return send(res,200,{ok:true,service:'ND qstash Full Drive',auth_mode:'user_oauth',full_rw:true,tools:TOOLS.length,user:about.user?.emailAddress||null,storage_quota_present:!!about.storageQuota});
    }
    if(req.method==='POST'&&u.pathname==='/drive/invoke'){
      if(!safeEqual(req.headers['x-nd-bridge-key'],BRIDGE_KEY))return send(res,401,{ok:false,error:'unauthorized'});
      let j={};try{j=JSON.parse(await readBody(req)||'{}');}catch{return send(res,400,{ok:false,error:'invalid_json'});}
      const tool=String(j.tool||''),args=(j.args&&typeof j.args==='object')?j.args:{};
      if(!TOOLS.includes(tool))return send(res,403,{ok:false,error:'tool_denied'});
      try{return send(res,200,{ok:true,tool,result:await invoke(tool,args)});}catch(e){const msg=String(e?.message||e).slice(0,1200);const status=(msg.includes('REVISION_MISMATCH')||msg.includes('DRIVE_VERSION_MISMATCH')||msg.includes('EXACT_MATCH_REQUIRED'))?409:502;return send(res,status,{ok:false,error:msg});}
    }
    return send(res,404,{ok:false,error:'not_found'});
  }catch(e){return send(res,503,{ok:false,error:String(e?.message||e).slice(0,1000)});}
});
server.listen(PORT,'0.0.0.0',()=>console.log('ND_QSTASH_FULL_DRIVE_READY '+JSON.stringify({port:PORT,tools:TOOLS.length,auth_mode:'user_oauth'})));
