import http from 'node:http';
import crypto from 'node:crypto';

const PORT = Number(process.env.PORT || 8080);
const PATH_TOKEN = String(process.env.ND_DRIVE_DEVMODE_PATH_TOKEN || '').trim();
const MCP_PATH = '/mcp/' + PATH_TOKEN;
const STATEHEAD = String(process.env.ND_GOOGLE_STATEHEAD_ID || '1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ').trim();
const WRITE_IDS = new Set(
  [process.env.ND_DRIVE_MCP_WRITABLE_FILE_IDS || '', process.env.ND_DRIVE_WRITABLE_FILE_IDS || '']
    .join(',').split(',').map(x => x.trim()).filter(Boolean)
);
const SCOPES = 'https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents';

let tokenCache = null;

function b64u(v) {
  return Buffer.from(v).toString('base64').replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
}

function credential() {
  let email = String(process.env.ND_GOOGLE_CLIENT_EMAIL || '').trim();
  const rawB64 = String(process.env.ND_GOOGLE_PRIVATE_KEY_B64 || '').trim();
  if (!email || !rawB64) throw new Error('google service-account env missing');
  let raw = Buffer.from(rawB64, 'base64').toString('utf8');
  let key = raw;
  try {
    const obj = JSON.parse(raw);
    email = String(obj.client_email || email).trim();
    key = String(obj.private_key || '');
  } catch {}
  key = key.replace(/\\n/g, '\n');
  if (!email || !key.includes('BEGIN PRIVATE KEY')) throw new Error('google service-account material incomplete');
  return { email, key };
}

async function accessToken() {
  const { email, key } = credential();
  const now = Math.floor(Date.now() / 1000);
  if (tokenCache && tokenCache.email === email && tokenCache.exp > now + 90) return tokenCache.token;
  const header = b64u(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const payload = b64u(JSON.stringify({
    iss: email,
    scope: SCOPES,
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3500
  }));
  const unsigned = header + '.' + payload;
  const signature = crypto.sign('RSA-SHA256', Buffer.from(unsigned), key);
  const assertion = unsigned + '.' + b64u(signature);
  const body = new URLSearchParams({
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion
  });
  const res = await fetch('https://oauth2.googleapis.com/token', {
    method:'POST',
    headers:{'content-type':'application/x-www-form-urlencoded'},
    body
  });
  const text = await res.text();
  if (!res.ok) throw new Error('google token HTTP ' + res.status + ': ' + text.slice(0,300));
  const obj = JSON.parse(text || '{}');
  if (!obj.access_token) throw new Error('google access token missing');
  tokenCache = { email, token:obj.access_token, exp:now + Number(obj.expires_in || 3500) };
  return obj.access_token;
}

async function gjson(url, {method='GET', body}={}) {
  const token = await accessToken();
  const headers = { authorization:'Bearer ' + token, accept:'application/json' };
  let payload;
  if (body !== undefined) {
    payload = JSON.stringify(body);
    headers['content-type'] = 'application/json';
  }
  const res = await fetch(url, {method,headers,body:payload});
  const text = await res.text();
  let obj={};
  try { obj = text ? JSON.parse(text) : {}; } catch { obj={raw:text.slice(0,1000)}; }
  if (!res.ok) {
    const e = new Error('google HTTP ' + res.status + ': ' + text.slice(0,1000));
    e.status = res.status;
    throw e;
  }
  return obj;
}

async function gtext(url) {
  const token = await accessToken();
  const res = await fetch(url,{headers:{authorization:'Bearer '+token,accept:'text/plain'}});
  const text = await res.text();
  if (!res.ok) {
    const e=new Error('google HTTP '+res.status+': '+text.slice(0,1000)); e.status=res.status; throw e;
  }
  return text;
}

function collect(elements,out) {
  for (const el of elements || []) {
    for (const pe of el?.paragraph?.elements || []) if (pe?.textRun?.content) out.push(pe.textRun.content);
    for (const row of el?.table?.tableRows || [])
      for (const cell of row?.tableCells || []) collect(cell?.content || [],out);
    if (el?.tableOfContents?.content) collect(el.tableOfContents.content,out);
  }
}
function docText(doc) {
  const out=[];
  const walk=tab=>{
    collect(tab?.documentTab?.body?.content || [],out);
    for (const child of tab?.childTabs || []) walk(child);
  };
  if (Array.isArray(doc.tabs) && doc.tabs.length) for (const tab of doc.tabs) walk(tab);
  else collect(doc?.body?.content || [],out);
  return out.join('');
}
async function docSnapshot(id) {
  const doc=await gjson('https://docs.googleapis.com/v1/documents/'+encodeURIComponent(id)+'?includeTabsContent=true');
  return {document_id:id,title:doc.title,revision_id:doc.revisionId,text:docText(doc)};
}
async function metadata(id) {
  const fields=encodeURIComponent('id,name,mimeType,modifiedTime,createdTime,version,trashed,parents,webViewLink,capabilities(canEdit)');
  return gjson('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?supportsAllDrives=true&fields='+fields);
}
async function batch(id,requests,expectedRevisionId) {
  const body={requests};
  if(expectedRevisionId) body.writeControl={requiredRevisionId:expectedRevisionId};
  try {
    return await gjson('https://docs.googleapis.com/v1/documents/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',body});
  } catch(e) {
    if(expectedRevisionId && (e.status===400 || e.status===409)) throw new Error('REVISION_MISMATCH: '+e.message);
    throw e;
  }
}
function requireWritable(id) {
  if(!WRITE_IDS.has(id)) throw new Error('drive docs write denied');
}
function escQ(s) {
  return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
}
async function driveSearch(args={}) {
  const query=String(args.query || '').trim();
  const top=Math.max(1,Math.min(50,Number(args.top_n || 20)));
  const clauses=["trashed = false"];
  if(query) clauses.push("(name contains '"+escQ(query)+"' or fullText contains '"+escQ(query)+"')");
  if(args.mime_type) clauses.push("mimeType = '"+escQ(String(args.mime_type))+"'");
  if(args.parent_id) clauses.push("'"+escQ(String(args.parent_id))+"' in parents");
  const q=new URLSearchParams({
    q:clauses.join(' and '),
    pageSize:String(top),
    orderBy:'modifiedTime desc',
    spaces:'drive',
    fields:'files(id,name,mimeType,modifiedTime,createdTime,version,parents,webViewLink,capabilities(canEdit))'
  });
  const obj=await gjson('https://www.googleapis.com/drive/v3/files?'+q.toString());
  return {results:(obj.files || []).map(f=>({
    id:f.id,name:f.name,mime_type:f.mimeType,modified_time:f.modifiedTime,created_time:f.createdTime,
    drive_version:f.version,parents:f.parents || [],url:f.webViewLink || null,can_edit:!!f?.capabilities?.canEdit
  }))};
}
async function driveFetch(args={}) {
  const id=String(args.id || args.file_id || args.document_id || '').trim();
  if(!id) throw new Error('id required');
  const m=await metadata(id);
  const meta={id:m.id,name:m.name,mime_type:m.mimeType,modified_time:m.modifiedTime,created_time:m.createdTime,
    drive_version:m.version,parents:m.parents||[],url:m.webViewLink||null,can_edit:!!m?.capabilities?.canEdit};
  if(m.mimeType==='application/vnd.google-apps.document') return {metadata:meta,document:await docSnapshot(id)};
  return {metadata:meta,content_note:'Non-Google-Doc content is not hydrated by this backup MCP.'};
}
async function listChildren(args={}) {
  const parent=String(args.folder_id || args.parent_id || '').trim();
  if(!parent) throw new Error('folder_id required');
  return driveSearch({query:'',top_n:args.top_n || 50,parent_id:parent});
}
async function currentness(args={}) {
  const id=String(args.file_id || args.document_id || '').trim();
  if(!id) throw new Error('file_id required');
  const m=await metadata(id);
  const out={file_id:id,name:m.name,mime_type:m.mimeType,drive_version:m.version,modified_time:m.modifiedTime,trashed:!!m.trashed,can_edit:!!m?.capabilities?.canEdit};
  if(m.mimeType==='application/vnd.google-apps.document') out.docs_revision_id=(await docSnapshot(id)).revision_id;
  return out;
}
async function registryHealth() {
  const stateText=await gtext('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(STATEHEAD)+'/export?mimeType=text%2Fplain');
  let state={};
  try { state=JSON.parse(stateText.trim()); } catch { throw new Error('statehead json parse failed'); }
  const regId=String(state?.capability_registry?.canonical_artifact_id || '').trim();
  if(!regId) throw new Error('statehead registry pointer missing');
  const rm=await metadata(regId);
  return {registry_id:regId,registry_access_ok:rm.id===regId && !rm.trashed,registry_can_edit:!!rm?.capabilities?.canEdit};
}

const TOOL_DEFS=[
  {name:'search',description:'Search files and folders accessible to the ND backup Google Drive service account.',inputSchema:{type:'object',properties:{query:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50},mime_type:{type:'string'},parent_id:{type:'string'}},additionalProperties:false}},
  {name:'fetch',description:'Fetch metadata and, for native Google Docs, current text plus revision ID.',inputSchema:{type:'object',properties:{id:{type:'string'}},required:['id'],additionalProperties:false}},
  {name:'drive_list_children',description:'List direct children of an accessible Google Drive folder.',inputSchema:{type:'object',properties:{folder_id:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50}},required:['folder_id'],additionalProperties:false}},
  {name:'drive_get_currentness_token',description:'Read provider currentness metadata and Docs revision for a file.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'docs_read',description:'Read current text and revision ID from an accessible native Google Doc.',inputSchema:{type:'object',properties:{document_id:{type:'string'}},required:['document_id'],additionalProperties:false}},
  {name:'docs_append',description:'Append text to an allowlisted Google Doc with optional required revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},text:{type:'string'},expected_revision_id:{type:'string'}},required:['document_id','text'],additionalProperties:false}},
  {name:'docs_replace_exact',description:'Replace exactly one matching text occurrence in an allowlisted Google Doc with optional required revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},old_text:{type:'string'},new_text:{type:'string'},expected_revision_id:{type:'string'}},required:['document_id','old_text','new_text'],additionalProperties:false}}
];

async function invoke(name,args={}) {
  if(name==='search') return driveSearch(args);
  if(name==='fetch') return driveFetch(args);
  if(name==='drive_list_children') return listChildren(args);
  if(name==='drive_get_currentness_token') return currentness(args);
  if(name==='docs_read') return docSnapshot(String(args.document_id || '').trim());
  if(name==='docs_append') {
    const id=String(args.document_id || '').trim(); requireWritable(id);
    const before=await docSnapshot(id);
    const expected=String(args.expected_revision_id || before.revision_id || '');
    await batch(id,[{insertText:{endOfSegmentLocation:{},text:String(args.text || '')}}],expected);
    const after=await docSnapshot(id);
    return {document_id:id,before_revision_id:before.revision_id,after_revision_id:after.revision_id,text_length:after.text.length};
  }
  if(name==='docs_replace_exact') {
    const id=String(args.document_id || '').trim(); requireWritable(id);
    const oldText=String(args.old_text || ''), newText=String(args.new_text || '');
    if(!oldText) throw new Error('old_text required');
    const before=await docSnapshot(id);
    const count=before.text.split(oldText).length-1;
    if(count!==1) throw new Error('EXACT_MATCH_REQUIRED: found '+count+' occurrences');
    const expected=String(args.expected_revision_id || before.revision_id || '');
    const result=await batch(id,[{replaceAllText:{containsText:{text:oldText,matchCase:true},replaceText:newText}}],expected);
    const after=await docSnapshot(id);
    return {document_id:id,occurrences_changed:result?.replies?.[0]?.replaceAllText?.occurrencesChanged ?? null,before_revision_id:before.revision_id,after_revision_id:after.revision_id};
  }
  throw new Error('tool_not_allowed');
}

function sendJson(res,status,obj) {
  const raw=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{'content-type':'application/json','content-length':raw.length,'cache-control':'no-store'});
  res.end(raw);
}
function rpcResult(id,result){return {jsonrpc:'2.0',id,result};}
function rpcError(id,code,message,data){return {jsonrpc:'2.0',id,error:{code,message,...(data?{data}:{})}};}
async function readJson(req) {
  const chunks=[]; for await (const c of req) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}
async function handleRpc(msg) {
  const id=msg?.id ?? null, method=String(msg?.method || '');
  if(method==='initialize') {
    return rpcResult(id,{
      protocolVersion:String(msg?.params?.protocolVersion || '2025-06-18'),
      capabilities:{tools:{listChanged:false}},
      serverInfo:{name:'ND Drive Backup',version:'1.0.0'},
      instructions:'Backup access to the same authoritative Nameless Dhamma Google Drive corpus. Use search/fetch for reads and revision-guarded Docs tools for allowlisted writes. Do not treat this server as a second corpus.'
    });
  }
  if(method==='ping') return rpcResult(id,{});
  if(method==='tools/list') return rpcResult(id,{tools:TOOL_DEFS});
  if(method==='tools/call') {
    const name=String(msg?.params?.name || '');
    try {
      const result=await invoke(name,msg?.params?.arguments || {});
      return rpcResult(id,{content:[{type:'text',text:JSON.stringify(result)}],structuredContent:result,isError:false});
    } catch(e) {
      const text=String(e?.message || e);
      return rpcResult(id,{content:[{type:'text',text}],structuredContent:{ok:false,error:text},isError:true});
    }
  }
  if(method.startsWith('notifications/')) return null;
  return rpcError(id,-32601,'Method not found');
}

const server=http.createServer(async(req,res)=>{
  if(req.method==='GET' && req.url==='/health') {
    try {
      const s=await currentness({file_id:STATEHEAD});
      const reg=await registryHealth();
      const ok=s.file_id===STATEHEAD && !!s.docs_revision_id && !!s.can_edit && reg.registry_access_ok;
      return sendJson(res,ok?200:503,{ok,service:'nd-drive-developer-mcp',transport:'mcp-streamable-http',statehead_id:STATEHEAD,drive_version:s.drive_version,docs_revision_present:!!s.docs_revision_id,can_edit:!!s.can_edit,writable_file_count:WRITE_IDS.size,...reg});
    } catch(e) {
      return sendJson(res,503,{ok:false,service:'nd-drive-developer-mcp',error:String(e?.message||e).slice(0,600)});
    }
  }
  if(!PATH_TOKEN || req.url!==MCP_PATH) return sendJson(res,404,{ok:false,error:'not_found'});
  if(req.method==='GET') {
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});
    res.write(': nd-drive-developer-mcp\n\n');
    return res.end();
  }
  if(req.method!=='POST') return sendJson(res,405,{ok:false,error:'method_not_allowed'});
  let msg;
  try { msg=await readJson(req); } catch { return sendJson(res,400,rpcError(null,-32700,'Parse error')); }
  try {
    const out=await handleRpc(msg);
    if(out===null){res.writeHead(202,{'cache-control':'no-store'});return res.end();}
    return sendJson(res,200,out);
  } catch(e) {
    return sendJson(res,200,rpcError(msg?.id ?? null,-32603,'Internal error',{detail:String(e?.message||e).slice(0,800)}));
  }
});

server.listen(PORT,'0.0.0.0',()=>{
  console.log(JSON.stringify({event:'ND_DRIVE_DEVMODE_MCP_READY',port:PORT,mcp_path_configured:!!PATH_TOKEN,writable_file_count:WRITE_IDS.size}));
});
