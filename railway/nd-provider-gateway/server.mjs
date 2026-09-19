import http from 'node:http';
import { URL } from 'node:url';
import { inflateRawSync } from 'node:zlib';
import { createHash, createSign } from 'node:crypto';
const PORT=Number(process.env.PORT||5678);
const ND_YOUTUBE_MUX_CODE_REV='youtube-mux-rwq-v3-20260916';
const ND_YANDEX_MUX_CODE_REV='yandex-delete-v3-20260919';
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
const ROUTE=String(process.env.ND_YANDEX_MCP_ROUTE_TOKEN||'').trim();
const YANDEX_MCP_PATH=ROUTE?'/yandex/mcp/'+ROUTE:'';
const API='https://cloud-api.yandex.net/v1/disk';
const GOOGLE_CLIENT_EMAIL=String(process.env.ND_GOOGLE_CLIENT_EMAIL||'').trim();
const GOOGLE_PRIVATE_KEY_B64=String(process.env.ND_GOOGLE_PRIVATE_KEY_B64||'').trim();
const GOOGLE_STATEHEAD_ID=String(process.env.ND_GOOGLE_STATEHEAD_ID||'').trim();
const ADOPTION_ROUTE_TOKEN=String(process.env.ND_ADOPTION_ROUTE_TOKEN||'').trim();
const ADOPTION_PATH=ADOPTION_ROUTE_TOKEN?'/nd/adoption/'+ADOPTION_ROUTE_TOKEN:'';
let googleTokenCache={token:'',exp:0};

function sha256Text(text){return createHash('sha256').update(Buffer.from(String(text),'utf8')).digest('hex');}
function b64url(input){return Buffer.from(input).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function googlePrivateKey(){
  if(!GOOGLE_PRIVATE_KEY_B64)throw new Error('ND_GOOGLE_PRIVATE_KEY_B64 missing');
  return Buffer.from(GOOGLE_PRIVATE_KEY_B64,'base64').toString('utf8');
}
async function googleAccessToken(){
  const now=Math.floor(Date.now()/1000);
  if(googleTokenCache.token && googleTokenCache.exp>now+60)return googleTokenCache.token;
  if(!GOOGLE_CLIENT_EMAIL)throw new Error('ND_GOOGLE_CLIENT_EMAIL missing');
  const header=b64url(JSON.stringify({alg:'RS256',typ:'JWT'}));
  const payload=b64url(JSON.stringify({
    iss:GOOGLE_CLIENT_EMAIL,
    scope:'https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents',
    aud:'https://oauth2.googleapis.com/token',
    iat:now,
    exp:now+3600
  }));
  const unsigned=header+'.'+payload;
  const signer=createSign('RSA-SHA256'); signer.update(unsigned); signer.end();
  const assertion=unsigned+'.'+b64url(signer.sign(googlePrivateKey()));
  const body=new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion});
  const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body});
  const t=await r.text(); if(!r.ok)throw new Error('google_token_http_'+r.status+':'+t.slice(0,500));
  const o=JSON.parse(t); if(!o.access_token)throw new Error('google_access_token_missing');
  googleTokenCache={token:o.access_token,exp:now+Number(o.expires_in||3600)};
  return googleTokenCache.token;
}
async function googleFetch(url,init={}){
  const token=await googleAccessToken();
  const headers={...(init.headers||{}),authorization:'Bearer '+token};
  const r=await fetch(url,{...init,headers});
  const buf=Buffer.from(await r.arrayBuffer());
  if(!r.ok)throw new Error('google_http_'+r.status+':'+buf.toString('utf8').slice(0,1000));
  return {r,buf};
}
async function driveReadText(id){
  const m=await googleFetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?fields=id,name,mimeType,parents,md5Checksum,size,modifiedTime,version');
  const meta=JSON.parse(m.buf.toString('utf8'));
  const d=await googleFetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?alt=media');
  const text=d.buf.toString('utf8');
  return {meta,text,sha256:sha256Text(text),bytes:d.buf.length};
}
async function driveCreateText({name,mimeType='text/plain',parentId,text}){
  if(!name||!parentId)throw new Error('name and parentId required');
  const token=await googleAccessToken();
  const boundary='nd-adoption-'+Date.now().toString(16);
  const meta={name,mimeType,parents:[parentId]};
  const head=Buffer.from('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+JSON.stringify(meta)+'\r\n--'+boundary+'\r\nContent-Type: '+mimeType+'\r\n\r\n');
  const body=Buffer.from(String(text),'utf8');
  const tail=Buffer.from('\r\n--'+boundary+'--\r\n');
  const payload=Buffer.concat([head,body,tail]);
  const r=await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,mimeType,parents,md5Checksum,size,version',{
    method:'POST',
    headers:{authorization:'Bearer '+token,'content-type':'multipart/related; boundary='+boundary,'content-length':String(payload.length)},
    body:payload
  });
  const out=await r.text(); if(!r.ok)throw new Error('drive_create_http_'+r.status+':'+out.slice(0,900));
  return {...JSON.parse(out),sha256:sha256Text(text),bytes:body.length};
}
function docText(doc){
  const out=[];
  for(const el of (doc.body?.content||[])){
    const p=el.paragraph; if(!p)continue;
    for(const e of (p.elements||[])) if(e.textRun?.content) out.push(e.textRun.content);
  }
  return out.join('');
}
async function docsRead(id){
  const g=await googleFetch('https://docs.googleapis.com/v1/documents/'+encodeURIComponent(id));
  const doc=JSON.parse(g.buf.toString('utf8'));
  return {documentId:doc.documentId,title:doc.title,revisionId:doc.revisionId,text:docText(doc)};
}
async function docsReplaceCas({documentId,text,requiredRevisionId}){
  if(!documentId||!requiredRevisionId)throw new Error('documentId and requiredRevisionId required');
  const before=await docsRead(documentId);
  if(before.revisionId!==requiredRevisionId)throw new Error('revision_mismatch');
  const end=Math.max(1,1+before.text.length);
  const requests=[];
  if(before.text.length>1)requests.push({deleteContentRange:{range:{startIndex:1,endIndex:end}}});
  else if(before.text.length===1)requests.push({deleteContentRange:{range:{startIndex:1,endIndex:2}}});
  requests.push({insertText:{location:{index:1},text:String(text)}});
  const g=await googleFetch('https://docs.googleapis.com/v1/documents/'+encodeURIComponent(documentId)+':batchUpdate',{
    method:'POST',
    headers:{'content-type':'application/json; charset=utf-8'},
    body:JSON.stringify({requests,writeControl:{requiredRevisionId}})
  });
  const response=JSON.parse(g.buf.toString('utf8')||'{}');
  const after=await docsRead(documentId);
  return {response,after,sha256:sha256Text(after.text)};
}
async function adoptionDispatch(a={}){
  const op=String(a.op||'');
  if(op==='status')return {ok:true,google_configured:Boolean(GOOGLE_CLIENT_EMAIL&&GOOGLE_PRIVATE_KEY_B64),statehead_id:GOOGLE_STATEHEAD_ID||null};
  if(op==='drive_read_text')return {ok:true,...await driveReadText(String(a.file_id||''))};
  if(op==='drive_create_text')return {ok:true,file:await driveCreateText({name:String(a.name||''),mimeType:String(a.mime_type||'text/plain'),parentId:String(a.parent_id||''),text:String(a.text??'')})};
  if(op==='docs_read')return {ok:true,...await docsRead(String(a.document_id||GOOGLE_STATEHEAD_ID||''))};
  if(op==='docs_replace_cas')return {ok:true,...await docsReplaceCas({documentId:String(a.document_id||GOOGLE_STATEHEAD_ID||''),text:String(a.text??''),requiredRevisionId:String(a.required_revision_id||'')})};
  throw new Error('unknown_adoption_op');
}
function clean(e){let s=String((e&&e.message)||e||'');for(const x of [TOKEN,ROUTE])if(x)s=s.split(x).join('[REDACTED]');return s.slice(0,1200);}
function result(id,r){return {jsonrpc:'2.0',id,result:r};}
function error(id,c,m){return {jsonrpc:'2.0',id,error:{code:c,message:m}};}
const RO={readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:true};
const WR={readOnlyHint:false,destructiveHint:false,idempotentHint:false,openWorldHint:true};
const DEL={readOnlyHint:false,destructiveHint:true,idempotentHint:true,openWorldHint:true};
async function api(endpoint,q={},method='GET'){if(!TOKEN)throw new Error('YANDEX_DISK_TOKEN missing');const u=new URL(API+endpoint);for(const[k,v]of Object.entries(q))if(v!==undefined&&v!==null)u.searchParams.set(k,String(v));const r=await fetch(u,{method,headers:{Authorization:'OAuth '+TOKEN,Accept:'application/json','User-Agent':'nd-yandex-mcp/1.0'}});const t=await r.text();let d={};if(t){try{d=JSON.parse(t);}catch{d={text:t.slice(0,5000)};}}if(!r.ok)throw new Error('Yandex Disk HTTP '+r.status+': '+(d.message||d.description||'request_failed'));return d;}
function yandexTools(){return [
{name:'yandex_status',description:'Verify direct Yandex Disk API access.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:RO},
{name:'yandex_list',description:'List files and folders in a Yandex Disk directory.',inputSchema:{type:'object',properties:{path:{type:'string',default:'disk:/'},limit:{type:'integer',minimum:1,maximum:100,default:50},offset:{type:'integer',minimum:0,default:0}},additionalProperties:false},annotations:RO},
{name:'yandex_stat',description:'Read metadata for one Yandex Disk resource.',inputSchema:{type:'object',properties:{path:{type:'string'}},required:['path'],additionalProperties:false},annotations:RO},
{name:'yandex_read_text',description:'Read a text-like Yandex Disk file. DOCX files are decoded from OOXML and returned as extracted UTF-8 text.',inputSchema:{type:'object',properties:{path:{type:'string'},max_chars:{type:'integer',minimum:1,maximum:100000,default:30000}},required:['path'],additionalProperties:false},annotations:RO},
{name:'yandex_get_download_url',description:'Return a temporary direct download URL for a Yandex Disk file.',inputSchema:{type:'object',properties:{path:{type:'string'}},required:['path'],additionalProperties:false},annotations:RO},
{name:'yandex_write_text',description:'Create or replace a UTF-8 text file.',inputSchema:{type:'object',properties:{path:{type:'string'},text:{type:'string',maxLength:1000000},overwrite:{type:'boolean',default:true}},required:['path','text'],additionalProperties:false},annotations:WR},
{name:'yandex_write_base64',description:'Create or replace a binary file from base64 content.',inputSchema:{type:'object',properties:{path:{type:'string'},base64:{type:'string',maxLength:30000000},content_type:{type:'string',default:'application/octet-stream'},overwrite:{type:'boolean',default:true}},required:['path','base64'],additionalProperties:false},annotations:WR},
{name:'yandex_import_zip_base64',description:'Unpack a standard ZIP archive supplied as base64 and upload its files under a Yandex Disk root path. Supports stored and deflate entries; rejects encrypted/ZIP64/path-traversal archives.',inputSchema:{type:'object',properties:{root_path:{type:'string',default:'disk:/'},zip_base64:{type:'string',maxLength:30000000},overwrite:{type:'boolean',default:true},max_entries:{type:'integer',minimum:1,maximum:500,default:200},max_uncompressed_bytes:{type:'integer',minimum:1,maximum:200000000,default:100000000}},required:['zip_base64'],additionalProperties:false},annotations:WR},
{name:'yandex_mkdir',description:'Create a folder.',inputSchema:{type:'object',properties:{path:{type:'string'}},required:['path'],additionalProperties:false},annotations:WR},
{name:'yandex_copy',description:'Copy a file or folder.',inputSchema:{type:'object',properties:{from_path:{type:'string'},to_path:{type:'string'},overwrite:{type:'boolean',default:false}},required:['from_path','to_path'],additionalProperties:false},annotations:WR},
{name:'yandex_move',description:'Move or rename a file or folder.',inputSchema:{type:'object',properties:{from_path:{type:'string'},to_path:{type:'string'},overwrite:{type:'boolean',default:false}},required:['from_path','to_path'],additionalProperties:false},annotations:WR},
{name:'yandex_delete',description:'Delete a file or folder. By default moves it to Yandex Disk Trash; permanently=true requests permanent deletion. confirm=true is required.',inputSchema:{type:'object',properties:{path:{type:'string'},permanently:{type:'boolean',default:false},confirm:{type:'boolean'}},required:['path','confirm'],additionalProperties:false},annotations:DEL}
];}

async function ensureDir(path){
  const p=String(path||'').replace(/\/+$/,'');
  if(!p||p==='disk:')return;
  try{await api('/resources',{path:p},'PUT');}
  catch(e){if(!String((e&&e.message)||e).includes('HTTP 409'))throw e;}
}
async function uploadBuffer(path,body,overwrite=true,contentType='application/octet-stream'){
  const p=String(path||''); if(!p)throw new Error('path required');
  const d=await api('/resources/upload',{path:p,overwrite:overwrite?'true':'false'});
  if(!d.href)throw new Error('upload href missing');
  const r=await fetch(d.href,{method:'PUT',headers:{'Content-Type':String(contentType||'application/octet-stream')},body});
  if(!r.ok)throw new Error('upload HTTP '+r.status);
  return {ok:true,path:p,bytes:body.length};
}
function safeZipName(name){
  const s=String(name||'').replace(/\\/g,'/').replace(/^\/+/, '');
  const parts=s.split('/').filter(Boolean);
  if(parts.some(x=>x==='.'||x==='..'))throw new Error('unsafe zip path');
  return parts.join('/');
}
function decodeXmlText(s){
  return String(s||'')
    .replace(/&#x([0-9a-fA-F]+);/g,(_,h)=>String.fromCodePoint(parseInt(h,16)))
    .replace(/&#([0-9]+);/g,(_,d)=>String.fromCodePoint(parseInt(d,10)))
    .replace(/&lt;/g,'<')
    .replace(/&gt;/g,'>')
    .replace(/&quot;/g,'"')
    .replace(/&apos;/g,"'")
    .replace(/&amp;/g,'&');
}
function docxTextFromBuffer(buf){
  const entries=unpackZip(buf,5000,100000000);
  const doc=entries.find(e=>e&&!e.isDir&&e.name==='word/document.xml');
  if(!doc||!doc.data)throw new Error('DOCX word/document.xml missing');
  const xml=doc.data.toString('utf8');
  const out=[];
  const re=/<w:t\b[^>]*>([\s\S]*?)<\/w:t>|<w:tab\b[^>]*\/>|<w:br\b[^>]*\/>|<\/w:p>|<\/w:tc>|<\/w:tr>/g;
  let m;
  while((m=re.exec(xml))){
    const token=m[0];
    if(m[1]!==undefined)out.push(decodeXmlText(m[1]));
    else if(/^<w:tab\b/.test(token))out.push('\t');
    else if(/^<w:br\b/.test(token))out.push('\n');
    else if(token==='</w:tc>')out.push('\t');
    else out.push('\n');
  }
  return out.join('')
    .replace(/[ \t]+\n/g,'\n')
    .replace(/\n{3,}/g,'\n\n')
    .trim();
}
function unpackZip(buf,maxEntries,maxBytes){
  if(!Buffer.isBuffer(buf))buf=Buffer.from(buf);
  let eocd=-1; const floor=Math.max(0,buf.length-65557);
  for(let i=buf.length-22;i>=floor;i--){if(buf.readUInt32LE(i)===0x06054b50){eocd=i;break;}}
  if(eocd<0)throw new Error('zip EOCD not found');
  const count=buf.readUInt16LE(eocd+10);
  const cdOffset=buf.readUInt32LE(eocd+16);
  if(count===0xffff||cdOffset===0xffffffff)throw new Error('ZIP64 not supported');
  if(count>maxEntries)throw new Error('zip entry limit exceeded');
  let p=cdOffset,total=0; const out=[];
  for(let i=0;i<count;i++){
    if(p+46>buf.length||buf.readUInt32LE(p)!==0x02014b50)throw new Error('invalid central directory');
    const flags=buf.readUInt16LE(p+8),method=buf.readUInt16LE(p+10);
    const compSize=buf.readUInt32LE(p+20),uncompSize=buf.readUInt32LE(p+24);
    const nameLen=buf.readUInt16LE(p+28),extraLen=buf.readUInt16LE(p+30),commentLen=buf.readUInt16LE(p+32);
    const localOffset=buf.readUInt32LE(p+42);
    if(flags&1)throw new Error('encrypted zip entry not supported');
    if(method!==0&&method!==8)throw new Error('zip compression method '+method+' not supported');
    const rawName=buf.subarray(p+46,p+46+nameLen).toString('utf8');
    const isDir=/\/$/.test(rawName); const name=safeZipName(rawName);
    if(!name){p+=46+nameLen+extraLen+commentLen;continue;}
    if(isDir){out.push({name,isDir:true,data:null,size:0});p+=46+nameLen+extraLen+commentLen;continue;}
    total+=uncompSize; if(total>maxBytes)throw new Error('zip uncompressed byte limit exceeded');
    if(localOffset+30>buf.length||buf.readUInt32LE(localOffset)!==0x04034b50)throw new Error('invalid local zip header');
    const ln=buf.readUInt16LE(localOffset+26),le=buf.readUInt16LE(localOffset+28);
    const dataStart=localOffset+30+ln+le, dataEnd=dataStart+compSize;
    if(dataEnd>buf.length)throw new Error('truncated zip entry');
    const compressed=buf.subarray(dataStart,dataEnd);
    const data=method===0?Buffer.from(compressed):inflateRawSync(compressed);
    if(data.length!==uncompSize)throw new Error('zip size mismatch');
    out.push({name,isDir:false,data,size:data.length});
    p+=46+nameLen+extraLen+commentLen;
  }
  return out;
}
async function ensureParentDirs(fullPath){
  const s=String(fullPath||''); const m=s.match(/^(disk:)(\/.*)?$/);
  if(!m)return;
  const rest=String(m[2]||'').replace(/^\/+/, '');
  const parts=rest.split('/').filter(Boolean); parts.pop();
  let cur='disk:';
  for(const part of parts){cur+=(cur==='disk:'?'/':'/')+part;await ensureDir(cur);}
}

async function yandexCall(name,a={}){
if(name==='yandex_status'){const d=await api('/');return {ok:true,transport:'DIRECT_YANDEX_DISK_API',total_space:d.total_space,used_space:d.used_space,trash_size:d.trash_size,system_folders:d.system_folders};}
if(name==='yandex_list'){const path=String(a.path||'disk:/');const d=await api('/resources',{path,limit:Math.max(1,Math.min(Number(a.limit||50),100)),offset:Math.max(0,Number(a.offset||0))});const e=d._embedded||{};return {ok:true,path,total:e.total,items:(e.items||[]).map(x=>({name:x.name,path:x.path,type:x.type,size:x.size,modified:x.modified,mime_type:x.mime_type}))};}
if(name==='yandex_stat'){const path=String(a.path||'');if(!path)throw new Error('path required');const d=await api('/resources',{path,limit:1});return {ok:true,resource:{name:d.name,path:d.path,type:d.type,size:d.size,created:d.created,modified:d.modified,mime_type:d.mime_type,md5:d.md5,sha256:d.sha256,public_url:d.public_url}};}
if(name==='yandex_get_download_url'){const path=String(a.path||'');if(!path)throw new Error('path required');const d=await api('/resources/download',{path});if(!d.href)throw new Error('download href missing');return {ok:true,path,href:d.href,temporary:true};}
if(name==='yandex_read_text'){const path=String(a.path||'');if(!path)throw new Error('path required');const d=await api('/resources/download',{path});if(!d.href)throw new Error('download href missing');const r=await fetch(d.href);if(!r.ok)throw new Error('download HTTP '+r.status);const body=Buffer.from(await r.arrayBuffer());let text,format='utf8';if(/\.docx$/i.test(path)){text=docxTextFromBuffer(body);format='docx-ooxml';}else{text=body.toString('utf8');}const max=Math.max(1,Math.min(Number(a.max_chars||30000),100000));let truncated=false;if(text.length>max){text=text.slice(0,max);truncated=true;}return {ok:true,path,text,truncated,format,bytes:body.length};}
if(name==='yandex_write_text'){const path=String(a.path||'');if(!path)throw new Error('path required');const d=await api('/resources/upload',{path,overwrite:a.overwrite===false?'false':'true'});if(!d.href)throw new Error('upload href missing');const body=Buffer.from(String(a.text??''),'utf8');const r=await fetch(d.href,{method:'PUT',headers:{'Content-Type':'text/plain; charset=utf-8'},body});if(!r.ok)throw new Error('upload HTTP '+r.status);return {ok:true,path,bytes:body.length};}
if(name==='yandex_write_base64'){const path=String(a.path||'');if(!path)throw new Error('path required');const body=Buffer.from(String(a.base64||''),'base64');if(body.length>22500000)throw new Error('binary payload too large');await ensureParentDirs(path);return await uploadBuffer(path,body,a.overwrite!==false,String(a.content_type||'application/octet-stream'));}
if(name==='yandex_import_zip_base64'){const root=String(a.root_path||'disk:/').replace(/\/+$/,'');const zip=Buffer.from(String(a.zip_base64||''),'base64');if(zip.length>22500000)throw new Error('zip payload too large');const entries=unpackZip(zip,Math.max(1,Math.min(Number(a.max_entries||200),500)),Math.max(1,Math.min(Number(a.max_uncompressed_bytes||100000000),200000000)));await ensureDir(root);const uploaded=[];for(const e of entries){const dest=root+'/'+e.name;if(e.isDir){await ensureDir(dest);continue;}await ensureParentDirs(dest);await uploadBuffer(dest,e.data,a.overwrite!==false,'application/octet-stream');uploaded.push({path:dest,bytes:e.size});}return {ok:true,root_path:root,zip_bytes:zip.length,entries:entries.length,files_uploaded:uploaded.length,uploaded};}
if(name==='yandex_mkdir'){const path=String(a.path||'');if(!path)throw new Error('path required');return {ok:true,response:await api('/resources',{path},'PUT')};}
if(name==='yandex_copy'){const f=String(a.from_path||''),t=String(a.to_path||'');if(!f||!t)throw new Error('from_path and to_path required');return {ok:true,response:await api('/resources/copy',{from:f,path:t,overwrite:a.overwrite?'true':'false'},'POST')};}
if(name==='yandex_move'){const f=String(a.from_path||''),t=String(a.to_path||'');if(!f||!t)throw new Error('from_path and to_path required');return {ok:true,response:await api('/resources/move',{from:f,path:t,overwrite:a.overwrite?'true':'false'},'POST')};}
if(name==='yandex_delete'){const path=String(a.path||'');if(!path)throw new Error('path required');if(a.confirm!==true)throw new Error('confirm_required');const permanently=a.permanently===true;return {ok:true,path,permanently,response:await api('/resources',{path,permanently:permanently?'true':'false'},'DELETE')};}
throw new Error('unknown tool');}
async function yandexDispatch(q){const id=q&&q.id!=null?q.id:null;const m=q&&q.method;const p=(q&&q.params)||{};if(m==='initialize')return [200,result(id,{protocolVersion:p.protocolVersion||'2025-06-18',capabilities:{tools:{listChanged:false}},serverInfo:{name:'ND Yandex Disk',version:'1.0.0'},instructions:'Direct read/write access to Yandex Disk API, including binary upload, ZIP import, and guarded deletion.'})];if(m==='notifications/initialized')return [202,null];if(m==='ping')return [200,result(id,{})];if(m==='tools/list')return [200,result(id,{tools:yandexTools()})];if(m==='tools/call'){try{const d=await yandexCall(p.name,p.arguments||{});return [200,result(id,{content:[{type:'text',text:JSON.stringify(d)}],structuredContent:d,isError:false})];}catch(e){return [200,result(id,{content:[{type:'text',text:clean(e)}],isError:true})];}}return [404,error(id,-32601,'Method not found')];}

const YT_PATH_TOKEN=String(process.env.ND_YOUTUBE_MCP_PATH_TOKEN||"").trim();
const YT_CLIENT_ID=String(process.env.ND_YOUTUBE_CLIENT_ID||"").trim();
const YT_CLIENT_SECRET=String(process.env.ND_YOUTUBE_CLIENT_SECRET||"").trim();
const YT_REFRESH_TOKEN=String(process.env.ND_YOUTUBE_REFRESH_TOKEN||"").trim();
const YT_WRITES=/^(1|true|yes|on)$/i.test(String(process.env.ND_SOCIAL_WRITES_ENABLED||"true"));
const YT_GITHUB_PAT=String(process.env.ND_GITHUB_PAT||"").trim();
const YOUTUBE_MCP_PATH=YT_PATH_TOKEN?"/nd/youtube/mcp/"+YT_PATH_TOKEN:"";

function j(res,status,obj){
  const raw=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{"content-type":"application/json; charset=utf-8","content-length":String(raw.length),"cache-control":"no-store"});
  res.end(raw);
}
function cleanErr(e){
  let s=String(e?.message||e||"error");
  for(const v of [YT_CLIENT_ID,YT_CLIENT_SECRET,YT_REFRESH_TOKEN,YT_PATH_TOKEN,YT_GITHUB_PAT]) if(v)s=s.split(v).join("[REDACTED]");
  return s.slice(0,1800);
}
async function accessToken(){
  if(!YT_CLIENT_ID||!YT_CLIENT_SECRET||!YT_REFRESH_TOKEN)throw new Error("youtube_credentials_missing");
  const body=new URLSearchParams({client_id:YT_CLIENT_ID,client_secret:YT_CLIENT_SECRET,refresh_token:YT_REFRESH_TOKEN,grant_type:"refresh_token"});
  const r=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body});
  const t=await r.text(); if(!r.ok)throw new Error("youtube_token_http_"+r.status+":"+t.slice(0,700));
  const o=JSON.parse(t); if(!o.access_token)throw new Error("youtube_access_token_missing"); return o.access_token;
}
async function yfetch(method,url,body){
  const token=await accessToken();
  const init={method,headers:{authorization:"Bearer "+token,accept:"application/json"}};
  if(body!==undefined){init.headers["content-type"]="application/json; charset=utf-8";init.body=JSON.stringify(body);}
  const r=await fetch(url,init); const t=await r.text();
  if(!r.ok)throw new Error("youtube_http_"+r.status+":"+t.slice(0,1400));
  return t?JSON.parse(t):{ok:true};
}
async function yapi(method,resource,query={},body){
  const clean=String(resource||"").replace(/^\/+/,"");
  if(!clean||clean.includes("..")||clean.includes("://"))throw new Error("invalid_youtube_resource");
  const u=new URL("https://www.googleapis.com/youtube/v3/"+clean);
  for(const [k,v] of Object.entries(query||{})){if(v!==undefined&&v!==null)u.searchParams.set(k,String(v));}
  return await yfetch(method,u.toString(),body);
}
async function channel(){
  const o=await yapi("GET","channels",{part:"id,snippet,statistics,contentDetails,brandingSettings,status",mine:"true",maxResults:"10"});
  const item=o.items?.[0]; if(!item)throw new Error("youtube_authorized_channel_not_found"); return item;
}
async function video(id){
  const o=await yapi("GET","videos",{part:"id,snippet,status,statistics,contentDetails",id});
  const item=o.items?.[0]; if(!item)throw new Error("youtube_video_not_found"); return item;
}
async function uploadFromUrl(a){
  if(!YT_WRITES)throw new Error("youtube_writes_disabled");
  const src=await fetch(String(a.media_url||"")); if(!src.ok)throw new Error("media_fetch_http_"+src.status);
  const len=src.headers.get("content-length"); if(!len)throw new Error("media_content_length_required");
  const ctype=(src.headers.get("content-type")||"application/octet-stream").split(";")[0];
  const token=await accessToken();
  const snippet={title:String(a.title||""),description:String(a.description||""),categoryId:String(a.category_id||"22")};
  if(Array.isArray(a.tags)&&a.tags.length)snippet.tags=a.tags.map(String);
  const status={privacyStatus:String(a.privacy_status||"private"),selfDeclaredMadeForKids:Boolean(a.made_for_kids)};
  if(a.publish_at){status.privacyStatus="private";status.publishAt=String(a.publish_at);}
  const init=await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",{
    method:"POST",
    headers:{authorization:"Bearer "+token,"content-type":"application/json; charset=UTF-8","x-upload-content-type":ctype,"x-upload-content-length":len},
    body:JSON.stringify({snippet,status})
  });
  const initText=await init.text(); if(!init.ok)throw new Error("youtube_upload_init_"+init.status+":"+initText.slice(0,900));
  const loc=init.headers.get("location"); if(!loc)throw new Error("youtube_upload_session_missing");
  const put=await fetch(loc,{method:"PUT",headers:{authorization:"Bearer "+token,"content-type":ctype,"content-length":len},body:src.body,duplex:"half"});
  const out=await put.text(); if(!put.ok)throw new Error("youtube_upload_"+put.status+":"+out.slice(0,1200));
  return JSON.parse(out||"{}");
}
async function thumbnail(a){
  if(!YT_WRITES)throw new Error("youtube_writes_disabled");
  const src=await fetch(String(a.image_url||"")); if(!src.ok)throw new Error("image_fetch_http_"+src.status);
  const buf=Buffer.from(await src.arrayBuffer()); if(buf.length>20*1024*1024)throw new Error("thumbnail_too_large");
  const token=await accessToken(); const u=new URL("https://www.googleapis.com/upload/youtube/v3/thumbnails/set");u.searchParams.set("videoId",String(a.video_id||""));
  const r=await fetch(u,{method:"POST",headers:{authorization:"Bearer "+token,"content-type":src.headers.get("content-type")||"application/octet-stream"},body:buf});
  const t=await r.text();if(!r.ok)throw new Error("youtube_thumbnail_"+r.status+":"+t.slice(0,1000));return JSON.parse(t||"{}");
}
const YT_TOOLS=[
  ["youtube_account","Read authorized channel identity, handle, statistics and uploads playlist",{}],
  ["youtube_list_videos","List videos from the authorized channel uploads playlist",{max_results:{type:"integer"},page_token:{type:"string"}}],
  ["youtube_get_video","Read metadata, status and statistics for one video",{video_id:{type:"string"}}],
  ["youtube_update_video","Update title, description, tags, category, privacy, schedule or made-for-kids status",{video_id:{type:"string"},title:{type:"string"},description:{type:"string"},tags:{type:"array",items:{type:"string"}},category_id:{type:"string"},privacy_status:{type:"string"},publish_at:{type:"string"},made_for_kids:{type:"boolean"}}],
  ["youtube_delete_video","Permanently delete a video; confirm=true required",{video_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_upload_video_from_url","Upload a video from an HTTP(S) URL",{media_url:{type:"string"},title:{type:"string"},description:{type:"string"},privacy_status:{type:"string"},tags:{type:"array",items:{type:"string"}},category_id:{type:"string"},publish_at:{type:"string"},made_for_kids:{type:"boolean"}}],
  ["youtube_set_thumbnail","Set a custom thumbnail from an HTTP(S) URL",{video_id:{type:"string"},image_url:{type:"string"}}],
  ["youtube_list_comments","List comment threads for a video",{video_id:{type:"string"},max_results:{type:"integer"},page_token:{type:"string"}}],
  ["youtube_create_comment","Create a top-level comment",{video_id:{type:"string"},text:{type:"string"}}],
  ["youtube_reply_comment","Reply to a comment",{parent_comment_id:{type:"string"},text:{type:"string"}}],
  ["youtube_delete_comment","Delete a comment; confirm=true required",{comment_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_list_playlists","List playlists owned by the channel",{max_results:{type:"integer"},page_token:{type:"string"}}],
  ["youtube_create_playlist","Create a playlist",{title:{type:"string"},description:{type:"string"},privacy_status:{type:"string"}}],
  ["youtube_delete_playlist","Delete a playlist; confirm=true required",{playlist_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_add_to_playlist","Add a video to a playlist",{playlist_id:{type:"string"},video_id:{type:"string"},position:{type:"integer"}}],
  ["youtube_remove_from_playlist","Remove a playlist item; confirm=true required",{playlist_item_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_analytics","Query YouTube Analytics",{start_date:{type:"string"},end_date:{type:"string"},metrics:{type:"string"},dimensions:{type:"string"},filters:{type:"string"},sort:{type:"string"}}],
  ["youtube_api","Low-level full YouTube Data API v3 access",{method:{type:"string"},resource:{type:"string"},query:{type:"object"},body:{type:"object"},confirm_destructive:{type:"boolean"}}]
].map(([name,description,properties])=>({name,description,inputSchema:{type:"object",properties,additionalProperties:false}}));

async function ytCallTool(name,a={}){
  if(name==="youtube_account"){const x=await channel(),s=x.snippet||{},st=x.statistics||{},cd=x.contentDetails||{};return {ok:true,channel:{id:x.id,title:s.title,customUrl:s.customUrl,description:s.description,subscriberCount:st.subscriberCount,videoCount:st.videoCount,viewCount:st.viewCount,uploadsPlaylist:cd.relatedPlaylists?.uploads}};}
  if(name==="youtube_list_videos"){const x=await channel(),id=x.contentDetails?.relatedPlaylists?.uploads;return {ok:true,result:await yapi("GET","playlistItems",{part:"id,snippet,contentDetails,status",playlistId:id,maxResults:Math.max(1,Math.min(Number(a.max_results||25),50)),...(a.page_token?{pageToken:a.page_token}:{})})};}
  if(name==="youtube_get_video")return {ok:true,result:await video(String(a.video_id||""))};
  if(name==="youtube_update_video"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");const id=String(a.video_id||""),x=await video(id),sn={...(x.snippet||{})},st={...(x.status||{})};if(a.title!==undefined)sn.title=String(a.title);if(a.description!==undefined)sn.description=String(a.description);if(a.tags!==undefined)sn.tags=(a.tags||[]).map(String);if(a.category_id)sn.categoryId=String(a.category_id);if(a.privacy_status)st.privacyStatus=String(a.privacy_status);if(a.publish_at){st.publishAt=String(a.publish_at);st.privacyStatus="private";}if(a.made_for_kids!==undefined)st.selfDeclaredMadeForKids=Boolean(a.made_for_kids);return {ok:true,result:await yapi("PUT","videos",{part:"snippet,status"},{id,snippet:sn,status:st})};}
  if(name==="youtube_delete_video"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","videos",{id:String(a.video_id||"")})};}
  if(name==="youtube_upload_video_from_url")return {ok:true,result:await uploadFromUrl(a)};
  if(name==="youtube_set_thumbnail")return {ok:true,result:await thumbnail(a)};
  if(name==="youtube_list_comments")return {ok:true,result:await yapi("GET","commentThreads",{part:"id,snippet,replies",videoId:String(a.video_id||""),maxResults:Math.max(1,Math.min(Number(a.max_results||50),100)),textFormat:"plainText",...(a.page_token?{pageToken:a.page_token}:{})})};
  if(name==="youtube_create_comment"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");return {ok:true,result:await yapi("POST","commentThreads",{part:"snippet"},{snippet:{videoId:String(a.video_id||""),topLevelComment:{snippet:{textOriginal:String(a.text||"")}}}})};}
  if(name==="youtube_reply_comment"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");return {ok:true,result:await yapi("POST","comments",{part:"snippet"},{snippet:{parentId:String(a.parent_comment_id||""),textOriginal:String(a.text||"")}})};}
  if(name==="youtube_delete_comment"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","comments",{id:String(a.comment_id||"")})};}
  if(name==="youtube_list_playlists")return {ok:true,result:await yapi("GET","playlists",{part:"id,snippet,status,contentDetails",mine:"true",maxResults:Math.max(1,Math.min(Number(a.max_results||50),50)),...(a.page_token?{pageToken:a.page_token}:{})})};
  if(name==="youtube_create_playlist"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");return {ok:true,result:await yapi("POST","playlists",{part:"snippet,status"},{snippet:{title:String(a.title||""),description:String(a.description||"")},status:{privacyStatus:String(a.privacy_status||"private")}})};}
  if(name==="youtube_delete_playlist"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","playlists",{id:String(a.playlist_id||"")})};}
  if(name==="youtube_add_to_playlist"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");const sn={playlistId:String(a.playlist_id||""),resourceId:{kind:"youtube#video",videoId:String(a.video_id||"")}};if(Number(a.position)>=0)sn.position=Number(a.position);return {ok:true,result:await yapi("POST","playlistItems",{part:"snippet"},{snippet:sn})};}
  if(name==="youtube_remove_from_playlist"){if(!YT_WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","playlistItems",{id:String(a.playlist_item_id||"")})};}
  if(name==="youtube_analytics"){const q={ids:"channel==MINE",startDate:String(a.start_date||""),endDate:String(a.end_date||""),metrics:String(a.metrics||"views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost")};for(const k of ["dimensions","filters","sort"])if(a[k])q[k]=String(a[k]);const u=new URL("https://youtubeanalytics.googleapis.com/v2/reports");for(const[k,v]of Object.entries(q))u.searchParams.set(k,v);return {ok:true,result:await yfetch("GET",u.toString())};}
  if(name==="youtube_api"){const m=String(a.method||"GET").toUpperCase();if(!["GET","POST","PUT","PATCH","DELETE"].includes(m))throw new Error("unsupported_http_method");if(m!=="GET"&&!YT_WRITES)throw new Error("youtube_writes_disabled");if(m==="DELETE"&&a.confirm_destructive!==true)throw new Error("confirm_required");return {ok:true,result:await yapi(m,String(a.resource||""),a.query||{},["GET","DELETE"].includes(m)?undefined:(a.body||{}))};}
  throw new Error("unknown_tool");
}

async function readBody(req){const chunks=[];for await(const c of req)chunks.push(c);return chunks.length?Buffer.concat(chunks).toString("utf8"):"";}
async function youtubeMcp(req,res){
  let msg;try{msg=JSON.parse(await readBody(req)||"{}");}catch{return j(res,400,{jsonrpc:"2.0",id:null,error:{code:-32700,message:"parse error"}});}
  const id=msg.id,method=String(msg.method||"");
  if(method==="notifications/initialized"){res.writeHead(204);return res.end();}
  if(method==="initialize")return j(res,200,{jsonrpc:"2.0",id,result:{protocolVersion:"2025-06-18",capabilities:{tools:{}},serverInfo:{name:"nd-youtube-full-mcp",version:"1.0.0"},instructions:"Nameless Dhamma YouTube MCP with full read/write access. Destructive deletes require explicit confirm=true."}});
  if(method==="ping")return j(res,200,{jsonrpc:"2.0",id,result:{}});
  if(method==="tools/list")return j(res,200,{jsonrpc:"2.0",id,result:{tools:YT_TOOLS}});
  if(method==="tools/call"){const p=msg.params||{};try{const out=await ytCallTool(String(p.name||""),p.arguments||{});return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:false}});}catch(e){const out={ok:false,error:cleanErr(e)};return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:true}});}}
  return j(res,200,{jsonrpc:"2.0",id,error:{code:-32601,message:"Method not found"}});
}
async function youtubeHealth(){try{const x=await channel(),s=x.snippet||{},st=x.statistics||{};return {ok:true,service:"nd-youtube-full-mcp",read_write:YT_WRITES,channel:{id:x.id,title:s.title,customUrl:s.customUrl,subscriberCount:st.subscriberCount,videoCount:st.videoCount,viewCount:st.viewCount}};}catch(e){return {ok:false,service:"nd-youtube-full-mcp",error:cleanErr(e)};}}

const YT_QUALIFY_REV=String(process.env.ND_YOUTUBE_QUALIFY_REV||"").trim();
let ytQualification={state:YT_QUALIFY_REV?"pending":"disabled",rev:YT_QUALIFY_REV||null};

async function runYoutubeQualification(){
  if(!YT_QUALIFY_REV)return;
  let playlistId="";
  const title="ND MCP QUALIFICATION "+Date.now();
  try{
    const created=await yapi("POST","playlists",{part:"snippet,status"},{snippet:{title,description:"Temporary private playlist for ND YouTube MCP reversible write qualification."},status:{privacyStatus:"private"}});
    playlistId=String(created?.id||"");
    if(!playlistId)throw new Error("qualification_create_missing_id");
    let item=null;
    for(let attempt=0;attempt<6;attempt++){
      if(attempt)await new Promise(r=>setTimeout(r,1000));
      const readback=await yapi("GET","playlists",{part:"id,snippet,status",id:playlistId});
      item=readback?.items?.[0]||null;
      if(item?.id===playlistId)break;
    }
    if(!item||item.id!==playlistId)throw new Error("qualification_readback_missing_after_retry");
    if(item?.status?.privacyStatus!=="private")throw new Error("qualification_not_private");
    await yapi("DELETE","playlists",{id:playlistId});
    let deleted=false;
    for(let attempt=0;attempt<6;attempt++){
      if(attempt)await new Promise(r=>setTimeout(r,1000));
      const after=await yapi("GET","playlists",{part:"id",id:playlistId});
      if(!(after?.items||[]).length){deleted=true;break;}
    }
    if(!deleted)throw new Error("qualification_delete_readback_failed_after_retry");
    ytQualification={
      state:"pass",
      rev:YT_QUALIFY_REV,
      created_private:true,
      readback:true,
      deleted:true,
      delete_readback:true,
      playlist_id:playlistId,
      title
    };
    console.log("ND_YOUTUBE_REVERSIBLE_WRITE_QUALIFICATION",JSON.stringify(ytQualification));
  }catch(e){
    if(playlistId){
      try{await yapi("DELETE","playlists",{id:playlistId});}catch{}
    }
    ytQualification={state:"fail",rev:YT_QUALIFY_REV,error:cleanErr(e),cleanup_attempted:Boolean(playlistId)};
    console.error("ND_YOUTUBE_REVERSIBLE_WRITE_QUALIFICATION",JSON.stringify(ytQualification));
  }
}




const muxServer=http.createServer(async(req,res)=>{
  try{
    const requestUrl=new URL(req.url||'/','http://local');
    const path=requestUrl.pathname;

    if(path==='/healthz'){
      const body={
        status:'ok',
        service:'ND Yandex + YouTube MCP',
        yandex:{configured:Boolean(TOKEN&&ROUTE),tools:yandexTools().length,code_rev:ND_YANDEX_MUX_CODE_REV},
        youtube:{configured:Boolean(YT_CLIENT_ID&&YT_CLIENT_SECRET&&YT_REFRESH_TOKEN&&YT_PATH_TOKEN),writes:YT_WRITES,tools:YT_TOOLS.length}
      };
      const raw=Buffer.from(JSON.stringify(body));
      res.writeHead(200,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});
      res.end(raw);return;
    }

    if(ADOPTION_PATH && path===ADOPTION_PATH){
      if(req.method==='GET'){
        try{
          const op=String(requestUrl.searchParams.get('op')||'status');
          if(!['status','drive_read_text','docs_read'].includes(op))return j(res,405,{ok:false,error:'read_only_get_op_forbidden'});
          const input={op};
          if(requestUrl.searchParams.get('file_id'))input.file_id=requestUrl.searchParams.get('file_id');
          if(requestUrl.searchParams.get('document_id'))input.document_id=requestUrl.searchParams.get('document_id');
          const out=await adoptionDispatch(input);
          return j(res,200,out);
        }catch(e){return j(res,500,{ok:false,error:cleanErr(e)});}
      }
      if(req.method!=='POST'){res.writeHead(405,{Allow:'GET, POST','content-length':'0'});res.end();return;}
      try{
        const raw=await readBody(req);
        const input=JSON.parse(raw||'{}');
        const out=await adoptionDispatch(input);
        return j(res,200,out);
      }catch(e){
        return j(res,500,{ok:false,error:cleanErr(e)});
      }
    }

    if(path==='/youtube/health'){
      const h=await youtubeHealth();
      return j(res,h.ok?200:503,h);
    }

    if(path==='/youtube/qualification'){
      return j(res,ytQualification.state==="fail"?503:200,{...ytQualification,code_rev:ND_YOUTUBE_MUX_CODE_REV});
    }
    if(path==='/youtube/qualification-v2'){
      return j(res,ytQualification.state==="fail"?503:200,{...ytQualification,code_rev:ND_YOUTUBE_MUX_CODE_REV});
    }


    if(path==='/'){
      const body={
        service:'ND Multiplex MCP Host',
        yandex_mcp_configured:Boolean(YANDEX_MCP_PATH),
        youtube_mcp_configured:Boolean(YOUTUBE_MCP_PATH),
        youtube_read_write:YT_WRITES
      };
      const raw=Buffer.from(JSON.stringify(body));
      res.writeHead(200,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});
      res.end(raw);return;
    }

    if(YOUTUBE_MCP_PATH && path===YOUTUBE_MCP_PATH){
      if(req.method==='GET') return j(res,200,{ok:true,service:'nd-youtube-full-mcp',transport:'streamable-http',methods:['POST'],tools:YT_TOOLS.length});
      if(req.method!=='POST'){res.writeHead(405,{Allow:'POST','content-length':'0'});res.end();return;}
      return await youtubeMcp(req,res);
    }

    if(YANDEX_MCP_PATH && path===YANDEX_MCP_PATH){
      if(req.method!=='POST'){res.writeHead(405,{Allow:'POST','content-length':'0'});res.end();return;}
      try{
        const chunks=[];for await(const c of req)chunks.push(c);
        const input=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');
        const[status,payload]=await yandexDispatch(input);
        if(payload==null){res.writeHead(status,{'content-length':'0'});res.end();return;}
        const raw=Buffer.from(JSON.stringify(payload));
        res.writeHead(status,{'content-type':'application/json; charset=utf-8','content-length':String(raw.length)});
        res.end(raw);return;
      }catch(e){
        const raw=Buffer.from(JSON.stringify(error(null,-32700,clean(e))));
        res.writeHead(400,{'content-type':'application/json','content-length':String(raw.length)});
        res.end(raw);return;
      }
    }

    const raw=Buffer.from(JSON.stringify({error:'not_found'}));
    res.writeHead(404,{'content-type':'application/json','content-length':String(raw.length)});
    res.end(raw);
  }catch(e){
    return j(res,500,{ok:false,error:cleanErr(e)});
  }
});

console.log('ND_YANDEX_YOUTUBE_MUX_START',JSON.stringify({
  port:PORT,
  yandex_configured:Boolean(TOKEN&&ROUTE),
  yandex_tools:yandexTools().length,
  yandex_code_rev:ND_YANDEX_MUX_CODE_REV,
  youtube_configured:Boolean(YT_CLIENT_ID&&YT_CLIENT_SECRET&&YT_REFRESH_TOKEN&&YT_PATH_TOKEN),
  youtube_writes:YT_WRITES,
  youtube_tools:YT_TOOLS.length,
  code_rev:ND_YOUTUBE_MUX_CODE_REV,
  qualification_rev:YT_QUALIFY_REV||null
}));
muxServer.listen(PORT,'0.0.0.0');
setTimeout(runYoutubeQualification,2000);