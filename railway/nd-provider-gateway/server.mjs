import http from 'node:http';
import { URL } from 'node:url';
import { inflateRawSync } from 'node:zlib';
import { createHash, createSign } from 'node:crypto';
import { chromium } from 'playwright-core';
const PORT=Number(process.env.PORT||5678);
const ND_YOUTUBE_MUX_CODE_REV='youtube-mux-rwq-v3-20260916';
const ND_YANDEX_MUX_CODE_REV='yandex-delete-v3-20260919';
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
const ROUTE=String(process.env.ND_YANDEX_MCP_ROUTE_TOKEN||'').trim();
const YANDEX_MCP_PATH=ROUTE?'/yandex/mcp/'+ROUTE:'';
const ND_LIGHTPANDA_MUX_CODE_REV='lightpanda-cdp-playwright-v3-20260920';
const LIGHTPANDA_TOKEN=String(process.env.LIGHTPANDA_TOKEN||'').trim();
const LIGHTPANDA_PATH_TOKEN=String(process.env.ND_LIGHTPANDA_MCP_PATH_TOKEN||'').trim();
const LIGHTPANDA_MCP_PATH=LIGHTPANDA_PATH_TOKEN?'/nd/lightpanda/mcp/'+LIGHTPANDA_PATH_TOKEN:'';
const LIGHTPANDA_API='https://euwest.cloud.lightpanda.io/api/fetch';
const LIGHTPANDA_CDP_URL='wss://euwest.cloud.lightpanda.io/ws?token='+encodeURIComponent(LIGHTPANDA_TOKEN);
const LIGHTPANDA_MCP_SSE='https://euwest.cloud.lightpanda.io/mcp/sse?token='+encodeURIComponent(LIGHTPANDA_TOKEN);
let lpUpstream={reader:null,postUrl:'',pending:new Map(),connecting:null,ready:false,seq:1000,lastError:''};

const API='https://cloud-api.yandex.net/v1/disk';
const GOOGLE_CLIENT_EMAIL=String(process.env.ND_GOOGLE_CLIENT_EMAIL||'').trim();
const GOOGLE_PRIVATE_KEY_B64=String(process.env.ND_GOOGLE_PRIVATE_KEY_B64||'').trim();
const GOOGLE_STATEHEAD_ID=String(process.env.ND_GOOGLE_STATEHEAD_ID||'').trim();
const ADOPTION_ROUTE_TOKEN=String(process.env.ND_ADOPTION_ROUTE_TOKEN||'').trim();
const ADOPTION_PATH=ADOPTION_ROUTE_TOKEN?'/nd/adoption/'+ADOPTION_ROUTE_TOKEN:'';
let googleTokenCache={token:'',exp:0};
const ADOPTION_READ_REGISTRY_ID=String(process.env.ND_ADOPTION_READ_REGISTRY_ID||'').trim();
const ADOPTION_READ_STATEHEAD_ID=String(process.env.ND_ADOPTION_READ_STATEHEAD_ID||'').trim();
const ADOPTION_READ_BUNDLE_ID=String(process.env.ND_ADOPTION_READ_BUNDLE_ID||'').trim();
const ADOPTION_READ_EXTRA_IDS=String(process.env.ND_ADOPTION_READ_EXTRA_IDS||'').trim();
const ADOPTION_READ_REV=String(process.env.ND_ADOPTION_READ_REV||'').trim();
const ADOPTION_PROFILE_PROBE_REV=String(process.env.ND_ADOPTION_PROFILE_PROBE_REV||'').trim();
const ADOPTION_PROFILE_REGISTRY_ID=String(process.env.ND_ADOPTION_PROFILE_REGISTRY_ID||'').trim();
const ADOPTION_WHOLE_STATE_B64=String(process.env.ND_ADOPTION_WHOLE_STATE_B64||'').trim();
const ADOPTION_WHOLE_STATE_PROBE_REV=String(process.env.ND_ADOPTION_WHOLE_STATE_PROBE_REV||'').trim();
const ADOPTION_STATE_REFRESH_B64=String(process.env.ND_ADOPTION_STATE_REFRESH_B64||'').trim();
const ADOPTION_RECONSTRUCT_REV=String(process.env.ND_ADOPTION_RECONSTRUCT_REV||'').trim();
const ADOPTION_ALT_GOOGLE_CLIENT_EMAIL=String(process.env.ND_ADOPTION_ALT_GOOGLE_CLIENT_EMAIL||'').trim();
const ADOPTION_ALT_GOOGLE_PRIVATE_KEY_B64=String(process.env.ND_ADOPTION_ALT_GOOGLE_PRIVATE_KEY_B64||'').trim();
const ADOPTION_EXACT_REGISTRY_ID=String(process.env.ND_ADOPTION_EXACT_REGISTRY_ID||'').trim();
const ADOPTION_EXACT_REGISTRY_EXPECTED_SHA=String(process.env.ND_ADOPTION_EXACT_REGISTRY_EXPECTED_SHA||'').trim();
const ADOPTION_EXACT_REGISTRY_PROBE_REV=String(process.env.ND_ADOPTION_EXACT_REGISTRY_PROBE_REV||'').trim();
let adoptionAltGoogleTokenCache={token:'',exp:0};


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
async function adoptionAltGoogleAccessToken(){
  const now=Math.floor(Date.now()/1000);
  if(adoptionAltGoogleTokenCache.token && adoptionAltGoogleTokenCache.exp>now+60)return adoptionAltGoogleTokenCache.token;
  if(!ADOPTION_ALT_GOOGLE_CLIENT_EMAIL||!ADOPTION_ALT_GOOGLE_PRIVATE_KEY_B64)throw new Error('alt_google_credentials_missing');
  const pem=Buffer.from(ADOPTION_ALT_GOOGLE_PRIVATE_KEY_B64,'base64').toString('utf8');
  const header=b64url(JSON.stringify({alg:'RS256',typ:'JWT'}));
  const payload=b64url(JSON.stringify({
    iss:ADOPTION_ALT_GOOGLE_CLIENT_EMAIL,
    scope:'https://www.googleapis.com/auth/drive.readonly',
    aud:'https://oauth2.googleapis.com/token',
    iat:now,
    exp:now+3600
  }));
  const unsigned=header+'.'+payload;
  const signer=createSign('RSA-SHA256'); signer.update(unsigned); signer.end();
  const assertion=unsigned+'.'+b64url(signer.sign(pem));
  const body=new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion});
  const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body});
  const t=await r.text(); if(!r.ok)throw new Error('alt_google_token_http_'+r.status+':'+t.slice(0,300));
  const o=JSON.parse(t); if(!o.access_token)throw new Error('alt_google_access_token_missing');
  adoptionAltGoogleTokenCache={token:o.access_token,exp:now+Number(o.expires_in||3600)};
  return adoptionAltGoogleTokenCache.token;
}
async function adoptionAltDriveReadText(id){
  const token=await adoptionAltGoogleAccessToken();
  async function get(url){
    const r=await fetch(url,{headers:{authorization:'Bearer '+token}});
    const buf=Buffer.from(await r.arrayBuffer());
    if(!r.ok)throw new Error('alt_drive_http_'+r.status+':'+buf.toString('utf8').slice(0,500));
    return buf;
  }
  const mb=await get('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?fields=id,name,mimeType,parents,md5Checksum,size,modifiedTime,version');
  const meta=JSON.parse(mb.toString('utf8'));
  const data=await get('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?alt=media&supportsAllDrives=true');
  const text=data.toString('utf8');
  return {meta,text,sha256:sha256Text(text),bytes:data.length};
}
async function runAdoptionExactRegistryProbe(){
  if(!ADOPTION_EXACT_REGISTRY_PROBE_REV||!ADOPTION_EXACT_REGISTRY_ID)return;
  try{
    const r=await adoptionAltDriveReadText(ADOPTION_EXACT_REGISTRY_ID);
    const match=!ADOPTION_EXACT_REGISTRY_EXPECTED_SHA||r.sha256===ADOPTION_EXACT_REGISTRY_EXPECTED_SHA;
    const b64=Buffer.from(r.text,'utf8').toString('base64'), chunkSize=6000, total=Math.max(1,Math.ceil(b64.length/chunkSize));
    console.log('ND_ADOPTION_EXACT_REGISTRY_META',JSON.stringify({
      rev:ADOPTION_EXACT_REGISTRY_PROBE_REV,ok:match,sha256:r.sha256,expected_sha256:ADOPTION_EXACT_REGISTRY_EXPECTED_SHA||null,
      bytes:r.bytes,total,meta:r.meta
    }));
    if(!match)throw new Error('exact_registry_sha_mismatch');
    for(let i=0;i<total;i++)console.log('ND_ADOPTION_EXACT_REGISTRY_CHUNK',JSON.stringify({
      rev:ADOPTION_EXACT_REGISTRY_PROBE_REV,index:i,total,data:b64.slice(i*chunkSize,(i+1)*chunkSize)
    }));
    const obj=JSON.parse(r.text.replace(/^\uFEFF/,''));
    console.log('ND_ADOPTION_EXACT_REGISTRY_DONE',JSON.stringify({
      rev:ADOPTION_EXACT_REGISTRY_PROBE_REV,ok:true,version:obj.version,component_count:(obj.components||[]).length
    }));
  }catch(e){
    console.error('ND_ADOPTION_EXACT_REGISTRY_DONE',JSON.stringify({rev:ADOPTION_EXACT_REGISTRY_PROBE_REV,ok:false,error:cleanErr(e)}));
  }
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
async function runAdoptionReadProbe(){
  if(!ADOPTION_READ_REV)return;
  const logChunks=(kind,text,meta={})=>{
    const b64=Buffer.from(String(text),'utf8').toString('base64');
    const chunkSize=6000;
    const total=Math.max(1,Math.ceil(b64.length/chunkSize));
    console.log('ND_ADOPTION_READ_META',JSON.stringify({rev:ADOPTION_READ_REV,kind,total,...meta}));
    for(let i=0;i<total;i++){
      console.log('ND_ADOPTION_READ_CHUNK',JSON.stringify({rev:ADOPTION_READ_REV,kind,index:i,total,data:b64.slice(i*chunkSize,(i+1)*chunkSize)}));
    }
  };
  const results={};
  if(ADOPTION_READ_REGISTRY_ID){
    try{
      const registry=await driveReadText(ADOPTION_READ_REGISTRY_ID);
      logChunks('registry',registry.text,{sha256:registry.sha256,bytes:registry.bytes,meta:registry.meta});
      results.registry='ok';
    }catch(e){results.registry=cleanErr(e);console.error('ND_ADOPTION_READ_ITEM',JSON.stringify({rev:ADOPTION_READ_REV,kind:'registry',ok:false,error:cleanErr(e)}));}
  }
  if(ADOPTION_READ_BUNDLE_ID){
    try{
      const bundle=await driveReadText(ADOPTION_READ_BUNDLE_ID);
      logChunks('bundle',bundle.text,{sha256:bundle.sha256,bytes:bundle.bytes,meta:bundle.meta});
      results.bundle='ok';
    }catch(e){results.bundle=cleanErr(e);console.error('ND_ADOPTION_READ_ITEM',JSON.stringify({rev:ADOPTION_READ_REV,kind:'bundle',ok:false,error:cleanErr(e)}));}
  }
  if(ADOPTION_READ_EXTRA_IDS){
    for(const pair of ADOPTION_READ_EXTRA_IDS.split(';').map(x=>x.trim()).filter(Boolean)){
      const eq=pair.indexOf('=');
      if(eq<1)continue;
      const label=pair.slice(0,eq).replace(/[^a-zA-Z0-9_.-]/g,'_');
      const id=pair.slice(eq+1).trim();
      try{
        const extra=await driveReadText(id);
        logChunks('extra:'+label,extra.text,{sha256:extra.sha256,bytes:extra.bytes,meta:extra.meta});
        results['extra:'+label]='ok';
      }catch(e){
        results['extra:'+label]=cleanErr(e);
        console.error('ND_ADOPTION_READ_ITEM',JSON.stringify({rev:ADOPTION_READ_REV,kind:'extra:'+label,ok:false,error:cleanErr(e)}));
      }
    }
  }
  if(ADOPTION_READ_STATEHEAD_ID){
    try{
      const head=await docsRead(ADOPTION_READ_STATEHEAD_ID);
      logChunks('statehead',head.text,{documentId:head.documentId,title:head.title,revisionId:head.revisionId,sha256:sha256Text(head.text),chars:head.text.length});
      results.statehead='ok';
    }catch(e){results.statehead=cleanErr(e);console.error('ND_ADOPTION_READ_ITEM',JSON.stringify({rev:ADOPTION_READ_REV,kind:'statehead',ok:false,error:cleanErr(e)}));}
  }
  console.log('ND_ADOPTION_READ_DONE',JSON.stringify({rev:ADOPTION_READ_REV,ok:Object.values(results).some(x=>x==='ok'),results}));
}

async function runAdoptionProfileProbe(){
  if(!ADOPTION_PROFILE_PROBE_REV||!ADOPTION_PROFILE_REGISTRY_ID)return;
  try{
    const reg=await driveReadText(ADOPTION_PROFILE_REGISTRY_ID);
    const obj=JSON.parse(reg.text.replace(/^\uFEFF/,''));
    const keys=(obj.components||[]).map(x=>x.component_key);
    const wanted=['TRUE_RESEARCH','RESEARCH_INTEROP','TRUE_WRITER','BOOKS_CREATOR','SYSTEM','TRUE_MEMORY'];
    const profiles={};
    for(const k of wanted){
      const p=(obj.components||[]).find(x=>x.component_key===k);
      if(p)profiles[k]=p;
    }
    console.log('ND_ADOPTION_PROFILE_PROBE',JSON.stringify({
      rev:ADOPTION_PROFILE_PROBE_REV,
      registry_sha256:reg.sha256,
      registry_version:obj.version,
      component_count:(obj.components||[]).length,
      component_keys:keys,
      profiles
    }));
  }catch(e){
    console.error('ND_ADOPTION_PROFILE_PROBE',JSON.stringify({rev:ADOPTION_PROFILE_PROBE_REV,ok:false,error:cleanErr(e)}));
  }
}

function findObjectsByPredicate(root,pred){
  const out=[]; const seen=new Set();
  const walk=(v,path)=>{
    if(!v||typeof v!=='object'||seen.has(v))return;
    seen.add(v);
    try{ if(pred(v,path)) out.push({path,value:v}); }catch{}
    if(Array.isArray(v)){ for(let i=0;i<v.length;i++) walk(v[i],path+'['+i+']'); }
    else for(const [k,x] of Object.entries(v)) walk(x,path?path+'.'+k:k);
  };
  walk(root,'');
  return out;
}
async function runAdoptionWholeStateProbe(){
  if(!ADOPTION_WHOLE_STATE_PROBE_REV||!ADOPTION_WHOLE_STATE_B64)return;
  try{
    const text=Buffer.from(ADOPTION_WHOLE_STATE_B64,'base64').toString('utf8');
    let obj; try{obj=JSON.parse(text.replace(/^\uFEFF/,''));}catch{obj=null;}
    const summary={rev:ADOPTION_WHOLE_STATE_PROBE_REV,bytes:Buffer.byteLength(text,'utf8'),sha256:sha256Text(text),json:Boolean(obj)};
    if(!obj){
      summary.preview=text.slice(0,1000);
      console.log('ND_ADOPTION_WHOLE_STATE_PROBE',JSON.stringify(summary));
      return;
    }
    const registries=findObjectsByPredicate(obj,(v)=>Array.isArray(v.components)&&typeof v.version==='string'&&v.components.some(x=>x&&x.component_key));
    const registry=registries.find(x=>x.value.version==='1.13.0')||registries[0]||null;
    if(registry){
      const wanted=['TRUE_RESEARCH','RESEARCH_INTEROP','TRUE_WRITER','BOOKS_CREATOR','LITERARY_CRITIC','STORY_ARCHITECT','TECHNICAL_WRITER'];
      const profiles={};
      for(const k of wanted){const p=registry.value.components.find(x=>x&&x.component_key===k);if(p)profiles[k]=p;}
      summary.registry={path:registry.path,version:registry.value.version,registry_id:registry.value.registry_id||null,component_count:registry.value.components.length,profiles};
    }
    const refs=findObjectsByPredicate(obj,(v)=>Object.values(v).some(x=>typeof x==='string'&&(
      x.includes('16TCMHEb9erk4rONK9poi6-62hNfSELKt')||
      x==='ND_CAPABILITY_REGISTRY'||
      x==='ND-SKILL-WRITER-1'||
      x==='ND-SKILL-BOOKS-1'
    ))).slice(0,25);
    summary.refs=refs;
    console.log('ND_ADOPTION_WHOLE_STATE_PROBE',JSON.stringify(summary));
  }catch(e){
    console.error('ND_ADOPTION_WHOLE_STATE_PROBE',JSON.stringify({rev:ADOPTION_WHOLE_STATE_PROBE_REV,ok:false,error:cleanErr(e)}));
  }
}

async function runAdoptionReconstructProbe(){
  if(!ADOPTION_RECONSTRUCT_REV)return;
  const out={rev:ADOPTION_RECONSTRUCT_REV};
  try{
    if(ADOPTION_PROFILE_REGISTRY_ID){
      const reg=await driveReadText(ADOPTION_PROFILE_REGISTRY_ID);
      const obj=JSON.parse(reg.text.replace(/^\uFEFF/,''));
      const pretty=JSON.stringify(obj,null,2)+'\n';
      const prettyNoNl=JSON.stringify(obj,null,2);
      out.serialization={
        original_sha256:reg.sha256,
        pretty_lf_sha256:sha256Text(pretty),
        pretty_no_final_nl_sha256:sha256Text(prettyNoNl),
        original_bytes:reg.bytes,
        pretty_bytes:Buffer.byteLength(pretty,'utf8'),
        pretty_no_final_nl_bytes:Buffer.byteLength(prettyNoNl,'utf8')
      };
    }
    if(ADOPTION_STATE_REFRESH_B64){
      const script=Buffer.from(ADOPTION_STATE_REFRESH_B64,'base64').toString('utf8');
      out.state_refresh_sha256=sha256Text(script);
      out.state_refresh_bytes=Buffer.byteLength(script,'utf8');
      const terms=['TRUE_RESEARCH','RESEARCH_INTEROP','1.13.0','1.4.4','1.4.0','GOVERNING_RESEARCH_CORE'];
      out.snippets={};
      for(const term of terms){
        const hits=[]; let p=0;
        while((p=script.indexOf(term,p))>=0 && hits.length<12){
          hits.push(script.slice(Math.max(0,p-1200),Math.min(script.length,p+2800)));
          p+=term.length;
        }
        out.snippets[term]=hits;
      }
    }
    console.log('ND_ADOPTION_RECONSTRUCT_PROBE',JSON.stringify(out));
  }catch(e){
    console.error('ND_ADOPTION_RECONSTRUCT_PROBE',JSON.stringify({rev:ADOPTION_RECONSTRUCT_REV,ok:false,error:cleanErr(e)}));
  }
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


const LP_TOOLS=[
  {name:"lightpanda_status",description:"Check the ND Lightpanda Cloud adapter configuration without opening a browser session.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:RO},
  {name:"lightpanda_fetch",description:"Render a public HTTP(S) page with Lightpanda Cloud and return post-JavaScript HTML or Markdown without keeping an interactive session open.",inputSchema:{type:"object",properties:{url:{type:"string",minLength:8},output_format:{type:"string",enum:["markdown","html"],default:"markdown"},wait_ms:{type:"integer",minimum:1,maximum:60000,default:5000},wait_event:{type:"string",enum:["DOMContentLoaded","load","networkAlmostIdle","networkIdle"],default:"networkIdle"},proxy_name:{type:"string",enum:["fast_dc","datacenter"],default:"fast_dc"},country:{type:"string",minLength:2,maxLength:2}},required:["url"],additionalProperties:false},annotations:RO},
  {name:"lightpanda_goto",description:"Open a URL in a stateful Lightpanda Cloud browser session. The session is retained briefly across subsequent interaction calls.",inputSchema:{type:"object",properties:{url:{type:"string",minLength:8},wait_until:{type:"string",enum:["load","domcontentloaded","networkidle","commit"],default:"domcontentloaded"},timeout_ms:{type:"integer",minimum:1000,maximum:90000,default:30000}},required:["url"],additionalProperties:false},annotations:RO},
  {name:"lightpanda_get_url",description:"Return the current URL and title of the active Lightpanda browser page.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:RO},
  {name:"lightpanda_read_text",description:"Read visible text from the current page or a CSS selector.",inputSchema:{type:"object",properties:{selector:{type:"string",default:"body"},max_chars:{type:"integer",minimum:1,maximum:100000,default:30000}},additionalProperties:false},annotations:RO},
  {name:"lightpanda_html",description:"Return HTML for the current document or a selected element.",inputSchema:{type:"object",properties:{selector:{type:"string"},max_chars:{type:"integer",minimum:1,maximum:200000,default:60000}},additionalProperties:false},annotations:RO},
  {name:"lightpanda_click",description:"Click an element in the active Lightpanda browser page using a CSS selector.",inputSchema:{type:"object",properties:{selector:{type:"string"},timeout_ms:{type:"integer",minimum:1000,maximum:60000,default:15000}},required:["selector"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_fill",description:"Fill a text input or textarea in the active Lightpanda browser page.",inputSchema:{type:"object",properties:{selector:{type:"string"},value:{type:"string"},timeout_ms:{type:"integer",minimum:1000,maximum:60000,default:15000}},required:["selector","value"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_press",description:"Press a keyboard key on the active page or on a selected element.",inputSchema:{type:"object",properties:{key:{type:"string"},selector:{type:"string"},timeout_ms:{type:"integer",minimum:1000,maximum:60000,default:15000}},required:["key"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_hover",description:"Hover over an element in the active Lightpanda browser page.",inputSchema:{type:"object",properties:{selector:{type:"string"},timeout_ms:{type:"integer",minimum:1000,maximum:60000,default:15000}},required:["selector"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_select_option",description:"Select a value from a select element in the active page.",inputSchema:{type:"object",properties:{selector:{type:"string"},value:{type:"string"},timeout_ms:{type:"integer",minimum:1000,maximum:60000,default:15000}},required:["selector","value"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_set_checked",description:"Check or uncheck a checkbox/radio input in the active page.",inputSchema:{type:"object",properties:{selector:{type:"string"},checked:{type:"boolean"},timeout_ms:{type:"integer",minimum:1000,maximum:60000,default:15000}},required:["selector","checked"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_wait_for_selector",description:"Wait until a CSS selector appears in the active page.",inputSchema:{type:"object",properties:{selector:{type:"string"},timeout_ms:{type:"integer",minimum:1000,maximum:90000,default:30000}},required:["selector"],additionalProperties:false},annotations:RO},
  {name:"lightpanda_evaluate",description:"Evaluate JavaScript in the active page and return the JSON-serializable result.",inputSchema:{type:"object",properties:{script:{type:"string",minLength:1}},required:["script"],additionalProperties:false},annotations:WR},
  {name:"lightpanda_get_cookies",description:"Read cookies from the active Lightpanda browser context, optionally scoped to a URL.",inputSchema:{type:"object",properties:{url:{type:"string"}},additionalProperties:false},annotations:RO}
]

function lightpandaStatus(){
  return {
    ok:Boolean(LIGHTPANDA_TOKEN&&LIGHTPANDA_PATH_TOKEN),
    service:"nd-lightpanda-cloud-mcp",
    transport:"streamable-http",
    provider:"Lightpanda Cloud",
    provider_transport:"CDP/WebSocket via Playwright + HTTP fetch",
    code_rev:ND_LIGHTPANDA_MUX_CODE_REV,
    tools:LP_TOOLS.length
  };
}

async function lightpandaFetch(a={}){
  if(!LIGHTPANDA_TOKEN)throw new Error("lightpanda_token_missing");
  let u;
  try{u=new URL(String(a.url||""));}catch{throw new Error("invalid_url");}
  if(!["http:","https:"].includes(u.protocol))throw new Error("url_must_be_http_or_https");
  const output_format=["markdown","html"].includes(String(a.output_format||"markdown"))?String(a.output_format||"markdown"):"markdown";
  const wait_ms=Math.max(1,Math.min(60000,Number(a.wait_ms||5000)));
  const wait_event=["DOMContentLoaded","load","networkAlmostIdle","networkIdle"].includes(String(a.wait_event||"networkIdle"))?String(a.wait_event||"networkIdle"):"networkIdle";
  const proxy_name=["fast_dc","datacenter"].includes(String(a.proxy_name||"fast_dc"))?String(a.proxy_name||"fast_dc"):"fast_dc";
  const body={url:u.toString(),output_format,wait_ms,wait_event,raw:false,proxy_name};
  if(proxy_name==="datacenter"&&a.country)body.country=String(a.country).toLowerCase();
  const r=await fetch(LIGHTPANDA_API,{
    method:"POST",
    headers:{authorization:"Bearer "+LIGHTPANDA_TOKEN,"content-type":"application/json",accept:"application/json"},
    body:JSON.stringify(body)
  });
  const t=await r.text();
  let d={};try{d=t?JSON.parse(t):{};}catch{d={data:t};}
  if(!r.ok)throw new Error("lightpanda_http_"+r.status+":"+String(d?.error||d?.message||t).slice(0,800));
  return {
    ok:true,
    url:u.toString(),
    output_format,
    status:Number(d.status||0),
    data:String(d.data||"").slice(0,250000),
    truncated:String(d.data||"").length>250000,
    headers:d.headers||{}
  };
}

let lpCdp={browser:null,context:null,page:null,connecting:null,idleTimer:null,lastError:"",stage:"idle"};
async function lpStage(label,promise,ms=10000){
  lpCdp.stage=label;
  let timer;
  try{
    return await Promise.race([
      promise,
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error("lightpanda_stage_timeout:"+label)),ms);})
    ]);
  }finally{if(timer)clearTimeout(timer);}
}
function lpCdpTouch(){
  if(lpCdp.idleTimer)clearTimeout(lpCdp.idleTimer);
  lpCdp.idleTimer=setTimeout(async()=>{
    try{if(lpCdp.browser)await lpCdp.browser.close();}catch{}
    lpCdp={browser:null,context:null,page:null,connecting:null,idleTimer:null,lastError:""};
  },120000);
}
async function ensureLpCdp(){
  if(lpCdp.browser&&lpCdp.page){
    lpCdpTouch();
    return lpCdp;
  }
  if(lpCdp.connecting)return await lpCdp.connecting;
  lpCdp.connecting=(async()=>{
    if(!LIGHTPANDA_TOKEN)throw new Error("lightpanda_token_missing");
    const browser=await lpStage("connectOverCDP",chromium.connectOverCDP(LIGHTPANDA_CDP_URL,{timeout:9000}),10000);
    browser.on("disconnected",()=>{lpCdp.browser=null;lpCdp.context=null;lpCdp.page=null;lpCdp.connecting=null;lpCdp.stage="disconnected";});
    const context=await lpStage("newContext",browser.newContext(),10000);
    const page=await lpStage("newPage",context.newPage(),10000);
    lpCdp.browser=browser;lpCdp.context=context;lpCdp.page=page;lpCdp.lastError="";lpCdp.connecting=null;lpCdp.stage="ready";
    lpCdpTouch();
    return lpCdp;
  })().catch(e=>{
    lpCdp.connecting=null;lpCdp.lastError=String(e?.message||e||"cdp_connect_error");
    throw e;
  });
  return await lpCdp.connecting;
}
function lpTimeout(a,def=15000,max=90000){return Math.max(1000,Math.min(max,Number(a?.timeout_ms||def)));}
async function lpCdpCall(name,a={}){
  const st=await ensureLpCdp();const page=st.page;lpCdpTouch();
  if(name==="lightpanda_goto"){
    let u;try{u=new URL(String(a.url||""));}catch{throw new Error("invalid_url");}
    if(!["http:","https:"].includes(u.protocol))throw new Error("url_must_be_http_or_https");
    const waitUntil=["load","domcontentloaded","networkidle","commit"].includes(String(a.wait_until||"domcontentloaded"))?String(a.wait_until||"domcontentloaded"):"domcontentloaded";
    const response=await page.goto(u.toString(),{waitUntil,timeout:lpTimeout(a,30000,90000)});
    return {ok:true,url:page.url(),title:await page.title(),status:response?response.status():null};
  }
  if(name==="lightpanda_get_url")return {ok:true,url:page.url(),title:await page.title()};
  if(name==="lightpanda_read_text"){
    const selector=String(a.selector||"body"),max=Math.max(1,Math.min(100000,Number(a.max_chars||30000)));
    const text=await page.locator(selector).innerText({timeout:15000});
    return {ok:true,url:page.url(),selector,text:String(text).slice(0,max),truncated:String(text).length>max};
  }
  if(name==="lightpanda_html"){
    const max=Math.max(1,Math.min(200000,Number(a.max_chars||60000)));
    const html=a.selector?await page.locator(String(a.selector)).evaluate(el=>el.outerHTML):await page.content();
    return {ok:true,url:page.url(),html:String(html).slice(0,max),truncated:String(html).length>max};
  }
  if(name==="lightpanda_click"){
    await page.locator(String(a.selector||"")).click({timeout:lpTimeout(a)});
    return {ok:true,url:page.url(),title:await page.title()};
  }
  if(name==="lightpanda_fill"){
    await page.locator(String(a.selector||"")).fill(String(a.value??""),{timeout:lpTimeout(a)});
    return {ok:true,url:page.url(),selector:String(a.selector),value:String(a.value??"")};
  }
  if(name==="lightpanda_press"){
    const target=a.selector?page.locator(String(a.selector)):page.locator("body");
    await target.press(String(a.key||""),{timeout:lpTimeout(a)});
    return {ok:true,url:page.url(),key:String(a.key||"")};
  }
  if(name==="lightpanda_hover"){
    await page.locator(String(a.selector||"")).hover({timeout:lpTimeout(a)});
    return {ok:true,url:page.url(),selector:String(a.selector)};
  }
  if(name==="lightpanda_select_option"){
    const selected=await page.locator(String(a.selector||"")).selectOption(String(a.value??""),{timeout:lpTimeout(a)});
    return {ok:true,url:page.url(),selected};
  }
  if(name==="lightpanda_set_checked"){
    await page.locator(String(a.selector||"")).setChecked(Boolean(a.checked),{timeout:lpTimeout(a)});
    return {ok:true,url:page.url(),checked:Boolean(a.checked)};
  }
  if(name==="lightpanda_wait_for_selector"){
    await page.locator(String(a.selector||"")).waitFor({state:"attached",timeout:lpTimeout(a,30000,90000)});
    return {ok:true,url:page.url(),selector:String(a.selector)};
  }
  if(name==="lightpanda_evaluate"){
    const value=await page.evaluate(String(a.script||""));
    return {ok:true,url:page.url(),value};
  }
  if(name==="lightpanda_get_cookies"){
    const cookies=a.url?await st.context.cookies(String(a.url)):await st.context.cookies();
    return {ok:true,url:page.url(),cookies};
  }
  throw new Error("unknown_lightpanda_cdp_tool:"+String(name));
}

async function lpProcessSse(reader){
  const decoder=new TextDecoder();
  let buf="";
  try{
    while(true){
      const {value,done}=await reader.read();
      if(done)break;
      buf+=decoder.decode(value,{stream:true}).replace(/\r\n/g,"\n");
      while(true){
        const cut=buf.indexOf("\n\n");
        if(cut<0)break;
        const block=buf.slice(0,cut);buf=buf.slice(cut+2);
        let event="",data=[];
        for(const line of block.split("\n")){
          if(line.startsWith("event:"))event=line.slice(6).trim();
          else if(line.startsWith("data:"))data.push(line.slice(5).trimStart());
        }
        const payload=data.join("\n").trim();
        if(!payload)continue;
        if(event==="endpoint"){
          try{lpUpstream.postUrl=new URL(payload,LIGHTPANDA_MCP_SSE).toString();}catch{}
          continue;
        }
        if(event==="message"||!event){
          let msg;try{msg=JSON.parse(payload);}catch{continue;}
          const key=String(msg?.id??"");
          const p=lpUpstream.pending.get(key);
          if(p){lpUpstream.pending.delete(key);p.resolve(msg);}
        }
      }
    }
  }catch(e){
    lpUpstream.lastError=String(e?.message||e||"sse_read_error");
  }finally{
    for(const p of lpUpstream.pending.values())p.reject(new Error("lightpanda_sse_closed"));
    lpUpstream.pending.clear();
    lpUpstream.reader=null;lpUpstream.postUrl="";lpUpstream.ready=false;lpUpstream.connecting=null;
  }
}

async function lpPost(msg){
  if(!lpUpstream.postUrl)throw new Error("lightpanda_upstream_endpoint_missing");
  const r=await fetch(lpUpstream.postUrl,{
    method:"POST",
    headers:{authorization:"Bearer "+LIGHTPANDA_TOKEN,"content-type":"application/json",accept:"application/json,text/event-stream"},
    body:JSON.stringify(msg)
  });
  if(!r.ok){
    const t=await r.text();
    throw new Error("lightpanda_upstream_post_"+r.status+":"+t.slice(0,500));
  }
}

async function lpRpc(method,params={},timeoutMs=45000){
  await ensureLpUpstream();
  const id=++lpUpstream.seq;
  const msg={jsonrpc:"2.0",id,method,params};
  const reply=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{
      lpUpstream.pending.delete(String(id));
      reject(new Error("lightpanda_upstream_timeout:"+method));
    },timeoutMs);
    lpUpstream.pending.set(String(id),{
      resolve:(v)=>{clearTimeout(timer);resolve(v);},
      reject:(e)=>{clearTimeout(timer);reject(e);}
    });
  });
  await lpPost(msg);
  const out=await reply;
  if(out?.error)throw new Error("lightpanda_upstream_rpc_"+String(out.error?.code||"")+":"+String(out.error?.message||"error"));
  return out;
}

async function ensureLpUpstream(){
  if(lpUpstream.ready&&lpUpstream.reader&&lpUpstream.postUrl)return;
  if(lpUpstream.connecting)return await lpUpstream.connecting;
  lpUpstream.connecting=(async()=>{
    if(!LIGHTPANDA_TOKEN)throw new Error("lightpanda_token_missing");
    const r=await fetch(LIGHTPANDA_MCP_SSE,{
      method:"GET",
      headers:{authorization:"Bearer "+LIGHTPANDA_TOKEN,accept:"text/event-stream"},
      signal:AbortSignal.timeout(30000)
    });
    if(!r.ok)throw new Error("lightpanda_sse_http_"+r.status+":"+String(await r.text()).slice(0,500));
    if(!r.body)throw new Error("lightpanda_sse_body_missing");
    lpUpstream.reader=r.body.getReader();
    void lpProcessSse(lpUpstream.reader);
    const started=Date.now();
    while(!lpUpstream.postUrl&&Date.now()-started<10000)await new Promise(x=>setTimeout(x,50));
    if(!lpUpstream.postUrl)throw new Error("lightpanda_sse_endpoint_event_timeout");

    const id=++lpUpstream.seq;
    const initPromise=new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{lpUpstream.pending.delete(String(id));reject(new Error("lightpanda_initialize_timeout"));},15000);
      lpUpstream.pending.set(String(id),{
        resolve:(v)=>{clearTimeout(timer);resolve(v);},
        reject:(e)=>{clearTimeout(timer);reject(e);}
      });
    });
    await lpPost({
      jsonrpc:"2.0",id,method:"initialize",
      params:{protocolVersion:"2024-11-05",capabilities:{},clientInfo:{name:"nd-lightpanda-streamable-bridge",version:"2.0.0"}}
    });
    const init=await initPromise;
    if(init?.error)throw new Error("lightpanda_initialize_failed:"+String(init.error?.message||"error"));
    await lpPost({jsonrpc:"2.0",method:"notifications/initialized",params:{}});
    lpUpstream.ready=true;
    lpUpstream.lastError="";
  })().catch(e=>{
    lpUpstream.reader=null;lpUpstream.postUrl="";lpUpstream.ready=false;lpUpstream.connecting=null;
    lpUpstream.lastError=String(e?.message||e||"connect_error");
    throw e;
  });
  try{return await lpUpstream.connecting;}
  finally{if(lpUpstream.ready)lpUpstream.connecting=null;}
}

async function lpNativeTools(){
  const out=await lpRpc("tools/list",{});
  return Array.isArray(out?.result?.tools)?out.result.tools:[];
}

async function lightpandaCallTool(name,args){
  if(name==="lightpanda_status"){
    return {...lightpandaStatus(),cdp_configured:Boolean(LIGHTPANDA_TOKEN),cdp_active:Boolean(lpCdp.browser&&lpCdp.page),cdp_last_error:lpCdp.lastError||null,native_sse_status:"provider_endpoint_404"};
  }
  if(name==="lightpanda_fetch")return await lightpandaFetch(args||{});
  if(LP_TOOLS.some(x=>x.name===name))return await lpCdpCall(name,args||{});
  throw new Error("unknown_lightpanda_tool:"+String(name));
}

async function lightpandaMcp(req,res){
  let msg;
  try{msg=JSON.parse(await readBody(req)||"{}");}
  catch{return j(res,400,{jsonrpc:"2.0",id:null,error:{code:-32700,message:"parse error"}});}
  const id=msg.id,method=String(msg.method||"");
  if(method==="notifications/initialized"){res.writeHead(204);return res.end();}
  if(method==="initialize")return j(res,200,{jsonrpc:"2.0",id,result:{
    protocolVersion:"2025-06-18",
    capabilities:{tools:{listChanged:false}},
    serverInfo:{name:"nd-lightpanda-cloud-mcp",version:"1.0.0"},
    instructions:"Nameless Dhamma Lightpanda Cloud browser adapter. Read/fetch and stateful browser-control tools are exposed through Streamable HTTP; interactive sessions auto-close after 120 seconds of inactivity to conserve the free quota."
  }});
  if(method==="ping")return j(res,200,{jsonrpc:"2.0",id,result:{}});
  if(method==="tools/list")return j(res,200,{jsonrpc:"2.0",id,result:{tools:LP_TOOLS}});
  if(method==="resources/list"||method==="resources/read"){
    try{
      const out=await lpRpc(method,msg.params||{},60000);
      return j(res,200,{jsonrpc:"2.0",id,result:out?.result||{}});
    }catch(e){
      return j(res,200,{jsonrpc:"2.0",id,error:{code:-32000,message:"Lightpanda upstream resource error"}});
    }
  }
  if(method==="tools/call"){
    const p=msg.params||{};
    try{
      const name=String(p.name||"");
      if(LP_TOOLS.some(x=>x.name===name)){
        const out=await lightpandaCallTool(name,p.arguments||{});
        return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:false}});
      }
      return j(res,200,{jsonrpc:"2.0",id,error:{code:-32601,message:"Unknown Lightpanda tool"}});
    }catch(e){
      let err=String(e?.message||e||"error");
      if(LIGHTPANDA_TOKEN)err=err.split(LIGHTPANDA_TOKEN).join("[REDACTED]");
      if(LIGHTPANDA_PATH_TOKEN)err=err.split(LIGHTPANDA_PATH_TOKEN).join("[REDACTED]");
      const out={ok:false,error:err.slice(0,1800)};
      return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:true}});
    }
  }
  return j(res,200,{jsonrpc:"2.0",id,error:{code:-32601,message:"Method not found"}});
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
        youtube:{configured:Boolean(YT_CLIENT_ID&&YT_CLIENT_SECRET&&YT_REFRESH_TOKEN&&YT_PATH_TOKEN),writes:YT_WRITES,tools:YT_TOOLS.length},
        lightpanda:{configured:Boolean(LIGHTPANDA_TOKEN&&LIGHTPANDA_PATH_TOKEN),tools:LP_TOOLS.length,code_rev:ND_LIGHTPANDA_MUX_CODE_REV,cdp_stage:lpCdp.stage,cdp_active:Boolean(lpCdp.browser&&lpCdp.page),cdp_last_error:String(lpCdp.lastError||"").slice(0,300)}
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

    if(path==='/lightpanda/diagnostic'){
      try{
        const st=await ensureLpCdp();
        return j(res,200,{ok:true,code_rev:ND_LIGHTPANDA_MUX_CODE_REV,cdp_connected:true,stage:lpCdp.stage,url:st.page.url(),tools:LP_TOOLS.length,idle_close_seconds:120});
      }catch(e){
        let err=String(e?.message||e||"error");
        if(LIGHTPANDA_TOKEN)err=err.split(LIGHTPANDA_TOKEN).join("[REDACTED]");
        if(LIGHTPANDA_PATH_TOKEN)err=err.split(LIGHTPANDA_PATH_TOKEN).join("[REDACTED]");
        return j(res,200,{ok:false,code_rev:ND_LIGHTPANDA_MUX_CODE_REV,cdp_connected:false,stage:lpCdp.stage,error:err.slice(0,1200)});
      }
    }

    if(path==='/lightpanda/qualification'){
      const stages=[];
      try{
        const st=await lpStage("qual_connect",ensureLpCdp(),12000);
        const page=st.page;
        stages.push({stage:"connect",ok:true,url:page.url()});

        const nav=await lpStage("qual_external_goto",page.goto("https://namelessdhamma.org/tmp/lightpanda-qualification.html",{waitUntil:"domcontentloaded",timeout:15000}),17000);
        stages.push({stage:"external_goto",ok:true,status:nav?nav.status():null,url:page.url()});

        const heading=await lpStage("qual_external_read",page.locator("#heading").innerText({timeout:6000}),7000);
        stages.push({stage:"external_read",ok:heading==="ND Lightpanda Qualification",heading});

        await lpStage("qual_fill",page.locator("#q").fill("ND-LIGHTPANDA-QUAL",{timeout:6000}),7000);
        const value=await lpStage("qual_fill_readback",page.locator("#q").inputValue({timeout:6000}),7000);
        stages.push({stage:"fill_readback",ok:value==="ND-LIGHTPANDA-QUAL",value_match:value==="ND-LIGHTPANDA-QUAL"});

        await lpStage("qual_click",page.locator("#go").click({timeout:6000}),7000);
        const resultText=await lpStage("qual_click_readback",page.locator("#out").innerText({timeout:6000}),7000);
        stages.push({stage:"click_readback",ok:resultText==="ND-LIGHTPANDA-QUAL-CLICKED",result:resultText});

        return j(res,200,{
          ok:stages.every(x=>x.ok!==false),
          code_rev:ND_LIGHTPANDA_MUX_CODE_REV,
          engine:"lightpanda",
          stages,
          final_url:page.url()
        });
      }catch(e){
        let err=String(e?.message||e||"error");
        if(LIGHTPANDA_TOKEN)err=err.split(LIGHTPANDA_TOKEN).join("[REDACTED]");
        if(LIGHTPANDA_PATH_TOKEN)err=err.split(LIGHTPANDA_PATH_TOKEN).join("[REDACTED]");
        return j(res,200,{ok:false,code_rev:ND_LIGHTPANDA_MUX_CODE_REV,engine:"lightpanda",stage:lpCdp.stage,error:err.slice(0,1200),stages});
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
        youtube_read_write:YT_WRITES,
        lightpanda_mcp_configured:Boolean(LIGHTPANDA_MCP_PATH)
      };
      const raw=Buffer.from(JSON.stringify(body));
      res.writeHead(200,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});
      res.end(raw);return;
    }

    if(LIGHTPANDA_MCP_PATH && path===LIGHTPANDA_MCP_PATH){
      if(req.method==='GET') return j(res,200,{ok:true,service:'nd-lightpanda-cloud-mcp',transport:'streamable-http',methods:['POST'],tools:LP_TOOLS.length,code_rev:ND_LIGHTPANDA_MUX_CODE_REV});
      if(req.method!=='POST'){res.writeHead(405,{Allow:'POST','content-length':'0'});res.end();return;}
      return await lightpandaMcp(req,res);
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
setTimeout(runAdoptionReadProbe,3000);
setTimeout(runAdoptionProfileProbe,4500);
setTimeout(runAdoptionWholeStateProbe,6000);
setTimeout(runAdoptionReconstructProbe,7500);
setTimeout(runAdoptionExactRegistryProbe,9000);