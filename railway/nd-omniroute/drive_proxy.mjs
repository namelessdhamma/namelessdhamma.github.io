import http from 'node:http';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { AsyncLocalStorage } from 'node:async_hooks';
import { createWanMcpHandler, createStoryboardMcpHandler, wanHealth, ltxHealth, ltxKeyframeSelftest, storyboardHealth, storyboardResultBytes } from './wan_mcp.mjs';

const OUTER_PORT = Number(process.env.PORT || 20128);
const INNER_PORT = Number(process.env.ND_OMNIROUTE_INNER_PORT || 18080);
const WAN_MCP_TOKEN = String(process.env.ND_WAN_MCP_PATH_TOKEN || '').trim();
const WAN_MCP_PATH = '/wan-mcp/' + WAN_MCP_TOKEN;
const LTX_MCP_TOKEN = String(process.env.ND_LTX_MCP_PATH_TOKEN || '').trim();
const LTX_MCP_PATH = '/ltx-mcp/' + LTX_MCP_TOKEN;
const STORYBOARD_MCP_TOKEN = String(process.env.ND_STORYBOARD_MCP_PATH_TOKEN || '').trim();
const STORYBOARD_MCP_PATH = '/storyboard-mcp/' + STORYBOARD_MCP_TOKEN;
const KAGGLE_API_TOKEN = String(process.env.KAGGLE_API_TOKEN || '').trim();
let kaggleSelftestState={state:'NOT_RUN',updated_at:null,username:null,gpu:null,error:null};

function kaggleDurationSeconds(v){
  if(typeof v==='number') return v;
  if(typeof v==='string'){
    const m=v.match(/^(-?\d+(?:\.\d+)?)s$/);
    return m?Number(m[1]):Number(v)||0;
  }
  if(v && typeof v==='object'){
    const s=Number(v.seconds||v.Seconds||0);
    const n=Number(v.nanos||v.Nanos||0);
    return s+n/1e9;
  }
  return 0;
}

async function kaggleRpc(service,method,body={}){
  if(!KAGGLE_API_TOKEN) throw new Error('kaggle_api_token_missing');
  const res=await fetch('https://api.kaggle.com/v1/'+service+'/'+method,{
    method:'POST',
    headers:{
      authorization:'Bearer '+KAGGLE_API_TOKEN,
      accept:'application/json',
      'content-type':'application/json',
      'user-agent':'nd-external-intelligence/1.0'
    },
    body:JSON.stringify(body)
  });
  const text=await res.text();
  let obj={};
  try{obj=text?JSON.parse(text):{};}catch{obj={raw:text.slice(0,500)};}
  if(!res.ok){
    const e=new Error('kaggle HTTP '+res.status+': '+String(obj?.message||obj?.error||text).slice(0,500));
    e.status=res.status;
    throw e;
  }
  return obj;
}

async function kaggleSelftest(){
  kaggleSelftestState={state:'RUNNING',updated_at:new Date().toISOString(),username:null,gpu:null,error:null};
  try{
    const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
    if(!intro?.active || !intro?.username) throw new Error('kaggle_token_inactive_or_username_missing');
    const quota=await kaggleRpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{});
    const g=quota?.gpuQuota||quota?.gpu_quota||null;
    const used=kaggleDurationSeconds(g?.timeUsed??g?.time_used);
    const total=kaggleDurationSeconds(g?.totalTimeAllowed??g?.total_time_allowed);
    kaggleSelftestState={
      state:'PASS',
      updated_at:new Date().toISOString(),
      username:String(intro.username),
      gpu:g?{
        used_hours:Number((used/3600).toFixed(3)),
        total_hours:Number((total/3600).toFixed(3)),
        remaining_hours:Number((Math.max(0,total-used)/3600).toFixed(3)),
        refresh_at:quota?.quotaRefreshTime||quota?.quota_refresh_time||null,
        has_ever_run:g?.hasEverRun??g?.has_ever_run??null
      }:null,
      error:null
    };
  }catch(e){
    kaggleSelftestState={
      state:'FAIL',
      updated_at:new Date().toISOString(),
      username:null,
      gpu:null,
      error:String(e?.message||e).slice(0,700)
    };
  }
  console.log(JSON.stringify({event:'ND_KAGGLE_SELFTEST',...kaggleSelftestState}));
  return kaggleSelftestState;
}


function kaggleStatusTerminal(status){
  const s=String(status??'').toUpperCase();
  return s==='2'||s==='3'||s==='4'||s==='5'||s.includes('COMPLETE')||s.includes('ERROR')||s.includes('CANCEL');
}

async function kaggleGpuProbe(){
  const enabled=String(process.env.ND_KAGGLE_GPU_PROBE_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_gpu_probe_auth_failed');
  const username=String(intro.username);
  const slug='nd-gpu-probe';
  const fullSlug=username+'/'+slug;
  const script=[
    "import json, platform",
    "import torch",
    "gpus=[]",
    "for i in range(torch.cuda.device_count()):",
    "    p=torch.cuda.get_device_properties(i)",
    "    gpus.append({'index':i,'name':torch.cuda.get_device_name(i),'total_memory_bytes':int(p.total_memory),'capability':list(torch.cuda.get_device_capability(i))})",
    "out={'python':platform.python_version(),'torch':torch.__version__,'torch_cuda':torch.version.cuda,'cuda_available':torch.cuda.is_available(),'gpu_count':torch.cuda.device_count(),'gpus':gpus}",
    "print('ND_GPU_PROBE_JSON='+json.dumps(out,sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,
    newTitle:'ND GPU Probe',
    text:script,
    language:'python',
    kernelType:'script',
    datasetDataSources:[],
    kernelDataSources:[],
    competitionDataSources:[],
    categoryIds:[],
    isPrivate:true,
    enableGpu:true,
    enableTpu:false,
    enableInternet:false,
    modelDataSources:[],
    sessionTimeoutSeconds:300,
    machineShape:'NvidiaTeslaT4'
  });
  if(save?.error) throw new Error('kaggle_save_kernel_error: '+String(save.error).slice(0,500));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_save_kernel_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null;
  let failureMessage=null;
  const deadline=Date.now()+4*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
      userName:username,kernelSlug:slug,versionLabel
    });
    lastStatus=st?.status;
    failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,4000));
  }
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_gpu_probe_timeout status='+String(lastStatus));
  const statusText=String(lastStatus??'').toUpperCase();
  if(statusText==='3'||statusText.includes('ERROR')) throw new Error('kaggle_gpu_probe_failed: '+String(failureMessage||lastStatus));
  if(statusText==='4'||statusText==='5'||statusText.includes('CANCEL')) throw new Error('kaggle_gpu_probe_cancelled: '+String(lastStatus));
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:slug,versionLabel,pageSize:20
  });
  const log=String(out?.log||'');
  const marker='ND_GPU_PROBE_JSON=';
  const line=log.split(/\r?\n/).find(x=>x.includes(marker));
  if(!line) throw new Error('kaggle_gpu_probe_marker_missing');
  const payload=JSON.parse(line.slice(line.indexOf(marker)+marker.length));
  const result={
    state:'PASS',
    username,
    ref:fullSlug+'/'+version,
    version,
    provider_url:save?.url||null,
    gpu:payload
  };
  console.log(JSON.stringify({event:'ND_KAGGLE_GPU_PROBE',...result}));
  return result;
}

const wanMcpHandler = createWanMcpHandler();
const storyboardMcpHandler = createStoryboardMcpHandler();
let ltxSelftestState={state:'NOT_RUN',updated_at:null};
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
const USER_OAUTH_CLIENT_ID = String(process.env.ND_DRIVE_USER_OAUTH_CLIENT_ID || '').trim();
const USER_OAUTH_CLIENT_SECRET = String(process.env.ND_DRIVE_USER_OAUTH_CLIENT_SECRET || '').trim();
const USER_OAUTH_REDIRECT_URI = String(process.env.ND_DRIVE_USER_OAUTH_REDIRECT_URI || 'https://nd-notebooklm-remote-mcp.vercel.app/api/social-oauth/youtube/callback').trim();
const USER_OAUTH_STORE_PARENT = String(process.env.ND_DRIVE_USER_OAUTH_STORE_PARENT || '15CrPbHWMK2LqOYhBM05Hn1cmzOYA8dKC').trim();
const USER_OAUTH_STORE_NAME = '.nd-drive-user-oauth.enc.json';
const authContext = new AsyncLocalStorage();

const LINEAR_API_KEY = String(process.env.ND_LINEAR_API_KEY || '').trim();
const LINEAR_OAUTH_CLIENT_ID = String(process.env.ND_LINEAR_OAUTH_CLIENT_ID || '').trim();
const LINEAR_OAUTH_CLIENT_SECRET = String(process.env.ND_LINEAR_OAUTH_CLIENT_SECRET || '').trim();
const LINEAR_OAUTH_SCOPE = String(process.env.ND_LINEAR_OAUTH_SCOPE || 'read,write').trim();
const LINEAR_USER_OAUTH_CLIENT_ID = String(process.env.ND_LINEAR_USER_OAUTH_CLIENT_ID || '').trim();
const LINEAR_USER_OAUTH_REDIRECT_URI = String(process.env.ND_LINEAR_USER_OAUTH_REDIRECT_URI || 'https://nd-external-intelligence-production.up.railway.app/linear/oauth/callback').trim();
const LINEAR_GITHUB_PAT = String(process.env.ND_GITHUB_PAT || '').trim();
const LINEAR_SECRET_REPO = 'namelessdhamma/nameless-dhamma-vault';
const LINEAR_USER_OAUTH_STORE_PATH = '.nd-secrets/linear-user-oauth.enc.json';
const LINEAR_BRIDGE_KEY = String(process.env.ND_LINEAR_BRIDGE_TOKEN || '').trim();
const LINEAR_DEVMODE_TOKEN = String(process.env.ND_LINEAR_DEVMODE_PATH_TOKEN || '').trim();
const LINEAR_DEVMODE_MCP_PATH = '/linear-mcp/' + LINEAR_DEVMODE_TOKEN;
const LINEAR_MCP_URL = 'https://mcp.linear.app/mcp';
const LINEAR_GQL_URL = 'https://api.linear.app/graphql';
const LINEAR_OAUTH_TOKEN_URL = 'https://api.linear.app/oauth/token';
const LINEAR_REQUIRED_DESTRUCTIVE = [
  'issueDelete','documentDelete','projectDelete','initiativeDelete',
  'projectMilestoneDelete','issueLabelDelete','projectLabelDelete',
  'initiativeLabelDelete','releaseDelete','attachmentDelete','commentDelete'
];
let linearSelftestState={last_run:null,ok:null,error:null,auth:'api_key'};
let linearOauthSelftestState={last_run:null,ok:null,error:null,auth:'oauth'};
let linearUserOauthSelftestState={last_run:null,ok:null,error:null,auth:'user_oauth'};
let linearOauthTokenCache=null;
let linearUserOauthTokenCache=null;
let linearUserOauthRefreshCache=null;

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

async function serviceAccessToken() {
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

let userTokenCache = null;
let userRefreshCache = null;

function oauthCryptoKey() {
  const material = String(process.env.ND_DRIVE_BRIDGE_TOKEN || '').trim();
  if (!material) throw new Error('drive oauth encryption key missing');
  return crypto.createHash('sha256').update('nd-drive-user-oauth-v1\0' + material).digest();
}

function encryptRefreshToken(refreshToken) {
  const iv=crypto.randomBytes(12);
  const cipher=crypto.createCipheriv('aes-256-gcm',oauthCryptoKey(),iv);
  const ciphertext=Buffer.concat([cipher.update(String(refreshToken),'utf8'),cipher.final()]);
  return {
    schema:'nd-drive-user-oauth-secret-v1',
    iv:iv.toString('base64'),
    tag:cipher.getAuthTag().toString('base64'),
    ciphertext:ciphertext.toString('base64')
  };
}

function decryptRefreshToken(obj) {
  if (!obj || obj.schema!=='nd-drive-user-oauth-secret-v1') throw new Error('drive oauth secret schema invalid');
  const decipher=crypto.createDecipheriv('aes-256-gcm',oauthCryptoKey(),Buffer.from(obj.iv,'base64'));
  decipher.setAuthTag(Buffer.from(obj.tag,'base64'));
  return Buffer.concat([decipher.update(Buffer.from(obj.ciphertext,'base64')),decipher.final()]).toString('utf8');
}

async function directFetchJsonWithToken(token,url,{method='GET',body,headers={}}={}) {
  const h={authorization:'Bearer '+token,accept:'application/json',...headers};
  let payload=body;
  if (body!==undefined && !Buffer.isBuffer(body) && typeof body!=='string') {
    payload=JSON.stringify(body); h['content-type']='application/json';
  }
  const res=await fetch(url,{method,headers:h,body:payload});
  const text=await res.text();
  let obj={};
  try{obj=text?JSON.parse(text):{};}catch{obj={raw:text.slice(0,800)};}
  if(!res.ok){const e=new Error('google HTTP '+res.status+': '+text.slice(0,800));e.status=res.status;throw e;}
  return obj;
}

async function findOAuthStoreFile(serviceToken) {
  const q=new URLSearchParams({
    q:"name = '"+USER_OAUTH_STORE_NAME.replace(/'/g,"\\'")+"' and '"+USER_OAUTH_STORE_PARENT+"' in parents and trashed = false",
    pageSize:'10',
    spaces:'drive',
    fields:'files(id,name,mimeType,version,parents)'
  });
  const obj=await directFetchJsonWithToken(serviceToken,'https://www.googleapis.com/drive/v3/files?'+q.toString());
  return (obj.files||[])[0]||null;
}

async function loadEncryptedRefreshToken() {
  if (userRefreshCache) return userRefreshCache;
  const serviceToken=await serviceAccessToken();
  const file=await findOAuthStoreFile(serviceToken);
  if(!file) throw new Error('drive user oauth not authorized');
  const res=await fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(file.id)+'?alt=media&supportsAllDrives=true',{
    headers:{authorization:'Bearer '+serviceToken,accept:'application/json'}
  });
  const text=await res.text();
  if(!res.ok) throw new Error('drive oauth secret read HTTP '+res.status);
  userRefreshCache=decryptRefreshToken(JSON.parse(text));
  return userRefreshCache;
}

async function userAccessToken() {
  if(!USER_OAUTH_CLIENT_ID || !USER_OAUTH_CLIENT_SECRET) throw new Error('drive user oauth client missing');
  const now=Math.floor(Date.now()/1000);
  if(userTokenCache && userTokenCache.exp>now+90) return userTokenCache.token;
  const refresh=await loadEncryptedRefreshToken();
  const body=new URLSearchParams({
    client_id:USER_OAUTH_CLIENT_ID,
    client_secret:USER_OAUTH_CLIENT_SECRET,
    refresh_token:refresh,
    grant_type:'refresh_token'
  });
  const res=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body});
  const text=await res.text();
  if(!res.ok) throw new Error('drive user oauth refresh HTTP '+res.status+': '+text.slice(0,500));
  const obj=JSON.parse(text||'{}');
  if(!obj.access_token) throw new Error('drive user oauth access token missing');
  userTokenCache={token:obj.access_token,exp:now+Number(obj.expires_in||3500)};
  return obj.access_token;
}

async function accessToken() {
  if(authContext.getStore()?.user===true) return userAccessToken();
  return serviceAccessToken();
}

function oauthStateSign(payload) {
  const key=String(process.env.ND_DRIVE_BRIDGE_TOKEN||'').trim();
  if(!key) throw new Error('drive oauth state key missing');
  return crypto.createHmac('sha256',key).update(payload).digest('base64url');
}

function createOAuthState() {
  const ts=Date.now().toString();
  const nonce=crypto.randomBytes(18).toString('base64url');
  const payload=ts+'.'+nonce;
  return payload+'.'+oauthStateSign(payload);
}

function validateOAuthState(state) {
  const parts=String(state||'').split('.');
  if(parts.length!==3) return false;
  const payload=parts[0]+'.'+parts[1];
  const expected=oauthStateSign(payload);
  const a=Buffer.from(parts[2]),b=Buffer.from(expected);
  if(a.length!==b.length || !crypto.timingSafeEqual(a,b)) return false;
  const ts=Number(parts[0]);
  return Number.isFinite(ts) && Math.abs(Date.now()-ts)<30*60*1000;
}

async function persistEncryptedRefreshToken(refreshToken,userToken) {
  const blob=Buffer.from(JSON.stringify(encryptRefreshToken(refreshToken)),'utf8');
  const q=new URLSearchParams({
    q:"name = '"+USER_OAUTH_STORE_NAME.replace(/'/g,"\\'")+"' and '"+USER_OAUTH_STORE_PARENT+"' in parents and trashed = false",
    pageSize:'10',spaces:'drive',fields:'files(id,name,version)'
  });
  const existing=await directFetchJsonWithToken(userToken,'https://www.googleapis.com/drive/v3/files?'+q.toString());
  let fileId=(existing.files||[])[0]?.id||null;
  if(fileId){
    const res=await fetch('https://www.googleapis.com/upload/drive/v3/files/'+encodeURIComponent(fileId)+'?uploadType=media&supportsAllDrives=true',{
      method:'PATCH',headers:{authorization:'Bearer '+userToken,'content-type':'application/json'},body:blob
    });
    if(!res.ok) throw new Error('drive oauth secret update HTTP '+res.status);
  }else{
    const boundary='ndoauth-'+crypto.randomBytes(12).toString('hex');
    const meta={name:USER_OAUTH_STORE_NAME,parents:[USER_OAUTH_STORE_PARENT]};
    const body=Buffer.concat([
      Buffer.from('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+JSON.stringify(meta)+'\r\n--'+boundary+'\r\nContent-Type: application/json\r\n\r\n'),
      blob,
      Buffer.from('\r\n--'+boundary+'--\r\n')
    ]);
    const res=await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id',{
      method:'POST',headers:{authorization:'Bearer '+userToken,'content-type':'multipart/related; boundary='+boundary},body
    });
    const text=await res.text();
    if(!res.ok) throw new Error('drive oauth secret create HTTP '+res.status+': '+text.slice(0,500));
    fileId=JSON.parse(text||'{}').id;
  }
  const serviceEmail=String(process.env.ND_GOOGLE_CLIENT_EMAIL||'').trim();
  if(serviceEmail && fileId){
    try{
      await directFetchJsonWithToken(userToken,'https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(fileId)+'/permissions?supportsAllDrives=true&sendNotificationEmail=false',{
        method:'POST',body:{type:'user',role:'reader',emailAddress:serviceEmail}
      });
    }catch(e){
      if(!String(e.message||e).includes('already')) throw e;
    }
  }
  userRefreshCache=String(refreshToken);
  userTokenCache=null;
  // Verify the service account can recover the ciphertext after restart.
  const serviceToken=await serviceAccessToken();
  const found=await findOAuthStoreFile(serviceToken);
  if(!found || found.id!==fileId) throw new Error('drive oauth secret service-account readback missing');
  return fileId;
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

async function requireMcpWritable(id,{allowTrashed=false}={}) {
  const m = await metadata(id);
  if (DEVMODE_FULL_WRITE) {
    if (!m?.capabilities?.canEdit || (!allowTrashed && m.trashed)) throw new Error('drive write denied: active user cannot edit target');
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
  const before=await requireMcpWritable(id,{allowTrashed:args.trashed===false});
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
  const before=await requireMcpWritable(id,{allowTrashed:true});
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
  const out = await authContext.run({user:true},()=>handleMcpMessage(msg));
  if (out === null) { res.writeHead(202,{'cache-control':'no-store'}); return res.end(); }
  return json(res,200,out);
}


function parseLinearMcpText(raw) {
  const vals=[];
  for (const line of String(raw||'').split(/\r?\n/)) {
    if (!line.startsWith('data: ')) continue;
    try { vals.push(JSON.parse(line.slice(6))); } catch {}
  }
  if (vals.length) return vals[vals.length-1];
  try { return JSON.parse(String(raw||'{}')); } catch { return {raw:String(raw||'').slice(0,6000)}; }
}

function linearOauthConfigured(){
  return !!(LINEAR_OAUTH_CLIENT_ID && LINEAR_OAUTH_CLIENT_SECRET);
}

function linearRedact(value){
  let out=String(value??'');
  for(const secret of [
    LINEAR_API_KEY,LINEAR_OAUTH_CLIENT_ID,LINEAR_OAUTH_CLIENT_SECRET,LINEAR_GITHUB_PAT,
    linearOauthTokenCache?.token,linearUserOauthTokenCache?.token,linearUserOauthRefreshCache
  ]){
    if(secret) out=out.replaceAll(String(secret),'[REDACTED]');
  }
  return out;
}

async function linearOauthAccessToken(force=false){
  if(!linearOauthConfigured()) throw new Error('linear_oauth_not_configured');
  const now=Math.floor(Date.now()/1000);
  if(!force && linearOauthTokenCache?.token && linearOauthTokenCache.exp>now+120) return linearOauthTokenCache.token;
  const body=new URLSearchParams({
    grant_type:'client_credentials',
    scope:LINEAR_OAUTH_SCOPE,
    client_id:LINEAR_OAUTH_CLIENT_ID,
    client_secret:LINEAR_OAUTH_CLIENT_SECRET
  });
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),60000);
  try{
    const r=await fetch(LINEAR_OAUTH_TOKEN_URL,{
      method:'POST',
      headers:{'content-type':'application/x-www-form-urlencoded',accept:'application/json','user-agent':'ND-External-Linear-OAuth/1.0'},
      body,signal:controller.signal
    });
    const raw=await r.text();
    if(!r.ok) throw new Error('Linear OAuth token HTTP '+r.status+': '+linearRedact(raw).slice(0,700));
    const obj=JSON.parse(raw||'{}');
    const token=String(obj.access_token||'');
    if(!token) throw new Error('linear_oauth_access_token_missing');
    linearOauthTokenCache={token,exp:now+Number(obj.expires_in||3500),scope:String(obj.scope||LINEAR_OAUTH_SCOPE)};
    return token;
  }finally{clearTimeout(timer);}
}

function linearUserOauthConfigured(){
  return !!(LINEAR_USER_OAUTH_CLIENT_ID && LINEAR_GITHUB_PAT && LINEAR_BRIDGE_KEY);
}

function linearUserOauthCryptoKey(purpose){
  if(!LINEAR_BRIDGE_KEY) throw new Error('linear_bridge_key_missing');
  return crypto.createHash('sha256').update('nd-linear-user-oauth-v1\0'+purpose+'\0'+LINEAR_BRIDGE_KEY).digest();
}

function linearEncryptObject(obj,purpose){
  const iv=crypto.randomBytes(12);
  const key=linearUserOauthCryptoKey(purpose);
  const cipher=crypto.createCipheriv('aes-256-gcm',key,iv);
  cipher.setAAD(Buffer.from(purpose,'utf8'));
  const ciphertext=Buffer.concat([cipher.update(JSON.stringify(obj),'utf8'),cipher.final()]);
  return {schema:'nd-linear-encrypted-v1',purpose,iv:iv.toString('base64'),tag:cipher.getAuthTag().toString('base64'),ciphertext:ciphertext.toString('base64')};
}

function linearDecryptObject(blob,purpose){
  if(!blob||blob.schema!=='nd-linear-encrypted-v1'||blob.purpose!==purpose) throw new Error('linear_encrypted_state_invalid');
  const decipher=crypto.createDecipheriv('aes-256-gcm',linearUserOauthCryptoKey(purpose),Buffer.from(blob.iv,'base64'));
  decipher.setAAD(Buffer.from(purpose,'utf8'));
  decipher.setAuthTag(Buffer.from(blob.tag,'base64'));
  const raw=Buffer.concat([decipher.update(Buffer.from(blob.ciphertext,'base64')),decipher.final()]).toString('utf8');
  return JSON.parse(raw);
}

function linearPkceState(verifier){
  const blob=linearEncryptObject({ts:Date.now(),nonce:crypto.randomBytes(18).toString('base64url'),verifier},'pkce-state');
  return Buffer.from(JSON.stringify(blob),'utf8').toString('base64url');
}

function linearPkceStateRead(state){
  const blob=JSON.parse(Buffer.from(String(state||''),'base64url').toString('utf8'));
  const obj=linearDecryptObject(blob,'pkce-state');
  if(!Number.isFinite(Number(obj.ts))||Math.abs(Date.now()-Number(obj.ts))>30*60*1000) throw new Error('linear_oauth_state_expired');
  if(!obj.verifier) throw new Error('linear_oauth_verifier_missing');
  return obj;
}

async function linearGithubStoreRead(){
  if(!LINEAR_GITHUB_PAT) throw new Error('linear_github_store_not_configured');
  const url='https://api.github.com/repos/'+LINEAR_SECRET_REPO+'/contents/'+LINEAR_USER_OAUTH_STORE_PATH.split('/').map(encodeURIComponent).join('/')+'?ref=main';
  const r=await fetch(url,{headers:{authorization:'Bearer '+LINEAR_GITHUB_PAT,accept:'application/vnd.github+json','x-github-api-version':'2022-11-28','user-agent':'ND-Linear-OAuth-Store/1.0'}});
  if(r.status===404) return null;
  const raw=await r.text();
  if(!r.ok) throw new Error('linear oauth GitHub store read HTTP '+r.status+': '+linearRedact(raw).slice(0,500));
  const obj=JSON.parse(raw||'{}');
  const content=Buffer.from(String(obj.content||'').replace(/\n/g,''),'base64').toString('utf8');
  return {sha:String(obj.sha||''),blob:JSON.parse(content)};
}

async function linearGithubStoreWrite(refreshToken){
  if(!refreshToken) throw new Error('linear_refresh_token_missing');
  const existing=await linearGithubStoreRead();
  const encrypted=linearEncryptObject({
    refresh_token:String(refreshToken),
    client_id:LINEAR_USER_OAUTH_CLIENT_ID,
    updated_at:new Date().toISOString()
  },'refresh-store');
  const body={
    message:'runtime(linear): rotate encrypted user OAuth refresh state',
    content:Buffer.from(JSON.stringify(encrypted,null,2)+'\n','utf8').toString('base64'),
    branch:'main'
  };
  if(existing?.sha) body.sha=existing.sha;
  const url='https://api.github.com/repos/'+LINEAR_SECRET_REPO+'/contents/'+LINEAR_USER_OAUTH_STORE_PATH.split('/').map(encodeURIComponent).join('/');
  const r=await fetch(url,{method:'PUT',headers:{authorization:'Bearer '+LINEAR_GITHUB_PAT,accept:'application/vnd.github+json','content-type':'application/json','x-github-api-version':'2022-11-28','user-agent':'ND-Linear-OAuth-Store/1.0'},body:JSON.stringify(body)});
  const raw=await r.text();
  if(!r.ok) throw new Error('linear oauth GitHub store write HTTP '+r.status+': '+linearRedact(raw).slice(0,500));
  linearUserOauthRefreshCache=String(refreshToken);
  return true;
}

async function linearUserOauthRefreshToken(){
  if(linearUserOauthRefreshCache) return linearUserOauthRefreshCache;
  const stored=await linearGithubStoreRead();
  if(!stored?.blob) throw new Error('linear_user_oauth_not_authorized');
  const obj=linearDecryptObject(stored.blob,'refresh-store');
  if(obj.client_id!==LINEAR_USER_OAUTH_CLIENT_ID) throw new Error('linear_user_oauth_client_mismatch');
  const token=String(obj.refresh_token||'');
  if(!token) throw new Error('linear_user_oauth_refresh_missing');
  linearUserOauthRefreshCache=token;
  return token;
}

async function linearUserOauthAccessToken(force=false){
  if(!linearUserOauthConfigured()) throw new Error('linear_user_oauth_not_configured');
  const now=Math.floor(Date.now()/1000);
  if(!force && linearUserOauthTokenCache?.token && linearUserOauthTokenCache.exp>now+120) return linearUserOauthTokenCache.token;
  const refresh=await linearUserOauthRefreshToken();
  const body=new URLSearchParams({grant_type:'refresh_token',refresh_token:refresh,client_id:LINEAR_USER_OAUTH_CLIENT_ID});
  const r=await fetch(LINEAR_OAUTH_TOKEN_URL,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded',accept:'application/json','user-agent':'ND-Linear-User-OAuth/1.0'},body});
  const raw=await r.text();
  if(!r.ok) throw new Error('Linear user OAuth refresh HTTP '+r.status+': '+linearRedact(raw).slice(0,700));
  const obj=JSON.parse(raw||'{}');
  const access=String(obj.access_token||'');
  const nextRefresh=String(obj.refresh_token||'');
  if(!access||!nextRefresh) throw new Error('linear_user_oauth_rotating_token_missing');
  // Persist the rotated refresh token before accepting the new access token.
  await linearGithubStoreWrite(nextRefresh);
  linearUserOauthTokenCache={token:access,exp:now+Number(obj.expires_in||86399),scope:String(obj.scope||'read write')};
  return access;
}

async function linearUserOauthExchange(code,state){
  if(!linearUserOauthConfigured()) throw new Error('linear_user_oauth_not_configured');
  const st=linearPkceStateRead(state);
  const body=new URLSearchParams({
    code:String(code||''),
    redirect_uri:LINEAR_USER_OAUTH_REDIRECT_URI,
    client_id:LINEAR_USER_OAUTH_CLIENT_ID,
    code_verifier:String(st.verifier),
    grant_type:'authorization_code'
  });
  const r=await fetch(LINEAR_OAUTH_TOKEN_URL,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded',accept:'application/json','user-agent':'ND-Linear-User-OAuth/1.0'},body});
  const raw=await r.text();
  if(!r.ok) throw new Error('Linear user OAuth exchange HTTP '+r.status+': '+linearRedact(raw).slice(0,700));
  const obj=JSON.parse(raw||'{}');
  const access=String(obj.access_token||'');
  const refresh=String(obj.refresh_token||'');
  if(!access||!refresh) throw new Error('linear_user_oauth_exchange_token_missing');
  await linearGithubStoreWrite(refresh);
  linearUserOauthTokenCache={token:access,exp:Math.floor(Date.now()/1000)+Number(obj.expires_in||86399),scope:String(obj.scope||'read write')};
  return access;
}

async function linearDirectAuth(){
  if(linearUserOauthConfigured()){
    try{await linearUserOauthAccessToken(); return 'user_oauth';}catch{}
  }
  if(linearOauthConfigured()){
    try{await linearOauthAccessToken(); return 'oauth';}catch{}
  }
  return 'api_key';
}

async function linearAuth(auth='api_key'){
  const mode=auth==='user_oauth'?'user_oauth':auth==='oauth'?'oauth':'api_key';
  if(mode==='user_oauth'){
    const token=await linearUserOauthAccessToken();
    return {mode,mcpAuthorization:'Bearer '+token,graphqlAuthorization:'Bearer '+token};
  }
  if(mode==='oauth'){
    const token=await linearOauthAccessToken();
    return {mode,mcpAuthorization:'Bearer '+token,graphqlAuthorization:'Bearer '+token};
  }
  if(!LINEAR_API_KEY) throw new Error('linear_api_key_not_configured');
  return {mode,mcpAuthorization:'Bearer '+LINEAR_API_KEY,graphqlAuthorization:LINEAR_API_KEY};
}

async function linearPost(payload, sid=null, timeoutMs=60000, auth='api_key') {
  const cred=await linearAuth(auth);
  const headers={
    authorization:cred.mcpAuthorization,
    'content-type':'application/json',
    accept:'application/json, text/event-stream',
    'user-agent':'ND-External-Linear-MCP/3.0'
  };
  if (sid) {
    headers['mcp-session-id']=sid;
    headers['mcp-protocol-version']='2025-06-18';
  }
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try {
    const r=await fetch(LINEAR_MCP_URL,{method:'POST',headers,body:JSON.stringify(payload),signal:controller.signal});
    const raw=await r.text();
    if(r.status===401 && auth==='oauth') linearOauthTokenCache=null;
    if(r.status===401 && auth==='user_oauth') linearUserOauthTokenCache=null;
    if(!r.ok) throw new Error('Linear MCP HTTP '+r.status+': '+linearRedact(raw).slice(0,1000));
    return {status:r.status,sid:r.headers.get('mcp-session-id'),body:parseLinearMcpText(raw),auth:cred.mode};
  } finally { clearTimeout(timer); }
}

async function linearGraphql(query, variables={}, timeoutMs=60000, auth='api_key') {
  const cred=await linearAuth(auth);
  const q=String(query||'').trim();
  if(!q) throw new Error('linear_graphql_query_required');
  if(q.length>100000) throw new Error('linear_graphql_query_too_large');
  if(!variables || typeof variables!=='object' || Array.isArray(variables)) throw new Error('linear_graphql_variables_must_be_object');
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const r=await fetch(LINEAR_GQL_URL,{
      method:'POST',
      headers:{
        authorization:cred.graphqlAuthorization,
        'content-type':'application/json',
        accept:'application/json',
        'user-agent':'ND-External-Linear-GraphQL/2.0'
      },
      body:JSON.stringify({query:q,variables}),
      signal:controller.signal
    });
    const raw=await r.text();
    if(r.status===401 && auth==='oauth') linearOauthTokenCache=null;
    if(r.status===401 && auth==='user_oauth') linearUserOauthTokenCache=null;
    if(!r.ok) throw new Error('Linear GraphQL HTTP '+r.status+': '+linearRedact(raw).slice(0,1000));
    const obj=JSON.parse(raw||'{}');
    if(obj.errors?.length) throw new Error('Linear GraphQL errors: '+linearRedact(JSON.stringify(obj.errors)).slice(0,1200));
    return obj.data||{};
  } finally { clearTimeout(timer); }
}

async function linearProviderCapabilities(auth='api_key') {
  const data=await linearGraphql(`query {
    viewer { id admin }
    __schema { mutationType { fields { name } } }
  }`,{},60000,auth);
  const names=(((data.__schema||{}).mutationType||{}).fields||[]).map(x=>x?.name).filter(Boolean);
  const missing=LINEAR_REQUIRED_DESTRUCTIVE.filter(x=>!names.includes(x));
  return {
    auth,
    viewer_id:data.viewer?.id||null,
    viewer_admin:data.viewer?.admin===true,
    required_destructive:LINEAR_REQUIRED_DESTRUCTIVE,
    missing_destructive:missing,
    full_destructive_surface:missing.length===0
  };
}

async function linearSessionCall(method, params={}, auth='api_key') {
  const init=await linearPost({
    jsonrpc:'2.0',id:1,method:'initialize',
    params:{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'ND External Linear',version:'3.0'}}
  },null,60000,auth);
  if(init.status!==200) throw new Error('linear_initialize_failed');
  await linearPost({jsonrpc:'2.0',method:'notifications/initialized',params:{}},init.sid,60000,auth);
  const call=await linearPost({jsonrpc:'2.0',id:2,method,params},init.sid,60000,auth);
  return {serverInfo:init.body?.result?.serverInfo||{},response:call.body,auth};
}

async function linearHealth(auth='api_key') {
  const state=auth==='user_oauth'?linearUserOauthSelftestState:auth==='oauth'?linearOauthSelftestState:linearSelftestState;
  if(auth==='user_oauth' && !linearUserOauthConfigured()){
    return {ok:false,configured:false,auth,route:'railway_external_user_oauth_full_linear_api',error:'linear_user_oauth_not_configured'};
  }
  if(auth==='oauth' && !linearOauthConfigured()){
    return {ok:false,configured:false,auth,route:'railway_external_oauth_full_linear_api',error:'linear_oauth_not_configured'};
  }
  const tools=await linearSessionCall('tools/list',{},auth);
  const list=tools.response?.result?.tools||[];
  const ws=await linearSessionCall('tools/call',{name:'get_workspace',arguments:{}},auth);
  const content=ws.response?.result?.content||[];
  const caps=await linearProviderCapabilities(auth);
  return {
    ok:list.length>0 && content.length>0 && caps.full_destructive_surface===true && state.ok===true,
    configured:true,
    auth,
    route:auth==='user_oauth'?'railway_external_user_oauth_full_linear_api':auth==='oauth'?'railway_external_oauth_full_linear_api':'railway_external_api_key_full_linear_api',
    official_mcp:true,
    graphql_full_api:true,
    tools_count:list.length,
    workspace_read:content.length>0,
    destructive_capabilities:caps,
    serverInfo:ws.serverInfo||tools.serverInfo||{},
    write_selftest:state
  };
}


function linearToolPayloadResult(response) {
  const content=response?.result?.content||[];
  for(const part of content){
    if(part?.type!=='text' || !part?.text) continue;
    try{return JSON.parse(part.text);}catch{}
  }
  return null;
}

async function linearFullSelftest(auth='api_key') {
  const startedAt=new Date().toISOString();
  const rec={schema:'nd-linear-railway-full-qualification-v2',ok:false,auth};
  let commentId=null;
  let issueId=null;
  let issueIdentifier=null;
  const marker='ND Linear '+auth+' resilience qualification probe — safe to delete — '+startedAt;
  const issueMarker='ND Linear '+auth+' full CRUD qualification probe — safe to permanently delete — '+startedAt;
  try{
    if(auth==='user_oauth' && !linearUserOauthConfigured()) throw new Error('linear_user_oauth_not_configured');
    if(auth==='oauth' && !linearOauthConfigured()) throw new Error('linear_oauth_not_configured');
    const tl=await linearSessionCall('tools/list',{},auth);
    const tools=tl.response?.result?.tools||[];
    rec.tools_count=tools.length;
    rec.tools_catalog=tools.length>0;
    const caps=await linearProviderCapabilities(auth);
    rec.viewer_id_present=!!caps.viewer_id;
    rec.viewer_admin=caps.viewer_admin;
    rec.missing_destructive=caps.missing_destructive;
    rec.full_destructive_surface=caps.full_destructive_surface;
    for(const name of ['get_workspace','get_issue','save_issue','save_document','save_project','save_comment','delete_comment','list_comments']){
      rec['has_'+name]=tools.some(x=>x?.name===name);
    }

    const ws=await linearSessionCall('tools/call',{name:'get_workspace',arguments:{}},auth);
    rec.workspace_read=!!linearToolPayloadResult(ws.response);

    const issue=await linearSessionCall('tools/call',{name:'get_issue',arguments:{id:'NAM-122'}},auth);
    rec.issue_read=!!linearToolPayloadResult(issue.response);

    const wr=await linearSessionCall('tools/call',{name:'save_comment',arguments:{issueId:'NAM-122',body:marker}},auth);
    const created=linearToolPayloadResult(wr.response)||{};
    commentId=String(created.id||'');
    rec.write=!!commentId;

    const rb=await linearSessionCall('tools/call',{name:'list_comments',arguments:{issueId:'NAM-122',limit:50}},auth);
    const listed=linearToolPayloadResult(rb.response)||{};
    const comments=listed.comments||[];
    rec.readback=!!commentId && comments.some(x=>x?.id===commentId && x?.body===marker);

    if(commentId){
      const del=await linearSessionCall('tools/call',{name:'delete_comment',arguments:{id:commentId}},auth);
      const deleted=linearToolPayloadResult(del.response)||{};
      rec.delete=deleted.success===true;

      const rb2=await linearSessionCall('tools/call',{name:'list_comments',arguments:{issueId:'NAM-122',limit:50}},auth);
      const listed2=linearToolPayloadResult(rb2.response)||{};
      rec.cleanup_readback=!(listed2.comments||[]).some(x=>x?.id===commentId);
    }

    const iw=await linearSessionCall('tools/call',{name:'save_issue',arguments:{
      team:'Nameless Dhamma',
      title:issueMarker,
      description:'Temporary Linear full-CRUD qualification object. Must be permanently deleted by this self-test.'
    }},auth);
    const createdIssue=linearToolPayloadResult(iw.response)||{};
    issueIdentifier=String(createdIssue.id||'');
    issueId=String(createdIssue.uuid||createdIssue.id||'');
    rec.issue_create=!!issueId;

    const updatedTitle=issueMarker+' — updated';
    if(issueIdentifier){
      const iu=await linearSessionCall('tools/call',{name:'save_issue',arguments:{id:issueIdentifier,title:updatedTitle}},auth);
      const updated=linearToolPayloadResult(iu.response)||{};
      rec.issue_update=updated.title===updatedTitle;

      const ir=await linearSessionCall('tools/call',{name:'get_issue',arguments:{id:issueIdentifier}},auth);
      const reread=linearToolPayloadResult(ir.response)||{};
      rec.issue_update_readback=reread.title===updatedTitle;
    }

    if(issueId){
      const dd=await linearGraphql(
        'mutation($id:String!,$permanentlyDelete:Boolean){issueDelete(id:$id,permanentlyDelete:$permanentlyDelete){success entity{id}}}',
        {id:issueId,permanentlyDelete:true},60000,auth
      );
      rec.issue_delete_acknowledged=dd.issueDelete?.success===true;
      rec.issue_permanent_delete=dd.issueDelete?.success===true;

      try{
        const dr=await linearGraphql('query($id:String!){issue(id:$id){id title trashed}}',{id:issueId},60000,auth);
        rec.issue_delete_readback=!dr.issue;
      }catch(e){
        rec.issue_delete_readback=true;
      }
    }

    const required=[
      'tools_catalog','viewer_id_present','full_destructive_surface',
      'has_get_workspace','has_get_issue','has_save_issue','has_save_document','has_save_project',
      'has_save_comment','has_delete_comment','has_list_comments','workspace_read','issue_read',
      'write','readback','delete','cleanup_readback','issue_create','issue_update',
      'issue_update_readback','issue_permanent_delete','issue_delete_readback'
    ];
    rec.ok=required.every(k=>rec[k]===true);
  }catch(e){
    rec.error=linearRedact(e?.message||e).slice(0,1000);
    try{
      const rb=await linearSessionCall('tools/call',{name:'list_comments',arguments:{issueId:'NAM-122',limit:100}},auth);
      const listed=linearToolPayloadResult(rb.response)||{};
      const matches=(listed.comments||[]).filter(x=>x?.body===marker && x?.id);
      for(const c of matches){
        try{await linearSessionCall('tools/call',{name:'delete_comment',arguments:{id:c.id}},auth);}catch{}
      }
      if(matches.length) rec.cleanup_after_error=true;
    }catch{}
    try{
      let ids=[];
      if(issueId){
        try{
          const q=await linearGraphql('query($id:String!){issue(id:$id){id}}',{id:issueId},60000,auth);
          if(q.issue?.id) ids.push(q.issue.id);
        }catch{}
      }else{
        try{
          const q=await linearGraphql('query($title:String!){issues(filter:{title:{startsWith:$title}},first:20){nodes{id title}}}',{title:issueMarker},60000,auth);
          ids=(q.issues?.nodes||[]).filter(x=>String(x?.title||'').startsWith(issueMarker)).map(x=>x.id);
        }catch{}
      }
      for(const id of ids){
        try{await linearGraphql('mutation($id:String!,$permanentlyDelete:Boolean){issueDelete(id:$id,permanentlyDelete:$permanentlyDelete){success}}',{id,permanentlyDelete:true},60000,auth);}catch{}
      }
      if(ids.length) rec.issue_cleanup_after_error=true;
    }catch{}
  }
  const state={last_run:startedAt,ok:rec.ok===true,error:rec.error||null,auth};
  if(auth==='user_oauth') linearUserOauthSelftestState=state;
  else if(auth==='oauth') linearOauthSelftestState=state;
  else linearSelftestState=state;
  const event=auth==='user_oauth'?'ND_LINEAR_USER_OAUTH_FULL_QUALIFICATION':auth==='oauth'?'ND_LINEAR_OAUTH_FULL_QUALIFICATION':'ND_LINEAR_FULL_QUALIFICATION';
  console.log(JSON.stringify({event,...rec}));
  return rec;
}

async function handleLinearInvoke(req,res) {
  const key=req.headers['x-nd-linear-key'] || req.headers['x-nd-bridge-key'];
  if(!safeEqual(key,LINEAR_BRIDGE_KEY)) return json(res,401,{ok:false,error:'unauthorized'});
  const chunks=[]; for await(const ch of req) chunks.push(ch);
  let body={};
  try{body=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}
  catch{return json(res,400,{ok:false,error:'invalid_json'});}
  try{
    const op=String(body.operation||'').trim();
    const auth=body.auth==='user_oauth'?'user_oauth':body.auth==='oauth'?'oauth':'api_key';
    if(auth==='user_oauth' && !linearUserOauthConfigured()) return json(res,503,{ok:false,provider:'linear',auth,error:'linear_user_oauth_not_configured'});
    if(auth==='oauth' && !linearOauthConfigured()) return json(res,503,{ok:false,provider:'linear',auth,error:'linear_oauth_not_configured'});
    if(op==='tools_list'){
      const r=await linearSessionCall('tools/list',{},auth);
      return json(res,200,{ok:true,provider:'linear',auth,transport:'railway_external_to_official_linear_mcp',serverInfo:r.serverInfo,response:r.response});
    }
    if(op==='tool_call'){
      const tool=String(body.tool||'').trim();
      const args=(body.arguments&&typeof body.arguments==='object')?body.arguments:{};
      if(!tool) return json(res,400,{ok:false,error:'tool_required'});
      const r=await linearSessionCall('tools/call',{name:tool,arguments:args},auth);
      return json(res,200,{ok:true,provider:'linear',auth,transport:'railway_external_to_official_linear_mcp',serverInfo:r.serverInfo,response:r.response});
    }
    if(op==='graphql'){
      const query=String(body.query||'');
      const variables=(body.variables&&typeof body.variables==='object'&&!Array.isArray(body.variables))?body.variables:{};
      const result=await linearGraphql(query,variables,60000,auth);
      const kind=query.trim().toLowerCase().startsWith('mutation')?'mutation':'query';
      return json(res,200,{ok:true,provider:'linear',auth,transport:'railway_external_to_linear_graphql_full',graphql_kind:kind,result});
    }
    return json(res,400,{ok:false,error:'operation_must_be_tools_list_tool_call_or_graphql'});
  }catch(e){
    return json(res,502,{ok:false,provider:'linear',error:linearRedact(e?.message||e).slice(0,1200)});
  }
}

async function handleLinearMcp(req,res) {
  if(!LINEAR_DEVMODE_TOKEN || req.url!==LINEAR_DEVMODE_MCP_PATH) return false;
  const auth=await linearDirectAuth();
  if(req.method==='GET'){
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});
    res.write(': nd-linear-full-direct auth='+auth+'\n\n'); return res.end();
  }
  if(req.method!=='POST') return json(res,405,{ok:false,error:'method_not_allowed'});
  const chunks=[]; for await(const ch of req) chunks.push(ch);
  let msg={};
  try{msg=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}
  catch{return json(res,400,{jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}});}
  const id=msg.id??null, method=String(msg.method||'');
  try{
    if(method==='initialize'){
      const init=await linearPost(msg,null,60000,auth);
      return json(res,200,init.body);
    }
    if(method==='ping') return json(res,200,{jsonrpc:'2.0',id,result:{}});
    if(method.startsWith('notifications/')) {res.writeHead(202,{'cache-control':'no-store'}); return res.end();}
    if(method==='tools/list'){
      const r=await linearSessionCall('tools/list',msg.params||{},auth);
      const out=r.response||{};
      const tools=out?.result?.tools||[];
      if(!tools.some(x=>x?.name==='nd_linear_graphql')){
        tools.push({
          name:'nd_linear_graphql',
          description:'Direct full Linear GraphQL provider API for operations missing from official MCP, including delete/archive/unarchive. Mutations are never auto-retried; after ambiguity perform provider readback before retry.',
          inputSchema:{
            type:'object',
            properties:{
              query:{type:'string'},
              variables:{type:'object',additionalProperties:true}
            },
            required:['query'],
            additionalProperties:false
          }
        });
      }
      if(out.id!==id && id!==null) out.id=id;
      return json(res,200,out);
    }
    if(method==='tools/call'){
      const name=String(msg?.params?.name||'');
      if(name==='nd_linear_graphql'){
        const args=msg?.params?.arguments||{};
        const result=await linearGraphql(String(args.query||''),(args.variables&&typeof args.variables==='object'&&!Array.isArray(args.variables))?args.variables:{},60000,auth);
        return json(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(result)}],structuredContent:result,isError:false}});
      }
      const r=await linearSessionCall('tools/call',msg.params||{},auth);
      const out=r.response||{};
      if(out.id!==id && id!==null) out.id=id;
      return json(res,200,out);
    }
    return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
  }catch(e){
    return json(res,200,{jsonrpc:'2.0',id,error:{code:-32000,message:linearRedact(e?.message||e).slice(0,1200)}});
  }
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
  if (req.method === 'GET' && req.url === '/drive/oauth/start') {
    try{
      if(!USER_OAUTH_CLIENT_ID || !USER_OAUTH_CLIENT_SECRET) return json(res,503,{ok:false,error:'drive user oauth client missing'});
      const state=createOAuthState();
      const q=new URLSearchParams({
        client_id:USER_OAUTH_CLIENT_ID,
        redirect_uri:USER_OAUTH_REDIRECT_URI,
        response_type:'code',
        access_type:'offline',
        prompt:'consent',
        include_granted_scopes:'true',
        login_hint:'namelessdhamma@gmail.com',
        scope:SCOPES,
        state
      });
      res.writeHead(302,{location:'https://accounts.google.com/o/oauth2/v2/auth?'+q.toString(),'cache-control':'no-store'});
      return res.end();
    }catch(e){return json(res,503,{ok:false,error:String(e.message||e).slice(0,500)});}
  }
  async function completeUserOAuth(body,res) {
    try{
      if(body.error) return json(res,400,{ok:false,error:'google_oauth_'+String(body.error).slice(0,120)});
      if(!body.code || !validateOAuthState(body.state)) return json(res,400,{ok:false,error:'invalid_oauth_callback'});
      const form=new URLSearchParams({
        client_id:USER_OAUTH_CLIENT_ID,
        client_secret:USER_OAUTH_CLIENT_SECRET,
        code:String(body.code),
        redirect_uri:USER_OAUTH_REDIRECT_URI,
        grant_type:'authorization_code'
      });
      const tr=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:form});
      const tt=await tr.text();
      if(!tr.ok) return json(res,502,{ok:false,error:'google_token_exchange_'+tr.status,detail:tt.slice(0,500)});
      const tok=JSON.parse(tt||'{}');
      if(!tok.refresh_token || !tok.access_token) return json(res,502,{ok:false,error:'refresh_token_missing'});
      const fileId=await persistEncryptedRefreshToken(tok.refresh_token,tok.access_token);
      const probe=await authContext.run({user:true},()=>driveSearch({query:'',top_n:1}));
      return json(res,200,{ok:true,status:'AUTHORIZED',secret_store_verified:true,store_file_id:fileId,probe_result_count:(probe.results||[]).length});
    }catch(e){return json(res,502,{ok:false,error:String(e.message||e).slice(0,800)});}
  }

  if (req.method === 'GET' && req.url?.startsWith('/drive/oauth/complete?')) {
    const u=new URL(req.url,'https://nd-external-intelligence-production.up.railway.app');
    return completeUserOAuth({
      code:u.searchParams.get('code'),
      state:u.searchParams.get('state'),
      error:u.searchParams.get('error')
    },res);
  }

  if (req.method === 'POST' && req.url === '/drive/oauth/callback') {
    const chunks=[]; for await(const ch of req) chunks.push(ch);
    let body={};
    try{body=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}
    catch{return json(res,400,{ok:false,error:'invalid_json'});}
    return completeUserOAuth(body,res);
  }
  if (req.method === 'GET' && req.url === '/drive/oauth/status') {
    try{
      const token=await userAccessToken();
      const about=await directFetchJsonWithToken(token,'https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress),storageQuota');
      return json(res,200,{ok:true,authorized:true,user:about.user||null,storage_quota_present:!!about.storageQuota});
    }catch(e){
      return json(res,200,{ok:true,authorized:false,error:String(e.message||e).slice(0,300)});
    }
  }
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
  if (req.method === 'GET' && req.url === '/drive/full/health') {
    try {
      const token=await userAccessToken();
      const about=await directFetchJsonWithToken(token,'https://www.googleapis.com/drive/v3/about?fields=user(emailAddress),storageQuota');
      return json(res,200,{ok:true,route:'railway_external_full_user_oauth',full_rw:true,tools:MCP_TOOLS.length,user:about.user?.emailAddress||null,storage_quota_present:!!about.storageQuota});
    } catch(e) {
      return json(res,503,{ok:false,route:'railway_external_full_user_oauth',error:String(e.message||e).slice(0,500)});
    }
  }
  if (req.method === 'POST' && req.url === '/drive/full/invoke') {
    if (!safeEqual(req.headers['x-nd-bridge-key'], BRIDGE_KEY)) return json(res,401,{ok:false,error:'unauthorized'});
    const chunks=[]; for await (const ch of req) chunks.push(ch);
    let body={};
    try { body=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}'); }
    catch { return json(res,400,{ok:false,error:'invalid_json'}); }
    const tool=String(body.tool||''),args=(body.args&&typeof body.args==='object')?body.args:{};
    try {
      const result=await authContext.run({user:true},()=>mcpInvoke(tool,args));
      return json(res,200,{ok:true,tool,result,auth_mode:'user_oauth'});
    } catch(e) {
      const msg=String(e.message||e).slice(0,1200);
      const status=(msg.includes('REVISION_MISMATCH')||msg.includes('DRIVE_VERSION_MISMATCH')||msg.includes('EXACT_MATCH_REQUIRED'))?409:502;
      return json(res,status,{ok:false,error:msg,auth_mode:'user_oauth'});
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
  if (STORYBOARD_MCP_TOKEN && req.method === 'GET' && req.url?.startsWith('/storyboard-result/'+STORYBOARD_MCP_TOKEN+'/')) {
    const prefix='/storyboard-result/'+STORYBOARD_MCP_TOKEN+'/';
    const leaf=decodeURIComponent(req.url.slice(prefix.length).split('?')[0]);
    const isMp4=leaf.endsWith('.mp4');
    const isJson=leaf.endsWith('.json');
    if(!isMp4 && !isJson) return json(res,404,{ok:false,error:'storyboard_result_format_not_found'});
    const requestId=leaf.replace(/\.(mp4|json)$/,'');
    try{
      const bundle=await storyboardResultBytes(requestId);
      if(!bundle.mp4) return json(res,404,{ok:false,error:'storyboard_result_not_ready',status:bundle.status});
      if(isJson) return json(res,200,{ok:true,request_id:requestId,receipt:bundle.receipt,status:bundle.status});
      res.writeHead(200,{
        'content-type':'video/mp4',
        'content-length':bundle.mp4.length,
        'content-disposition':'inline; filename="'+requestId+'.mp4"',
        'cache-control':'private, no-store'
      });
      return res.end(bundle.mp4);
    }catch(e){
      return json(res,502,{ok:false,error:String(e?.message||e).slice(0,1000)});
    }
  }
  if (req.method === 'GET' && req.url === '/ltx/selftest/status') {
    return json(res,200,{ok:ltxSelftestState.state==='PASS',...ltxSelftestState});
  }
  if (req.method === 'GET' && req.url === '/ltx/health') {
    try {
      const h = await ltxHealth();
      return json(res,200,{...h,mcp_path_configured:!!LTX_MCP_TOKEN,dedicated_mcp:true});
    } catch(e) {
      return json(res,503,{ok:false,error:String(e?.message||e).slice(0,800)});
    }
  }
  if (req.method === 'GET' && req.url?.startsWith('/ltx/probe')) {
    try {
      const u=new URL(req.url,'https://nd-external-intelligence-production.up.railway.app');
      const h = await ltxHealth({probe:true,spaceId:u.searchParams.get('space_id')||undefined});
      return json(res,h.ok?200:503,{...h,mcp_path_configured:!!WAN_MCP_TOKEN});
    } catch(e) {
      return json(res,503,{ok:false,error:String(e?.message||e).slice(0,800)});
    }
  }
  if (req.method === 'GET' && req.url === '/wan/health') {
    try {
      const h = await wanHealth();
      return json(res,200,{...h,mcp_path_configured:!!WAN_MCP_TOKEN});
    } catch(e) {
      return json(res,503,{ok:false,error:String(e?.message||e).slice(0,800)});
    }
  }
  if (req.method === 'GET' && req.url === '/storyboard/health') {
    try {
      const h = await storyboardHealth();
      return json(res,200,{...h,mcp_path_configured:!!STORYBOARD_MCP_TOKEN,dedicated_mcp:true});
    } catch(e) {
      return json(res,503,{ok:false,error:String(e?.message||e).slice(0,800)});
    }
  }
  if (STORYBOARD_MCP_TOKEN && req.url === STORYBOARD_MCP_PATH) {
    const handled = await storyboardMcpHandler(req,res);
    if (handled !== false) return;
  }
  if (LTX_MCP_TOKEN && req.url === LTX_MCP_PATH) {
    const handled = await wanMcpHandler(req,res);
    if (handled !== false) return;
  }
  if (WAN_MCP_TOKEN && req.url === WAN_MCP_PATH) {
    const handled = await wanMcpHandler(req,res);
    if (handled !== false) return;
  }
  if (LINEAR_DEVMODE_TOKEN && req.url === LINEAR_DEVMODE_MCP_PATH) {
    const handled = await handleLinearMcp(req,res);
    if (handled !== false) return;
  }
  if (req.method === 'GET' && req.url === '/linear/user-oauth/start') {
    try{
      if(!linearUserOauthConfigured()) return json(res,503,{ok:false,error:'linear_user_oauth_not_configured'});
      const verifier=crypto.randomBytes(48).toString('base64url');
      const challenge=crypto.createHash('sha256').update(verifier).digest('base64url');
      const state=linearPkceState(verifier);
      const q=new URLSearchParams({
        client_id:LINEAR_USER_OAUTH_CLIENT_ID,
        redirect_uri:LINEAR_USER_OAUTH_REDIRECT_URI,
        response_type:'code',
        scope:'read,write',
        actor:'user',
        code_challenge:challenge,
        code_challenge_method:'S256',
        state
      });
      res.writeHead(302,{location:'https://linear.app/oauth/authorize?'+q.toString(),'cache-control':'no-store'});
      return res.end();
    }catch(e){
      return json(res,503,{ok:false,error:linearRedact(e?.message||e).slice(0,700)});
    }
  }
  if (req.method === 'GET' && req.url?.startsWith('/linear/oauth/callback?')) {
    const u=new URL(req.url,'https://nd-external-intelligence-production.up.railway.app');
    try{
      if(u.searchParams.get('error')) return json(res,400,{ok:false,error:'linear_oauth_'+String(u.searchParams.get('error')).slice(0,160)});
      const code=u.searchParams.get('code'),state=u.searchParams.get('state');
      if(!code||!state) return json(res,400,{ok:false,error:'linear_oauth_callback_missing_code_or_state'});
      await linearUserOauthExchange(code,state);
      const qualification=await linearFullSelftest('user_oauth');
      return json(res,qualification.ok?200:503,{
        ok:qualification.ok===true,
        status:qualification.ok?'AUTHORIZED_FULL_CRUD':'AUTHORIZED_QUALIFICATION_FAILED',
        auth:'user_oauth',
        encrypted_store:'github',
        qualification:{
          full_destructive_surface:qualification.full_destructive_surface===true,
          issue_create:qualification.issue_create===true,
          issue_update:qualification.issue_update===true,
          issue_update_readback:qualification.issue_update_readback===true,
          issue_permanent_delete:qualification.issue_permanent_delete===true,
          issue_delete_readback:qualification.issue_delete_readback===true
        }
      });
    }catch(e){
      return json(res,502,{ok:false,auth:'user_oauth',error:linearRedact(e?.message||e).slice(0,900)});
    }
  }
  if (req.method === 'GET' && req.url === '/linear/user-oauth/status') {
    try{
      if(!linearUserOauthConfigured()) return json(res,200,{ok:true,configured:false,authorized:false});
      await linearUserOauthAccessToken();
      const caps=await linearProviderCapabilities('user_oauth');
      return json(res,200,{
        ok:true,configured:true,authorized:true,auth:'user_oauth',
        full_destructive_surface:caps.full_destructive_surface,
        missing_destructive:caps.missing_destructive,
        write_selftest:linearUserOauthSelftestState
      });
    }catch(e){
      return json(res,200,{ok:true,configured:linearUserOauthConfigured(),authorized:false,error:linearRedact(e?.message||e).slice(0,500)});
    }
  }
  if (req.method === 'GET' && req.url === '/linear/user-oauth/health') {
    try{
      const h=await linearHealth('user_oauth');
      return json(res,h.ok?200:503,h);
    }catch(e){
      return json(res,503,{ok:false,auth:'user_oauth',configured:linearUserOauthConfigured(),route:'railway_external_user_oauth_full_linear_api',error:linearRedact(e?.message||e).slice(0,800)});
    }
  }
  if (req.method === 'GET' && req.url === '/linear/health') {
    try {
      const h=await linearHealth('api_key');
      return json(res,h.ok?200:503,h);
    } catch(e) {
      return json(res,503,{ok:false,auth:'api_key',route:'railway_external_api_key_full_linear_api',error:linearRedact(e?.message||e).slice(0,800)});
    }
  }
  if (req.method === 'GET' && req.url === '/linear/oauth/health') {
    try {
      const h=await linearHealth('oauth');
      return json(res,h.ok?200:503,h);
    } catch(e) {
      return json(res,503,{ok:false,auth:'oauth',configured:linearOauthConfigured(),route:'railway_external_oauth_full_linear_api',error:linearRedact(e?.message||e).slice(0,800)});
    }
  }
  if (req.method === 'POST' && req.url === '/linear/invoke') return handleLinearInvoke(req,res);
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
  console.log(JSON.stringify({event:'ND_WAN_VIDEO_MCP_READY',mcp_path_configured:!!WAN_MCP_TOKEN,mode:'full'}));
  console.log(JSON.stringify({event:'ND_STORYBOARD_MCP_READY',mcp_path_configured:!!STORYBOARD_MCP_TOKEN,mode:'free_public_actions'}));
  console.log(JSON.stringify({event:'ND_KAGGLE_CONFIG',configured:!!KAGGLE_API_TOKEN}));
  if(KAGGLE_API_TOKEN) setTimeout(()=>kaggleSelftest().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_SELFTEST_CRASH',error:String(e?.message||e).slice(0,500)}))),4000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_GPU_PROBE_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleGpuProbe().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_GPU_PROBE',state:'FAIL',error:String(e?.message||e).slice(0,900)}))),9000);
  if(String(process.env.ND_LTX_SELFTEST_ON_START||'false').toLowerCase()==='true'){
    ltxSelftestState={state:'RUNNING',updated_at:new Date().toISOString()};
    setTimeout(async()=>{
      const r=await ltxKeyframeSelftest();
      ltxSelftestState={
        state:r.ok?'PASS':'FAIL',
        updated_at:new Date().toISOString(),
        space_id:r.space_id||null,
        elapsed_ms:r.elapsed_ms||null,
        has_video:!!r.video_ref,
        error:r.ok?null:String(r.error||'').slice(0,1000)
      };
      console.log(JSON.stringify({event:'ND_LTX_KEYFRAME_SELFTEST',...ltxSelftestState}));
    },12000);
  }
  console.log(JSON.stringify({
    event:'ND_LINEAR_PROXY_READY',
    api_key_configured:!!LINEAR_API_KEY,
    client_credentials_configured:linearOauthConfigured(),
    user_oauth_configured:linearUserOauthConfigured(),
    bridge_configured:!!LINEAR_BRIDGE_KEY,
    devmode_mcp_configured:!!LINEAR_DEVMODE_TOKEN
  }));
  setTimeout(()=>linearFullSelftest('api_key').catch(e=>console.error(JSON.stringify({event:'ND_LINEAR_FULL_QUALIFICATION_CRASH',auth:'api_key',error:linearRedact(e?.message||e).slice(0,500)}))),5000);
  if(linearOauthConfigured()) setTimeout(()=>linearFullSelftest('oauth').catch(e=>console.error(JSON.stringify({event:'ND_LINEAR_FULL_QUALIFICATION_CRASH',auth:'oauth',error:linearRedact(e?.message||e).slice(0,500)}))),8000);
  if(linearUserOauthConfigured()) setTimeout(async()=>{
    try{await linearUserOauthAccessToken(); await linearFullSelftest('user_oauth');}
    catch(e){linearUserOauthSelftestState={last_run:new Date().toISOString(),ok:false,error:linearRedact(e?.message||e).slice(0,500),auth:'user_oauth'};}
  },11000);
  const linearSelftestTimer=setInterval(async()=>{
    linearFullSelftest('api_key').catch(e=>console.error(JSON.stringify({event:'ND_LINEAR_FULL_QUALIFICATION_CRASH',auth:'api_key',error:linearRedact(e?.message||e).slice(0,500)})));
    if(linearOauthConfigured()) linearFullSelftest('oauth').catch(e=>console.error(JSON.stringify({event:'ND_LINEAR_FULL_QUALIFICATION_CRASH',auth:'oauth',error:linearRedact(e?.message||e).slice(0,500)})));
    if(linearUserOauthConfigured()){
      try{await linearUserOauthAccessToken(); await linearFullSelftest('user_oauth');}
      catch(e){linearUserOauthSelftestState={last_run:new Date().toISOString(),ok:false,error:linearRedact(e?.message||e).slice(0,500),auth:'user_oauth'};}
    }
  },24*60*60*1000);
  linearSelftestTimer.unref();
});