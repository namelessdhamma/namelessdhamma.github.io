import http from 'node:http';
import crypto from 'node:crypto';

const PORT=Number(process.env.PORT||3002);
const BRIDGE_KEY=String(process.env.ND_DRIVE_BRIDGE_TOKEN||'').trim();
const SERVICE_EMAIL=String(process.env.ND_GOOGLE_CLIENT_EMAIL||'').trim();
const SERVICE_KEY_B64=String(process.env.ND_GOOGLE_PRIVATE_KEY_B64||'').trim();
const OAUTH_CLIENT_ID=String(process.env.ND_DRIVE_USER_OAUTH_CLIENT_ID||'').trim();
const OAUTH_CLIENT_SECRET=String(process.env.ND_DRIVE_USER_OAUTH_CLIENT_SECRET||'').trim();
const OAUTH_REFRESH_ENV=String(process.env.ND_DRIVE_USER_OAUTH_REFRESH_TOKEN||'').trim();
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
  if(OAUTH_REFRESH_ENV)return OAUTH_REFRESH_ENV;
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
const MCP_TOOLS = [
  {name:'search',description:'Search files/folders in the user-authorized Drive corpus.',inputSchema:{type:'object',properties:{query:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50},mime_type:{type:'string'},parent_id:{type:'string'}},additionalProperties:false}},
  {name:'fetch',description:'Universal fetch: Docs text, Sheets metadata, Slides text/structure, folders, or raw-file content.',inputSchema:{type:'object',properties:{id:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50},max_bytes:{type:'integer',minimum:1,maximum:4194304},encoding:{type:'string',enum:['auto','utf8','base64']}},required:['id'],additionalProperties:false}},
  {name:'drive_get_metadata',description:'Read Drive metadata/capabilities for a file or folder.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'drive_get_currentness_token',description:'Read Drive version and Docs revision when applicable.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'drive_read_content',description:'Read raw non-Google-native file bytes in bounded chunks as UTF-8 or base64.',inputSchema:{type:'object',properties:{file_id:{type:'string'},start_byte:{type:'integer',minimum:0},max_bytes:{type:'integer',minimum:1,maximum:4194304},encoding:{type:'string',enum:['auto','utf8','base64']}},required:['file_id'],additionalProperties:false}},
  {name:'drive_list_children',description:'List direct children of a Drive folder.',inputSchema:{type:'object',properties:{folder_id:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50}},required:['folder_id'],additionalProperties:false}},
  {name:'drive_create_folder',description:'Create a folder in a writable user-authorized parent.',inputSchema:{type:'object',properties:{name:{type:'string'},parent_id:{type:'string'}},required:['name'],additionalProperties:false}},
  {name:'drive_create_native_file',description:'Create a native Google Doc, Sheet, or Slides file.',inputSchema:{type:'object',properties:{name:{type:'string'},kind:{type:'string',enum:['document','spreadsheet','presentation']},parent_id:{type:'string'}},required:['name','kind'],additionalProperties:false}},
  {name:'drive_create_raw_file',description:'Create an arbitrary raw Drive file from UTF-8 text or base64 bytes.',inputSchema:{type:'object',properties:{name:{type:'string'},mime_type:{type:'string'},parent_id:{type:'string'},content_text:{type:'string'},content_base64:{type:'string'}},required:['name','mime_type'],additionalProperties:false}},
  {name:'drive_replace_content',description:'Replace all bytes of a non-Google-native file after optional Drive-version precondition.',inputSchema:{type:'object',properties:{file_id:{type:'string'},mime_type:{type:'string'},content_text:{type:'string'},content_base64:{type:'string'},expected_drive_version:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'drive_update_metadata',description:'Rename, move, or trash/untrash a file/folder after optional Drive-version precondition.',inputSchema:{type:'object',properties:{file_id:{type:'string'},name:{type:'string'},add_parent_id:{type:'string'},remove_parent_id:{type:'string'},trashed:{type:'boolean'},expected_drive_version:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'drive_delete_file',description:'Permanently delete a provider-deletable file/folder.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'docs_read',description:'Read current Google Doc text and revision.',inputSchema:{type:'object',properties:{document_id:{type:'string'}},required:['document_id'],additionalProperties:false}},
  {name:'docs_append',description:'Append text with Google Docs revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},text:{type:'string'},expected_revision_id:{type:'string'}},required:['document_id','text'],additionalProperties:false}},
  {name:'docs_replace_exact',description:'Replace exactly one text occurrence with revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},old_text:{type:'string'},new_text:{type:'string'},expected_revision_id:{type:'string'}},required:['document_id','old_text','new_text'],additionalProperties:false}},
  {name:'docs_batch_update',description:'Run arbitrary Google Docs batchUpdate requests with required revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},requests:{type:'array',items:{type:'object'}},expected_revision_id:{type:'string'}},required:['document_id','requests'],additionalProperties:false}},
  {name:'sheets_get',description:'Read Google Sheets spreadsheet metadata and structure.',inputSchema:{type:'object',properties:{spreadsheet_id:{type:'string'}},required:['spreadsheet_id'],additionalProperties:false}},
  {name:'sheets_get_values',description:'Read an arbitrary A1 range from Google Sheets.',inputSchema:{type:'object',properties:{spreadsheet_id:{type:'string'},range:{type:'string'}},required:['spreadsheet_id','range'],additionalProperties:false}},
  {name:'sheets_update_values',description:'Write values to an arbitrary A1 range with optional Drive-version precondition and provider readback.',inputSchema:{type:'object',properties:{spreadsheet_id:{type:'string'},range:{type:'string'},values:{type:'array',items:{type:'array'}},value_input_option:{type:'string'},expected_drive_version:{type:'string'}},required:['spreadsheet_id','range','values'],additionalProperties:false}},
  {name:'sheets_batch_update',description:'Run arbitrary Google Sheets batchUpdate requests with optional Drive-version precondition.',inputSchema:{type:'object',properties:{spreadsheet_id:{type:'string'},requests:{type:'array',items:{type:'object'}},include_spreadsheet_in_response:{type:'boolean'},expected_drive_version:{type:'string'}},required:['spreadsheet_id','requests'],additionalProperties:false}},
  {name:'slides_get',description:'Read Google Slides structure, text, object IDs, and raw presentation JSON.',inputSchema:{type:'object',properties:{presentation_id:{type:'string'}},required:['presentation_id'],additionalProperties:false}},
  {name:'slides_batch_update',description:'Run arbitrary Google Slides batchUpdate requests with optional Drive-version precondition.',inputSchema:{type:'object',properties:{presentation_id:{type:'string'},requests:{type:'array',items:{type:'object'}},expected_drive_version:{type:'string'}},required:['presentation_id','requests'],additionalProperties:false}}
]

function send(res,status,obj){const raw=Buffer.from(JSON.stringify(obj));res.writeHead(status,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});res.end(raw);}
async function readBody(req){const a=[];for await(const c of req)a.push(c);return Buffer.concat(a).toString('utf8');}

function rpcResult(id,result){return {jsonrpc:'2.0',id,result};}
function rpcError(id,code,message){return {jsonrpc:'2.0',id,error:{code,message}};}
async function driveMcpMessage(msg){
  const id=msg?.id??null,method=String(msg?.method||'');
  if(method==='initialize')return rpcResult(id,{protocolVersion:String(msg?.params?.protocolVersion||'2025-06-18'),capabilities:{tools:{listChanged:false}},serverInfo:{name:'ND Drive Reserve Qstash',version:'2.1.0'},instructions:'Second synchronous full-RW MCP route to the same authoritative Nameless Dhamma Google Drive corpus. User OAuth; no content replication. Use provider readback and CAS/version preconditions for consequential writes.'});
  if(method==='ping')return rpcResult(id,{});
  if(method==='tools/list')return rpcResult(id,{tools:MCP_TOOLS});
  if(method==='tools/call'){
    const name=String(msg?.params?.name||'');
    if(!TOOLS.includes(name))return rpcResult(id,{content:[{type:'text',text:'tool_denied'}],structuredContent:{ok:false,error:'tool_denied'},isError:true});
    try{const result=await invoke(name,msg?.params?.arguments||{});return rpcResult(id,{content:[{type:'text',text:JSON.stringify(result)}],structuredContent:result,isError:false});}
    catch(e){const message=String(e?.message||e).slice(0,1200);return rpcResult(id,{content:[{type:'text',text:message}],structuredContent:{ok:false,error:message},isError:true});}
  }
  if(method.startsWith('notifications/'))return null;
  return rpcError(id,-32601,'Method not found');
}
async function handleDriveMcp(req,res){
  if(!safeEqual(req.headers['x-nd-bridge-key'],BRIDGE_KEY))return send(res,401,{ok:false,error:'unauthorized'});
  if(req.method==='GET'){res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});res.write(': nd-drive-qstash\n\n');return res.end();}
  if(req.method!=='POST')return send(res,405,{ok:false,error:'method_not_allowed'});
  let msg={};try{msg=JSON.parse(await readBody(req)||'{}');}catch{return send(res,400,rpcError(null,-32700,'Parse error'));}
  const out=await driveMcpMessage(msg);if(out===null){res.writeHead(202,{'cache-control':'no-store'});return res.end();}return send(res,200,out);
}



async function runMcpLoopbackCanary(){
  if(process.env.ND_DRIVE_MCP_CANARY!=='20261015')return;
  const endpoint='http://127.0.0.1:'+PORT+'/drive/mcp';
  const rpc=async(message,secret=BRIDGE_KEY)=>{
    const resp=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json','x-nd-bridge-key':secret},body:JSON.stringify(message)});
    return {status:resp.status,data:await resp.json()};
  };
  try{
    const no=await rpc({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}},'incorrect-key');
    if(no.status!==401)throw new Error('unauthorized_request_accepted');
    const init=await rpc({jsonrpc:'2.0',id:2,method:'initialize',params:{protocolVersion:'2025-06-18'}});
    if(init.status!==200||!init.data?.result?.capabilities?.tools)throw new Error('initialize_invalid');
    const ls=await rpc({jsonrpc:'2.0',id:3,method:'tools/list'});
    if(ls.status!==200||ls.data?.result?.tools?.length!==22)throw new Error('tools_list_invalid');
    const call=await rpc({jsonrpc:'2.0',id:4,method:'tools/call',params:{name:'search',arguments:{query:'ND_RENDER_EPHEMERAL_QUAL_',top_n:1}}});
    if(call.status!==200||call.data?.result?.isError||!Array.isArray(call.data?.result?.structuredContent?.results))throw new Error('search_dispatch_invalid');
    console.log('ND_DRIVE_RENDER_MCP_LOOPBACK_AUTH_22TOOLS_GOOGLE_READ_PASS');
  }catch(e){
    const reason=String(e?.message||e);
    const cls=/unauthorized_request_accepted/.test(reason)?'AUTH_BYPASS':/initialize_invalid/.test(reason)?'INITIALIZE':/tools_list_invalid/.test(reason)?'TOOLS_LIST':/search_dispatch_invalid/.test(reason)?'GOOGLE_READ':'OTHER';
    console.warn('ND_DRIVE_RENDER_MCP_LOOPBACK_FAIL class='+cls);
  }
}

async function runRenderRwQualification(){
  if(process.env.ND_DRIVE_QUALIFY_RUN!=='rw-20261015-b')return;
  const marker=crypto.randomBytes(7).toString('hex');
  const made=[];const results=[];
  const check=(x,reason)=>{if(!x)throw new Error(reason);};
  const safeClass=e=>{
    const msg=String(e?.message||e);
    if(/DRIVE_VERSION_MISMATCH/.test(msg))return 'VERSION_MISMATCH';
    if(/REVISION_MISMATCH/.test(msg))return 'REVISION_MISMATCH';
    if(/EXACT_MATCH_REQUIRED/.test(msg))return 'EXACT_MATCH_REQUIRED';
    const match=msg.match(/(?:google[_ ]HTTP[_ ]|oauth_refresh_http_)(\d{3})/i);
    return match?'PROVIDER_HTTP_'+match[1]:'VALIDATION_OR_OTHER';
  };
  async function phase(name,fn){
    try{await fn();results.push({name,ok:true});console.log('ND_DRIVE_RENDER_QUAL_'+name+'_PASS');}
    catch(e){results.push({name,ok:false});console.warn('ND_DRIVE_RENDER_QUAL_'+name+'_FAIL class='+safeClass(e));}
  }
  let folder=null;
  try{
    await phase('MCP_LOCAL_DISPATCH',async()=>{
      const init=await driveMcpMessage({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}});
      const list=await driveMcpMessage({jsonrpc:'2.0',id:2,method:'tools/list'});
      check(init?.result?.capabilities?.tools&&list?.result?.tools?.length===22,'mcp_list_invalid');
      check(new Set(list.result.tools.map(t=>t.name)).size===22,'mcp_duplicate_tools');
    });
    await phase('FOLDER_CREATE_READ',async()=>{
      folder=await invoke('drive_create_folder',{name:'ND_RENDER_EPHEMERAL_QUAL_'+marker});
      check(folder?.id,'folder_no_id');made.push(folder.id);
      const m=await invoke('drive_get_metadata',{file_id:folder.id});
      check(m.id===folder.id&&m.mimeType==='application/vnd.google-apps.folder','folder_readback');
      const q=await invoke('search',{query:'ND_RENDER_EPHEMERAL_QUAL_'+marker,top_n:10});
      check(q.results.some(f=>f.id===folder.id),'folder_search_readback');
    });
    if(!folder?.id) return;
    await phase('DRIVE_RAW_CRUD',async()=>{
      const f=await invoke('drive_create_raw_file',{name:'probe.txt',mime_type:'text/plain',parent_id:folder.id,content_text:'nd-alpha'});
      check(f?.id,'raw_no_id');made.push(f.id);
      const m=await invoke('drive_get_currentness_token',{file_id:f.id});
      const before=await invoke('drive_read_content',{file_id:f.id,max_bytes:128,encoding:'utf8'});
      check(before.content==='nd-alpha','raw_readback_before');
      let version=String(m.drive_version);
      try{await invoke('drive_replace_content',{file_id:f.id,mime_type:'text/plain',content_text:'nd-beta',expected_drive_version:version});}
      catch(e){
        if(!String(e?.message||e).includes('DRIVE_VERSION_MISMATCH'))throw e;
        const unchanged=await invoke('drive_read_content',{file_id:f.id,max_bytes:128,encoding:'utf8'});
        check(unchanged.content==='nd-alpha','concurrent_unexpected_change');
        const fresh=await invoke('drive_get_currentness_token',{file_id:f.id});
        version=String(fresh.drive_version);
        console.log('ND_DRIVE_RENDER_QUAL_RAW_CAS_REFRESH');
        await invoke('drive_replace_content',{file_id:f.id,mime_type:'text/plain',content_text:'nd-beta',expected_drive_version:version});
      }
      const after=await invoke('drive_read_content',{file_id:f.id,max_bytes:128,encoding:'utf8'});
      check(after.content==='nd-beta','raw_readback_after');
      let mismatch=false;
      try{await invoke('drive_replace_content',{file_id:f.id,mime_type:'text/plain',content_text:'must-not-write',expected_drive_version:'0'});}
      catch(e){mismatch=String(e?.message||e).includes('DRIVE_VERSION_MISMATCH');}
      check(mismatch,'stale_version_not_blocked');
      await invoke('drive_update_metadata',{file_id:f.id,name:'probe-renamed.txt'});
      const renamed=await invoke('drive_get_metadata',{file_id:f.id});
      check(renamed.name==='probe-renamed.txt','rename_readback');
    });
    await phase('DOCS_CRUD',async()=>{
      const f=await invoke('drive_create_native_file',{name:'probe-doc',kind:'document',parent_id:folder.id});
      check(f?.id,'doc_no_id');made.push(f.id);
      const before=await invoke('docs_read',{document_id:f.id});
      await invoke('docs_append',{document_id:f.id,text:'ND_RENDER_ALPHA',expected_revision_id:before.revision_id});
      const middle=await invoke('docs_read',{document_id:f.id});
      check(middle.text.includes('ND_RENDER_ALPHA'),'docs_append_readback');
      await invoke('docs_replace_exact',{document_id:f.id,old_text:'ND_RENDER_ALPHA',new_text:'ND_RENDER_BETA',expected_revision_id:middle.revision_id});
      const after=await invoke('docs_read',{document_id:f.id});
      check(after.text.includes('ND_RENDER_BETA')&&!after.text.includes('ND_RENDER_ALPHA'),'docs_replace_readback');
    });
    await phase('SHEETS_CRUD',async()=>{
      const f=await invoke('drive_create_native_file',{name:'probe-sheet',kind:'spreadsheet',parent_id:folder.id});
      check(f?.id,'sheet_no_id');made.push(f.id);
      let sh=await invoke('sheets_get',{spreadsheet_id:f.id});
      const sname=sh.sheets?.[0]?.properties?.title;
      let sheetName=sname;
      if(!sheetName){
        await invoke('sheets_batch_update',{spreadsheet_id:f.id,requests:[{addSheet:{properties:{title:'Qualification'}}}]});
        sheetName='Qualification';
      }
      const range="'"+sheetName.replace(/'/g,"''")+"'!A1:B1";
      await invoke('sheets_update_values',{spreadsheet_id:f.id,range,values:[['nd-key','nd-value']],value_input_option:'RAW'});
      const read=await invoke('sheets_get_values',{spreadsheet_id:f.id,range});
      check(read.values?.[0]?.[0]==='nd-key'&&read.values?.[0]?.[1]==='nd-value','sheets_readback');
      await invoke('sheets_batch_update',{spreadsheet_id:f.id,requests:[{updateSpreadsheetProperties:{properties:{title:'probe-sheet-updated'},fields:'title'}}]});
      sh=await invoke('sheets_get',{spreadsheet_id:f.id});
      check(sh.properties?.title==='probe-sheet-updated','sheets_batch_readback');
    });
    await phase('SLIDES_CRUD',async()=>{
      const f=await invoke('drive_create_native_file',{name:'probe-slides',kind:'presentation',parent_id:folder.id});
      check(f?.id,'slides_no_id');made.push(f.id);
      const s='nd_qual_slide_'+marker, shape='nd_qual_text_'+marker;
      const requests=[
        {createSlide:{objectId:s,slideLayoutReference:{predefinedLayout:'BLANK'}}},
        {createShape:{objectId:shape,shapeType:'TEXT_BOX',elementProperties:{pageObjectId:s,size:{width:{magnitude:200,unit:'PT'},height:{magnitude:60,unit:'PT'}},transform:{scaleX:1,scaleY:1,translateX:25,translateY:25,unit:'PT'}}}},
        {insertText:{objectId:shape,text:'ND_RENDER_SLIDE_OK',insertionIndex:0}}
      ];
      await invoke('slides_batch_update',{presentation_id:f.id,requests});
      const after=await invoke('slides_get',{presentation_id:f.id});
      check(after.slides?.some(t=>t.text.includes('ND_RENDER_SLIDE_OK')),'slides_readback');
    });
    await phase('FOLDER_CHILDREN',async()=>{
      const ch=await invoke('drive_list_children',{folder_id:folder.id,top_n:25});
      check(Array.isArray(ch.results)&&ch.results.length>=3,'children_missing');
    });
  }finally{
    let fails=0;
    for(const id of made.slice().reverse()){
      try{await invoke('drive_delete_file',{file_id:id});}
      catch(e){fails++;console.warn('ND_DRIVE_RENDER_QUAL_CLEANUP_ITEM_FAIL id='+id+' class='+safeClass(e));}
    }
    console.log(fails?'ND_DRIVE_RENDER_QUAL_CLEANUP_FAIL count='+fails:'ND_DRIVE_RENDER_QUAL_CLEANUP_PASS');
    console.log('ND_DRIVE_RENDER_QUAL_SUMMARY '+JSON.stringify({passed:results.filter(r=>r.ok).map(r=>r.name),failed:results.filter(r=>!r.ok).map(r=>r.name),cleanup_fails:fails}));
  }
}

const server=http.createServer(async(req,res)=>{
  try{
    const u=new URL(req.url||'/','http://127.0.0.1:'+PORT);
    if(req.method==='GET'&&u.pathname==='/livez')return send(res,200,{ok:true});
    if(!safeEqual(req.headers['x-nd-bridge-key'],BRIDGE_KEY))return send(res,401,{ok:false,error:'unauthorized'});
    if(u.pathname==='/drive/mcp')return handleDriveMcp(req,res);
    if(req.method==='GET'&&u.pathname==='/drive/mcp/health')return send(res,200,{ok:true,service:'ND Drive Reserve Qstash MCP',full_rw:true,tools:MCP_TOOLS.length,transport:'streamable-http',auth:'x-nd-bridge-key'});
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
  }catch(e){return send(res,503,{ok:false,error:'provider_unavailable'});}
});
if(!BRIDGE_KEY||!SERVICE_EMAIL||!SERVICE_KEY_B64||!OAUTH_CLIENT_ID||!OAUTH_CLIENT_SECRET)throw new Error('required_protected_env_missing');
server.listen(PORT,'0.0.0.0',()=>{
  console.log('ND_DRIVE_RENDER_READY '+JSON.stringify({tools:TOOLS.length,auth:'protected_bridge',google:'pending_readback'}));
  setImmediate(async()=>{
    try{await serviceAccessToken();console.log('ND_DRIVE_RENDER_SERVICE_ACCOUNT_PASS');}
    catch(e){
      const message=String(e?.message||'');
      const http=message.match(/^service_token_http_([0-9]{3})/);
      const category=http?'SERVICE_TOKEN_HTTP_'+http[1]:
        message.includes('service_account_env_missing')?'SERVICE_ENV_MISSING':
        message.includes('BEGIN PRIVATE KEY')?'KEY_FORMAT_INVALID':
        /sign|DECODER|key|crypto|PEM|ASN1|ASN.1/i.test(message)?'KEY_SIGNING_FAILED':
        /fetch|network|ENOTFOUND|ECONN|ETIMEOUT|ETIMEDOUT/i.test(message)?'NETWORK_FAILURE':'UNKNOWN';
      console.warn('ND_DRIVE_RENDER_SERVICE_ACCOUNT_FAIL category='+category);
      return;
    }
    try{await loadRefresh();console.log(OAUTH_REFRESH_ENV?'ND_DRIVE_RENDER_REFRESH_ENV_PRESENT':'ND_DRIVE_RENDER_ENCRYPTED_ESCROW_PASS');}
    catch{console.warn('ND_DRIVE_RENDER_ENCRYPTED_ESCROW_FAIL');return;}
    try{await userAccessToken();console.log('ND_DRIVE_RENDER_USER_OAUTH_PASS');}
    catch(e){
      const msg=String(e?.message||'');
      const status=(msg.match(/^oauth_refresh_http_([0-9]{3})/)||[])[1]||'UNKNOWN';
      const reasons=['invalid_client','invalid_grant','unauthorized_client','invalid_request','invalid_scope','access_denied'];
      const reason=reasons.find(k=>new RegExp('["\\s:]'+k+'["\\s,}]').test(msg))||'UNKNOWN';
      const descriptionClass=/Token has been expired or revoked/i.test(msg)?'EXPIRED_OR_REVOKED':/Bad Request/i.test(msg)?'BAD_REQUEST':/invalid_client/i.test(msg)?'CLIENT_REJECTED':'OTHER';
      console.warn('ND_DRIVE_RENDER_USER_OAUTH_FAIL status='+status+' reason='+reason+' detail='+descriptionClass);
      return;
    }
    try{await gjson('https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)');console.log('ND_DRIVE_RENDER_GOOGLE_READ_OK'); if(process.env.ND_DRIVE_MCP_CANARY==='20261015')await runMcpLoopbackCanary(); if(process.env.ND_DRIVE_QUALIFY_RUN==='rw-20261015-b')await runRenderRwQualification();}
    catch{console.warn('ND_DRIVE_RENDER_GOOGLE_READ_OR_QUAL_FAILED');}
  });
});
