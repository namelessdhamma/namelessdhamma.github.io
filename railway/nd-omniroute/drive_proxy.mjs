import http from 'node:http';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';

const OUTER_PORT = Number(process.env.PORT || 20128);
const INNER_PORT = Number(process.env.ND_OMNIROUTE_INNER_PORT || 18080);
const BRIDGE_KEY = String(process.env.ND_DRIVE_BRIDGE_TOKEN || '').trim();
const DEVMODE_TOKEN = String(process.env.ND_DRIVE_DEVMODE_PATH_TOKEN || '').trim();
const DEVMODE_MCP_PATH = '/mcp/' + DEVMODE_TOKEN;
const STATEHEAD = String(process.env.ND_GOOGLE_STATEHEAD_ID || '1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ').trim();
const WRITE_IDS = new Set(
  [process.env.ND_DRIVE_MCP_WRITABLE_FILE_IDS || '', process.env.ND_DRIVE_WRITABLE_FILE_IDS || '']
    .join(',').split(',').map(x => x.trim()).filter(Boolean)
);
const SCOPES = 'https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents';

let tokenCache = null;
let childReady = false;

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
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body
  });
  const text = await res.text();
  if (!res.ok) throw new Error('google token HTTP ' + res.status);
  const obj = JSON.parse(text);
  if (!obj.access_token) throw new Error('google access token missing');
  tokenCache = { email, token: obj.access_token, exp: now + Number(obj.expires_in || 3500) };
  return obj.access_token;
}

async function gjson(url, { method='GET', body }={}) {
  const token = await accessToken();
  const headers = { authorization: 'Bearer ' + token, accept: 'application/json' };
  let payload;
  if (body !== undefined) {
    payload = JSON.stringify(body);
    headers['content-type'] = 'application/json';
  }
  const res = await fetch(url, { method, headers, body: payload });
  const text = await res.text();
  let obj = {};
  try { obj = text ? JSON.parse(text) : {}; } catch { obj = { raw: text.slice(0, 800) }; }
  if (!res.ok) {
    const e = new Error('google HTTP ' + res.status + ': ' + text.slice(0, 800));
    e.status = res.status;
    throw e;
  }
  return obj;
}

function collect(elements, out) {
  for (const el of elements || []) {
    for (const pe of el?.paragraph?.elements || []) if (pe?.textRun?.content) out.push(pe.textRun.content);
    for (const row of el?.table?.tableRows || [])
      for (const cell of row?.tableCells || []) collect(cell?.content || [], out);
    if (el?.tableOfContents?.content) collect(el.tableOfContents.content, out);
  }
}

function docText(doc) {
  const out = [];
  const walk = tab => {
    collect(tab?.documentTab?.body?.content || [], out);
    for (const child of tab?.childTabs || []) walk(child);
  };
  if (Array.isArray(doc.tabs) && doc.tabs.length) for (const tab of doc.tabs) walk(tab);
  else collect(doc?.body?.content || [], out);
  return out.join('');
}

async function docSnapshot(id) {
  const doc = await gjson('https://docs.googleapis.com/v1/documents/' + encodeURIComponent(id) + '?includeTabsContent=true');
  return { document_id:id, title:doc.title, revision_id:doc.revisionId, text:docText(doc) };
}

async function metadata(id) {
  const fields = encodeURIComponent('id,name,mimeType,modifiedTime,version,trashed,md5Checksum,sha1Checksum,sha256Checksum,parents,capabilities(canEdit)');
  return gjson('https://www.googleapis.com/drive/v3/files/' + encodeURIComponent(id) + '?supportsAllDrives=true&fields=' + fields);
}

async function batch(id, requests, expectedRevisionId) {
  const body = { requests };
  if (expectedRevisionId) body.writeControl = { requiredRevisionId: expectedRevisionId };
  try {
    return await gjson('https://docs.googleapis.com/v1/documents/' + encodeURIComponent(id) + ':batchUpdate', { method:'POST', body });
  } catch (e) {
    if (expectedRevisionId && (e.status === 400 || e.status === 409)) throw new Error('REVISION_MISMATCH: ' + e.message);
    throw e;
  }
}

function requireWritable(id) {
  if (!WRITE_IDS.has(id)) throw new Error('drive docs write denied');
}

async function invoke(tool, args={}) {
  if (tool === 'drive_get_metadata' || tool === 'drive_get_currentness_token') {
    const id = String(args.file_id || args.document_id || '').trim();
    if (!id) throw new Error('file_id required');
    const m = await metadata(id);
    const out = {
      file_id:id, name:m.name, mime_type:m.mimeType, drive_version:m.version,
      modified_time:m.modifiedTime, trashed:!!m.trashed,
      can_edit:!!m?.capabilities?.canEdit,
      md5:m.md5Checksum || null, sha1:m.sha1Checksum || null, sha256:m.sha256Checksum || null
    };
    if (tool === 'drive_get_currentness_token' && m.mimeType === 'application/vnd.google-apps.document') {
      out.docs_revision_id = (await docSnapshot(id)).revision_id;
    }
    return out;
  }
  if (tool === 'docs_read') {
    const id = String(args.document_id || '').trim();
    if (!id) throw new Error('document_id required');
    return docSnapshot(id);
  }
  if (tool === 'docs_append') {
    const id = String(args.document_id || '').trim();
    requireWritable(id);
    const before = await docSnapshot(id);
    const expected = String(args.expected_revision_id || before.revision_id || '');
    await batch(id, [{ insertText:{ endOfSegmentLocation:{}, text:String(args.text || '') } }], expected);
    const after = await docSnapshot(id);
    return { document_id:id, before_revision_id:before.revision_id, after_revision_id:after.revision_id, text_length:after.text.length };
  }
  if (tool === 'docs_replace_exact') {
    const id = String(args.document_id || '').trim();
    requireWritable(id);
    const oldText = String(args.old_text || '');
    const newText = String(args.new_text || '');
    const before = await docSnapshot(id);
    const count = before.text.split(oldText).length - 1;
    if (count !== 1) throw new Error('EXACT_MATCH_REQUIRED: found ' + count + ' occurrences');
    const expected = String(args.expected_revision_id || before.revision_id || '');
    const result = await batch(id, [{ replaceAllText:{ containsText:{ text:oldText, matchCase:true }, replaceText:newText } }], expected);
    const after = await docSnapshot(id);
    return {
      document_id:id,
      occurrences_changed:result?.replies?.[0]?.replaceAllText?.occurrencesChanged ?? null,
      before_revision_id:before.revision_id,
      after_revision_id:after.revision_id
    };
  }
  if (tool === 'drive_changes_start_token') {
    return gjson('https://www.googleapis.com/drive/v3/changes/startPageToken?supportsAllDrives=true');
  }
  if (tool === 'drive_changes_list') {
    const pageToken = String(args.page_token || '').trim();
    if (!pageToken) throw new Error('page_token required');
    const pageSize = Math.max(1, Math.min(1000, Number(args.page_size || 100)));
    const q = new URLSearchParams({
      pageToken,
      pageSize:String(pageSize),
      supportsAllDrives:'true',
      includeItemsFromAllDrives:'true',
      fields:'nextPageToken,newStartPageToken,changes(fileId,removed,time,file(id,name,mimeType,modifiedTime,version,trashed))'
    });
    return gjson('https://www.googleapis.com/drive/v3/changes?' + q.toString());
  }
  throw new Error('tool_not_allowed');
}

function escQ(v) {
  return String(v || '').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
}

async function driveSearch(args={}) {
  const query = String(args.query || '').trim();
  const top = Math.max(1, Math.min(50, Number(args.top_n || 20)));
  const clauses = ['trashed = false'];
  if (query) clauses.push("(name contains '" + escQ(query) + "' or fullText contains '" + escQ(query) + "')");
  if (args.mime_type) clauses.push("mimeType = '" + escQ(args.mime_type) + "'");
  if (args.parent_id) clauses.push("'" + escQ(args.parent_id) + "' in parents");
  const q = new URLSearchParams({
    q: clauses.join(' and '),
    pageSize: String(top),
    orderBy: 'modifiedTime desc',
    spaces: 'drive',
    fields: 'files(id,name,mimeType,modifiedTime,createdTime,version,parents,webViewLink,capabilities(canEdit))'
  });
  const obj = await gjson('https://www.googleapis.com/drive/v3/files?' + q.toString());
  return {results:(obj.files || []).map(f => ({
    id:f.id, name:f.name, mime_type:f.mimeType, modified_time:f.modifiedTime,
    created_time:f.createdTime, drive_version:f.version, parents:f.parents || [],
    url:f.webViewLink || null, can_edit:!!f?.capabilities?.canEdit
  }))};
}

async function driveFetch(args={}) {
  const id = String(args.id || args.file_id || args.document_id || '').trim();
  if (!id) throw new Error('id required');
  const m = await metadata(id);
  const meta = {
    id:m.id, name:m.name, mime_type:m.mimeType, modified_time:m.modifiedTime,
    drive_version:m.version, parents:m.parents || [], can_edit:!!m?.capabilities?.canEdit
  };
  if (m.mimeType === 'application/vnd.google-apps.document') {
    return {metadata:meta, document:await docSnapshot(id)};
  }
  return {metadata:meta, content_note:'Non-Google-Doc content is not hydrated by this backup MCP.'};
}

const MCP_TOOLS = [
  {name:'search',description:'Search files and folders accessible to the ND backup Google Drive service account.',inputSchema:{type:'object',properties:{query:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50},mime_type:{type:'string'},parent_id:{type:'string'}},additionalProperties:false}},
  {name:'fetch',description:'Fetch metadata and current text/revision for a native Google Doc.',inputSchema:{type:'object',properties:{id:{type:'string'}},required:['id'],additionalProperties:false}},
  {name:'drive_get_currentness_token',description:'Read provider currentness metadata and Docs revision for a file.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'docs_read',description:'Read current text and revision ID from an accessible native Google Doc.',inputSchema:{type:'object',properties:{document_id:{type:'string'}},required:['document_id'],additionalProperties:false}},
  {name:'docs_append',description:'Append text to an allowlisted Google Doc with revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},text:{type:'string'},expected_revision_id:{type:'string'}},required:['document_id','text'],additionalProperties:false}},
  {name:'docs_replace_exact',description:'Replace exactly one matching text occurrence in an allowlisted Google Doc with revision CAS.',inputSchema:{type:'object',properties:{document_id:{type:'string'},old_text:{type:'string'},new_text:{type:'string'},expected_revision_id:{type:'string'}},required:['document_id','old_text','new_text'],additionalProperties:false}}
];

function rpcResult(id,result){ return {jsonrpc:'2.0',id,result}; }
function rpcError(id,code,message,data){ return {jsonrpc:'2.0',id,error:{code,message,...(data?{data}:{})}}; }

async function handleMcpMessage(msg) {
  const id = msg?.id ?? null;
  const method = String(msg?.method || '');
  if (method === 'initialize') {
    return rpcResult(id,{
      protocolVersion:String(msg?.params?.protocolVersion || '2025-06-18'),
      capabilities:{tools:{listChanged:false}},
      serverInfo:{name:'ND Drive Backup',version:'1.0.0'},
      instructions:'Backup MCP to the same authoritative Nameless Dhamma Google Drive corpus. Reads are service-account scoped; writes are revision-guarded and allowlisted. This is not a second corpus.'
    });
  }
  if (method === 'ping') return rpcResult(id,{});
  if (method === 'tools/list') return rpcResult(id,{tools:MCP_TOOLS});
  if (method === 'tools/call') {
    const name = String(msg?.params?.name || '');
    try {
      let result;
      if (name === 'search') result = await driveSearch(msg?.params?.arguments || {});
      else if (name === 'fetch') result = await driveFetch(msg?.params?.arguments || {});
      else result = await invoke(name,msg?.params?.arguments || {});
      return rpcResult(id,{content:[{type:'text',text:JSON.stringify(result)}],structuredContent:result,isError:false});
    } catch (e) {
      const text = String(e.message || e);
      return rpcResult(id,{content:[{type:'text',text}],structuredContent:{ok:false,error:text},isError:true});
    }
  }
  if (method.startsWith('notifications/')) return null;
  return rpcError(id,-32601,'Method not found');
}

async function handleMcp(req,res) {
  if (!DEVMODE_TOKEN || req.url !== DEVMODE_MCP_PATH) return false;
  if (req.method === 'GET') {
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});
    res.write(': nd-drive-backup\n\n');
    return res.end();
  }
  if (req.method !== 'POST') return json(res,405,{ok:false,error:'method_not_allowed'});
  const chunks=[];
  for await (const chunk of req) chunks.push(chunk);
  let msg;
  try { msg=JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); }
  catch { return json(res,400,rpcError(null,-32700,'Parse error')); }
  const out = await handleMcpMessage(msg);
  if (out === null) { res.writeHead(202,{'cache-control':'no-store'}); return res.end(); }
  return json(res,200,out);
}

function json(res, status, obj) {
  const raw = Buffer.from(JSON.stringify(obj));
  res.writeHead(status, { 'content-type':'application/json', 'content-length':raw.length, 'cache-control':'no-store' });
  res.end(raw);
}

function safeEqual(a,b) {
  const x = Buffer.from(String(a || '')), y = Buffer.from(String(b || ''));
  return x.length === y.length && x.length > 0 && crypto.timingSafeEqual(x,y);
}

async function handleDrive(req,res) {
  if (req.method === 'GET' && req.url === '/drive/health') {
    try {
      const r = await invoke('drive_get_currentness_token', { file_id:STATEHEAD });
      const ok = r.file_id === STATEHEAD && !!r.docs_revision_id && !!r.can_edit;
      return json(res, ok ? 200 : 503, {
        ok, route:'railway_external_direct_google', statehead_id:STATEHEAD,
        drive_version:r.drive_version, docs_revision_present:!!r.docs_revision_id,
        can_edit:!!r.can_edit, writable_file_count:WRITE_IDS.size, child_ready:childReady
      });
    } catch (e) {
      return json(res,503,{ok:false,route:'railway_external_direct_google',error:String(e.message || e).slice(0,500),child_ready:childReady});
    }
  }
  if (req.method === 'POST' && req.url === '/drive/invoke') {
    if (!safeEqual(req.headers['x-nd-bridge-key'], BRIDGE_KEY)) return json(res,401,{ok:false,error:'unauthorized'});
    const chunks = [];
    for await (const c of req) chunks.push(c);
    try {
      const payload = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
      const result = await invoke(String(payload.tool || ''), payload.args || {});
      return json(res,200,{ok:true,tool:payload.tool,result,mutation:['docs_append','docs_replace_exact'].includes(payload.tool)});
    } catch (e) {
      const msg = String(e.message || e);
      const status = /REVISION_MISMATCH|EXACT_MATCH_REQUIRED|write denied/.test(msg) ? 409 : 502;
      return json(res,status,{ok:false,error:msg.slice(0,1200)});
    }
  }
  return false;
}

function proxy(req,res) {
  const pr = http.request({
    hostname:'127.0.0.1', port:INNER_PORT, path:req.url, method:req.method,
    headers:{...req.headers, host:'127.0.0.1:' + INNER_PORT}
  }, rr => { res.writeHead(rr.statusCode || 502, rr.headers); rr.pipe(res); });
  pr.on('error', e => json(res,503,{ok:false,error:'inner_unavailable',detail:String(e.message || e).slice(0,300)}));
  req.pipe(pr);
}

const childEnv = {...process.env, PORT:String(INNER_PORT)};
const child = spawn('sh',['./start.sh'],{env:childEnv,stdio:['ignore','inherit','inherit']});
child.on('spawn',()=>{ childReady=true; console.log(JSON.stringify({event:'ND_OMNIROUTE_CHILD_SPAWNED',inner_port:INNER_PORT})); });
child.on('exit',(code,signal)=>{ childReady=false; console.error(JSON.stringify({event:'ND_OMNIROUTE_CHILD_EXIT',code,signal})); });

const server = http.createServer(async (req,res) => {
  if (DEVMODE_TOKEN && req.url === DEVMODE_MCP_PATH) {
    const handled = await handleMcp(req,res);
    if (handled !== false) return;
  }
  if (req.url?.startsWith('/drive/')) {
    const handled = await handleDrive(req,res);
    if (handled !== false) return;
  }
  return proxy(req,res);
});

server.listen(OUTER_PORT,'0.0.0.0',()=>{
  console.log(JSON.stringify({event:'ND_DRIVE_PROXY_READY',outer_port:OUTER_PORT,inner_port:INNER_PORT,writable_file_count:WRITE_IDS.size,devmode_mcp_configured:!!DEVMODE_TOKEN}));
});
