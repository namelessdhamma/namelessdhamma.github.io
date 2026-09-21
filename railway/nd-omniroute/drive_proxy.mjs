import http from 'node:http';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';

const OUTER_PORT = Number(process.env.PORT || 20128);
const INNER_PORT = Number(process.env.ND_OMNIROUTE_INNER_PORT || 18080);
const BRIDGE_KEY = String(process.env.ND_DRIVE_BRIDGE_TOKEN || '').trim();
const DEVMODE_TOKEN = String(process.env.ND_DRIVE_DEVMODE_PATH_TOKEN || '').trim();
const DEVMODE_MCP_PATH = '/mcp/' + DEVMODE_TOKEN;
const DEVMODE_FULL_WRITE = String(process.env.ND_DRIVE_DEVMODE_FULL_WRITE || 'false').trim().toLowerCase() === 'true';
const STATEHEAD = String(process.env.ND_GOOGLE_STATEHEAD_ID || '1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ').trim();
const WRITE_IDS = new Set(
  [process.env.ND_DRIVE_MCP_WRITABLE_FILE_IDS || '', process.env.ND_DRIVE_WRITABLE_FILE_IDS || '']
    .join(',').split(',').map(x => x.trim()).filter(Boolean)
);
const SCOPES = 'https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/presentations';

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
  const fields = encodeURIComponent('id,name,mimeType,size,createdTime,modifiedTime,version,trashed,md5Checksum,sha1Checksum,sha256Checksum,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive,canAddChildren)');
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

async function requireMcpWritable(id) {
  const m = await metadata(id);
  if (DEVMODE_FULL_WRITE) {
    if (!m?.capabilities?.canEdit || m.trashed) throw new Error('drive write denied: service account cannot edit target');
    return m;
  }
  requireWritable(id);
  return m;
}

async function requireMcpParent(parentId) {
  const m = await metadata(parentId);
  if (m.mimeType !== 'application/vnd.google-apps.folder') throw new Error('parent_id is not a folder');
  if (DEVMODE_FULL_WRITE) {
    if (!m?.capabilities?.canAddChildren && !m?.capabilities?.canEdit) throw new Error('drive create denied: service account cannot add children');
    return m;
  }
  if (!WRITE_IDS.has(parentId)) throw new Error('drive create denied: parent not allowlisted');
  return m;
}

async function gbytes(url,{method='GET',body,headers={}}={}) {
  const token=await accessToken();
  const h={authorization:'Bearer '+token,...headers};
  const res=await fetch(url,{method,headers:h,body});
  const buf=Buffer.from(await res.arrayBuffer());
  if(!res.ok){
    const e=new Error('google HTTP '+res.status+': '+buf.toString('utf8',0,Math.min(buf.length,800)));
    e.status=res.status; throw e;
  }
  return {buffer:buf,headers:res.headers,status:res.status};
}

async function driveCreateMetadata(name,mimeType,parentId) {
  if (parentId) await requireMcpParent(parentId);
  const body={name:String(name||'').trim(),mimeType:String(mimeType||'').trim()};
  if(!body.name || !body.mimeType) throw new Error('name and mime_type required');
  if(parentId) body.parents=[parentId];
  return gjson('https://www.googleapis.com/drive/v3/files?supportsAllDrives=true&fields=id,name,mimeType,size,createdTime,modifiedTime,version,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive,canAddChildren)',{method:'POST',body});
}

async function multipartCreate(name,mimeType,parentId,content) {
  if (parentId) await requireMcpParent(parentId);
  const token=await accessToken();
  const boundary='nd-'+crypto.randomBytes(12).toString('hex');
  const meta={name:String(name||'').trim()};
  if(!meta.name) throw new Error('name required');
  if(parentId) meta.parents=[parentId];
  const head=Buffer.from('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+JSON.stringify(meta)+'\r\n--'+boundary+'\r\nContent-Type: '+mimeType+'\r\n\r\n');
  const tail=Buffer.from('\r\n--'+boundary+'--\r\n');
  const body=Buffer.concat([head,content,tail]);
  const res=await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,mimeType,size,createdTime,modifiedTime,version,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive)',{
    method:'POST',headers:{authorization:'Bearer '+token,'content-type':'multipart/related; boundary='+boundary},body
  });
  const txt=await res.text();
  if(!res.ok){const e=new Error('google HTTP '+res.status+': '+txt.slice(0,800));e.status=res.status;throw e;}
  return JSON.parse(txt||'{}');
}

async function driveReadContent(args={}) {
  const id=String(args.file_id||args.id||'').trim();
  if(!id) throw new Error('file_id required');
  const m=await metadata(id);
  if(String(m.mimeType||'').startsWith('application/vnd.google-apps.')) throw new Error('native Google file: use Docs/Sheets/Slides tools');
  const start=Math.max(0,Number(args.start_byte||0));
  const max=Math.max(1,Math.min(4*1024*1024,Number(args.max_bytes||1024*1024)));
  const {buffer,headers}=await gbytes('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?alt=media&supportsAllDrives=true',{
    headers:{Range:'bytes='+start+'-'+(start+max-1)}
  });
  const mode=String(args.encoding||'auto').toLowerCase();
  const textual=/^(text\/|application\/(json|xml|javascript|x-javascript|yaml|x-yaml|csv))/.test(String(m.mimeType||''));
  const encoding=mode==='auto'?(textual?'utf8':'base64'):mode;
  const content=encoding==='utf8'?buffer.toString('utf8'):buffer.toString('base64');
  const cr=headers.get('content-range')||null;
  return {file_id:id,name:m.name,mime_type:m.mimeType,drive_version:m.version,start_byte:start,bytes_returned:buffer.length,content_range:cr,encoding,content};
}

async function driveReplaceContent(args={}) {
  const id=String(args.file_id||'').trim();
  if(!id) throw new Error('file_id required');
  const before=await requireMcpWritable(id);
  if(String(before.mimeType||'').startsWith('application/vnd.google-apps.')) throw new Error('native Google file: use Docs/Sheets/Slides tools');
  const expected=args.expected_drive_version==null?null:String(args.expected_drive_version);
  if(expected && String(before.version)!==expected) throw new Error('DRIVE_VERSION_MISMATCH: expected '+expected+' got '+before.version);
  const mime=String(args.mime_type||before.mimeType||'application/octet-stream');
  let content;
  if(args.content_base64!=null) content=Buffer.from(String(args.content_base64),'base64');
  else content=Buffer.from(String(args.content_text||''),'utf8');
  const token=await accessToken();
  const res=await fetch('https://www.googleapis.com/upload/drive/v3/files/'+encodeURIComponent(id)+'?uploadType=media&supportsAllDrives=true&fields=id,name,mimeType,size,modifiedTime,version,md5Checksum,sha256Checksum,capabilities(canEdit)',{
    method:'PATCH',headers:{authorization:'Bearer '+token,'content-type':mime},body:content
  });
  const txt=await res.text();
  if(!res.ok){const e=new Error('google HTTP '+res.status+': '+txt.slice(0,800));e.status=res.status;throw e;}
  const after=JSON.parse(txt||'{}');
  return {file_id:id,before_drive_version:before.version,after_drive_version:after.version,size:after.size||null,md5:after.md5Checksum||null,sha256:after.sha256Checksum||null};
}

async function driveUpdateMetadata(args={}) {
  const id=String(args.file_id||'').trim();
  if(!id) throw new Error('file_id required');
  const before=await requireMcpWritable(id);
  const expected=args.expected_drive_version==null?null:String(args.expected_drive_version);
  if(expected && String(before.version)!==expected) throw new Error('DRIVE_VERSION_MISMATCH: expected '+expected+' got '+before.version);
  const params=new URLSearchParams({supportsAllDrives:'true',fields:'id,name,mimeType,size,createdTime,modifiedTime,version,trashed,parents,driveId,webViewLink,capabilities(canEdit,canDelete,canTrash,canMoveItemWithinDrive)'});
  const body={};
  if(args.name!=null) body.name=String(args.name);
  if(args.trashed!=null) body.trashed=!!args.trashed;
  if(args.add_parent_id){
    await requireMcpParent(String(args.add_parent_id));
    params.set('addParents',String(args.add_parent_id));
  }
  if(args.remove_parent_id) params.set('removeParents',String(args.remove_parent_id));
  const after=await gjson('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?'+params.toString(),{method:'PATCH',body});
  return {before_drive_version:before.version,file:after};
}

async function driveDelete(args={}) {
  const id=String(args.file_id||'').trim();
  if(!id) throw new Error('file_id required');
  const before=await requireMcpWritable(id);
  if(!before?.capabilities?.canDelete) throw new Error('drive delete denied by provider capability');
  await gjson('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?supportsAllDrives=true',{method:'DELETE'});
  return {file_id:id,deleted:true};
}

async function spreadsheetGet(id) {
  return gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'?includeGridData=false');
}

async function sheetsGetValues(args={}) {
  const id=String(args.spreadsheet_id||'').trim(), range=String(args.range||'').trim();
  if(!id||!range) throw new Error('spreadsheet_id and range required');
  return gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values/'+encodeURIComponent(range)+'?majorDimension=ROWS');
}

async function sheetsUpdateValues(args={}) {
  const id=String(args.spreadsheet_id||'').trim(), range=String(args.range||'').trim();
  if(!id||!range||!Array.isArray(args.values)) throw new Error('spreadsheet_id, range, values required');
  const before=await requireMcpWritable(id);
  const expected=args.expected_drive_version==null?null:String(args.expected_drive_version);
  if(expected && String(before.version)!==expected) throw new Error('DRIVE_VERSION_MISMATCH: expected '+expected+' got '+before.version);
  const q=new URLSearchParams({valueInputOption:String(args.value_input_option||'USER_ENTERED'),includeValuesInResponse:'true'});
  const result=await gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values/'+encodeURIComponent(range)+'?'+q.toString(),{
    method:'PUT',body:{range,majorDimension:'ROWS',values:args.values}
  });
  const after=await metadata(id);
  const readback=await sheetsGetValues({spreadsheet_id:id,range});
  return {before_drive_version:before.version,after_drive_version:after.version,update:result,readback};
}

async function sheetsBatchUpdate(args={}) {
  const id=String(args.spreadsheet_id||'').trim();
  if(!id||!Array.isArray(args.requests)) throw new Error('spreadsheet_id and requests required');
  const before=await requireMcpWritable(id);
  const expected=args.expected_drive_version==null?null:String(args.expected_drive_version);
  if(expected && String(before.version)!==expected) throw new Error('DRIVE_VERSION_MISMATCH: expected '+expected+' got '+before.version);
  const result=await gjson('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',body:{requests:args.requests,includeSpreadsheetInResponse:!!args.include_spreadsheet_in_response}});
  const after=await metadata(id);
  return {before_drive_version:before.version,after_drive_version:after.version,result};
}

async function presentationGet(id) {
  return gjson('https://slides.googleapis.com/v1/presentations/'+encodeURIComponent(id));
}

function presentationText(p) {
  const slides=[];
  for(const [i,s] of (p.slides||[]).entries()){
    const chunks=[];
    for(const el of s.pageElements||[]){
      for(const te of el?.shape?.text?.textElements||[]) if(te?.textRun?.content) chunks.push(te.textRun.content);
      for(const row of el?.table?.tableRows||[]) for(const cell of row.tableCells||[]) for(const te of cell?.text?.textElements||[]) if(te?.textRun?.content) chunks.push(te.textRun.content);
    }
    slides.push({index:i,object_id:s.objectId,text:chunks.join('')});
  }
  return slides;
}

async function slidesBatchUpdate(args={}) {
  const id=String(args.presentation_id||'').trim();
  if(!id||!Array.isArray(args.requests)) throw new Error('presentation_id and requests required');
  const before=await requireMcpWritable(id);
  const expected=args.expected_drive_version==null?null:String(args.expected_drive_version);
  if(expected && String(before.version)!==expected) throw new Error('DRIVE_VERSION_MISMATCH: expected '+expected+' got '+before.version);
  const result=await gjson('https://slides.googleapis.com/v1/presentations/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',body:{requests:args.requests}});
  const after=await metadata(id);
  return {before_drive_version:before.version,after_drive_version:after.version,result};
}

async function mcpInvoke(tool,args={}) {
  if(tool==='search') return driveSearch(args);
  if(tool==='fetch') return driveFetch(args);
  if(tool==='drive_get_metadata' || tool==='drive_get_currentness_token') return invoke(tool,args);
  if(tool==='drive_read_content') return driveReadContent(args);
  if(tool==='drive_list_children') return driveSearch({query:'',top_n:args.top_n||50,parent_id:String(args.folder_id||'')});
  if(tool==='drive_create_folder') return driveCreateMetadata(args.name,'application/vnd.google-apps.folder',String(args.parent_id||'')||null);
  if(tool==='drive_create_native_file'){
    const kind=String(args.kind||'').toLowerCase();
    const map={document:'application/vnd.google-apps.document',spreadsheet:'application/vnd.google-apps.spreadsheet',presentation:'application/vnd.google-apps.presentation'};
    if(!map[kind]) throw new Error('kind must be document, spreadsheet, or presentation');
    return driveCreateMetadata(args.name,map[kind],String(args.parent_id||'')||null);
  }
  if(tool==='drive_create_raw_file'){
    const mime=String(args.mime_type||'application/octet-stream');
    const content=args.content_base64!=null?Buffer.from(String(args.content_base64),'base64'):Buffer.from(String(args.content_text||''),'utf8');
    return multipartCreate(args.name,mime,String(args.parent_id||'')||null,content);
  }
  if(tool==='drive_replace_content') return driveReplaceContent(args);
  if(tool==='drive_update_metadata') return driveUpdateMetadata(args);
  if(tool==='drive_delete_file') return driveDelete(args);
  if(tool==='docs_read') return docSnapshot(String(args.document_id||'').trim());
  if(tool==='docs_append'){
    const id=String(args.document_id||'').trim(); await requireMcpWritable(id);
    const before=await docSnapshot(id); const expected=String(args.expected_revision_id||before.revision_id||'');
    await batch(id,[{insertText:{endOfSegmentLocation:{},text:String(args.text||'')}}],expected);
    const after=await docSnapshot(id);
    return {document_id:id,before_revision_id:before.revision_id,after_revision_id:after.revision_id,text_length:after.text.length};
  }
  if(tool==='docs_replace_exact'){
    const id=String(args.document_id||'').trim(); await requireMcpWritable(id);
    const before=await docSnapshot(id), oldText=String(args.old_text||''), newText=String(args.new_text||'');
    const count=before.text.split(oldText).length-1; if(count!==1) throw new Error('EXACT_MATCH_REQUIRED: found '+count+' occurrences');
    const expected=String(args.expected_revision_id||before.revision_id||'');
    const result=await batch(id,[{replaceAllText:{containsText:{text:oldText,matchCase:true},replaceText:newText}}],expected);
    const after=await docSnapshot(id);
    return {document_id:id,occurrences_changed:result?.replies?.[0]?.replaceAllText?.occurrencesChanged??null,before_revision_id:before.revision_id,after_revision_id:after.revision_id};
  }
  if(tool==='docs_batch_update'){
    const id=String(args.document_id||'').trim(); await requireMcpWritable(id);
    const before=await docSnapshot(id); const expected=String(args.expected_revision_id||before.revision_id||'');
    const result=await batch(id,args.requests||[],expected); const after=await docSnapshot(id);
    return {before_revision_id:before.revision_id,after_revision_id:after.revision_id,result};
  }
  if(tool==='sheets_get') return spreadsheetGet(String(args.spreadsheet_id||'').trim());
  if(tool==='sheets_get_values') return sheetsGetValues(args);
  if(tool==='sheets_update_values') return sheetsUpdateValues(args);
  if(tool==='sheets_batch_update') return sheetsBatchUpdate(args);
  if(tool==='slides_get'){
    const p=await presentationGet(String(args.presentation_id||'').trim());
    return {presentation_id:p.presentationId,title:p.title,page_size:p.pageSize,slides:presentationText(p),raw:p};
  }
  if(tool==='slides_batch_update') return slidesBatchUpdate(args);
  throw new Error('tool_not_allowed');
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
    id:m.id, name:m.name, mime_type:m.mimeType, size:m.size||null, created_time:m.createdTime,
    modified_time:m.modifiedTime, drive_version:m.version, parents:m.parents || [], drive_id:m.driveId||null,
    url:m.webViewLink||null, trashed:!!m.trashed, can_edit:!!m?.capabilities?.canEdit,
    can_delete:!!m?.capabilities?.canDelete, can_move:!!m?.capabilities?.canMoveItemWithinDrive
  };
  if (m.mimeType === 'application/vnd.google-apps.document') return {metadata:meta, document:await docSnapshot(id)};
  if (m.mimeType === 'application/vnd.google-apps.spreadsheet') return {metadata:meta, spreadsheet:await spreadsheetGet(id)};
  if (m.mimeType === 'application/vnd.google-apps.presentation') {
    const p=await presentationGet(id);
    return {metadata:meta, presentation:{presentation_id:p.presentationId,title:p.title,page_size:p.pageSize,slides:presentationText(p)}};
  }
  if (m.mimeType === 'application/vnd.google-apps.folder') return {metadata:meta, children:await driveSearch({query:'',top_n:args.top_n||50,parent_id:id})};
  return {metadata:meta, content:await driveReadContent({file_id:id,start_byte:0,max_bytes:args.max_bytes||1024*1024,encoding:args.encoding||'auto'})};
}

const MCP_TOOLS = [
  {name:'search',description:'Search files/folders in the service-account accessible Drive corpus.',inputSchema:{type:'object',properties:{query:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50},mime_type:{type:'string'},parent_id:{type:'string'}},additionalProperties:false}},
  {name:'fetch',description:'Universal fetch: Docs text, Sheets metadata, Slides text/structure, folders, or raw-file content.',inputSchema:{type:'object',properties:{id:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50},max_bytes:{type:'integer',minimum:1,maximum:4194304},encoding:{type:'string',enum:['auto','utf8','base64']}},required:['id'],additionalProperties:false}},
  {name:'drive_get_metadata',description:'Read Drive metadata/capabilities for a file or folder.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'drive_get_currentness_token',description:'Read Drive version and Docs revision when applicable.',inputSchema:{type:'object',properties:{file_id:{type:'string'}},required:['file_id'],additionalProperties:false}},
  {name:'drive_read_content',description:'Read raw non-Google-native file bytes in bounded chunks as UTF-8 or base64.',inputSchema:{type:'object',properties:{file_id:{type:'string'},start_byte:{type:'integer',minimum:0},max_bytes:{type:'integer',minimum:1,maximum:4194304},encoding:{type:'string',enum:['auto','utf8','base64']}},required:['file_id'],additionalProperties:false}},
  {name:'drive_list_children',description:'List direct children of a Drive folder.',inputSchema:{type:'object',properties:{folder_id:{type:'string'},top_n:{type:'integer',minimum:1,maximum:50}},required:['folder_id'],additionalProperties:false}},
  {name:'drive_create_folder',description:'Create a folder in a writable service-account-accessible parent.',inputSchema:{type:'object',properties:{name:{type:'string'},parent_id:{type:'string'}},required:['name'],additionalProperties:false}},
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

function rpcResult(id,result){ return {jsonrpc:'2.0',id,result}; }
function rpcError(id,code,message,data){ return {jsonrpc:'2.0',id,error:{code,message,...(data?{data}:{})}}; }

async function handleMcpMessage(msg) {
  const id = msg?.id ?? null;
  const method = String(msg?.method || '');
  if (method === 'initialize') {
    return rpcResult(id,{
      protocolVersion:String(msg?.params?.protocolVersion || '2025-06-18'),
      capabilities:{tools:{listChanged:false}},
      serverInfo:{name:'ND Drive Backup',version:'2.0.0'},
      instructions:'Backup MCP to the same authoritative Nameless Dhamma Google Drive corpus. Full functional Drive/Docs/Sheets/Slides operations are available within the corpus accessible to the service account. Google Docs use provider revision CAS; other writes use Drive-version preconditions plus provider readback when supplied. This is not a second corpus.'
    });
  }
  if (method === 'ping') return rpcResult(id,{});
  if (method === 'tools/list') return rpcResult(id,{tools:MCP_TOOLS});
  if (method === 'tools/call') {
    const name = String(msg?.params?.name || '');
    try {
      const result = await mcpInvoke(name,msg?.params?.arguments || {});
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
  console.log(JSON.stringify({event:'ND_DRIVE_PROXY_READY',outer_port:OUTER_PORT,inner_port:INNER_PORT,writable_file_count:WRITE_IDS.size,devmode_mcp_configured:!!DEVMODE_TOKEN,devmode_full_write:DEVMODE_FULL_WRITE}));
});
