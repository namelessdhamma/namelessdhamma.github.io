import http from 'node:http';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { AsyncLocalStorage } from 'node:async_hooks';

// ND Music Studio: private Kaggle GPU bridge. Render holds no GPU, no job database,
// no lyrics, and no persistent files. Kaggle's private kernels are the job ledger.
const VERSION='0.1.4-video-readonly-admission';
const MAX_BODY=300_000;
const TMO=22_000;
const TOTAL_CONTROL_BUDGET=45_000;
const deadlineScope=new AsyncLocalStorage();
function controlBudget(){const d=deadlineScope.getStore();const remain=d===undefined?TMO:d-Date.now();if(remain<=0)throw error('CONTROL_DEADLINE_OUTCOME_UNKNOWN',504);return Math.min(remain,TMO);}
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const slugFor=(key,script)=>'nd-ace15-'+sha(String(key)+'\n'+sha(script)).slice(0,22);
const states={0:'QUEUED',1:'RUNNING',2:'COMPLETED',3:'FAILED',4:'CANCEL_REQUESTED',5:'CANCELLED',6:'NEW_SCRIPT'};
const stateOf=x=>{
 if((typeof x==='number'||(typeof x==='string'&&x.trim()!==''&&Number.isInteger(Number(x))))&&Object.hasOwn(states,Number(x)))return states[Number(x)];
 const raw=String(x??'').trim().toUpperCase();
 const val=raw.split('.').pop();
 const canonical={COMPLETE:'COMPLETED',COMPLETED:'COMPLETED',ERROR:'FAILED',FAILED:'FAILED',FAILURE:'FAILED',CANCELLED:'CANCELLED',CANCELED:'CANCELLED',CANCEL_ACKNOWLEDGED:'CANCELLED',CANCEL_REQUESTED:'CANCEL_REQUESTED',CANCELLING:'CANCEL_REQUESTED',RUNNING:'RUNNING',QUEUED:'QUEUED',PENDING:'QUEUED',NEW_SCRIPT:'NEW_SCRIPT'};
 return canonical[val]||'UNKNOWN';
};
const secs=v=>typeof v==='number'?v:typeof v==='string'?Number(v.replace(/s$/,''))||0:v&&typeof v==='object'?Number(v.seconds||0)+Number(v.nanos||0)/1e9:0;
const isAsciiSlug=s=>typeof s==='string'&&/^[a-z0-9][a-z0-9-]{4,100}$/.test(s);
function response(res,status,data){const b=JSON.stringify(data);res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','content-length':Buffer.byteLength(b),'x-content-type-options':'nosniff'});res.end(b);}
function error(m,status=400){const e=new Error(m);e.status=status;return e;}
function safeEqual(a,b){const x=Buffer.from(String(a)),y=Buffer.from(String(b));return x.length===y.length&&crypto.timingSafeEqual(x,y);}
function readBody(req){return new Promise((resolve,reject)=>{const chunks=[];let size=0;req.on('data',x=>{size+=x.length;if(size>MAX_BODY){reject(error('body too large',413));req.destroy();return;}chunks.push(x);});req.on('end',()=>{try{resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}'));}catch{reject(error('invalid JSON'));}});req.on('error',reject);});}
export function createServer(config={}){
 const kaggleToken=String(config.kaggleToken??process.env.KAGGLE_API_TOKEN??'').trim();
 const username=String(config.username??process.env.KAGGLE_USERNAME_SLUG??'').trim();
 const bridgeToken=String(config.bridgeToken??process.env.ND_KAGGLE_BRIDGE_TOKEN??'').trim();
 const ledgerUrl=String(config.ledgerUrl??(config.kaggleToken===undefined?process.env.ND_KAGGLE_LEDGER_URL:'')??'').trim();
 const ledgerRequired=Boolean(config.ledgerRequired??(config.kaggleToken===undefined&&process.env.ND_KAGGLE_LEDGER_REQUIRED==='true'));
 async function ledger(op,args){
   if(!ledgerUrl){if(ledgerRequired)throw error('DURABLE_LEDGER_NOT_CONFIGURED',503);return null;}
   if(!ledgerUrl.startsWith('https://'))throw error('DURABLE_LEDGER_URL_INVALID',503);
   const ms=controlBudget();const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),Math.min(ms,8000));
   try{
     const response=await fetch(ledgerUrl,{method:'POST',redirect:'manual',signal:ac.signal,headers:{authorization:'Bearer '+bridgeToken,'content-type':'application/json'},body:JSON.stringify({op,...args})});
     let data={};try{data=await response.json();}catch{}
     if(!response.ok||data.ok!==true)throw error('DURABLE_LEDGER_NOT_READY',503);
     return data;
   }catch(e){throw error('DURABLE_LEDGER_UNAVAILABLE',503);}finally{clearTimeout(timer);}
 }

 // Single-flight safety applies to this process only. Never claim cross-instance locking.
 const inFlight=new Map();
 const outcomeUnknown=new Set();
 async function rpc(service,method,body={}){
   if(!kaggleToken)throw error('KAGGLE_TOKEN_NOT_CONFIGURED',503);
   const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),controlBudget());
   try{
    const res=await fetch(`https://api.kaggle.com/v1/${service}/${method}`,{method:'POST',headers:{authorization:`Bearer ${kaggleToken}`,accept:'application/json','content-type':'application/json','user-agent':'nd-ace15-render-music/0.1'},body:JSON.stringify(body),signal:ac.signal,redirect:'manual'});
    const raw=(await res.text()).slice(0,1000000);let data={};try{data=raw?JSON.parse(raw):{}}catch{data={message:'provider returned non-JSON'}}
    if(!res.ok)throw error('KAGGLE_HTTP_'+res.status+': '+String(data.message||data.error||'provider failure').slice(0,600),res.status===401||res.status===403?502:503);
    return data;
   }catch(e){if(e.name==='AbortError')throw error('KAGGLE_CONTROL_TIMEOUT_OUTCOME_UNKNOWN',504);throw e;}finally{clearTimeout(timer);}
 }
 async function signedOutput(usr,slug,version,file){
  if(!kaggleToken)throw error('KAGGLE_TOKEN_NOT_CONFIGURED',503);
  const ac=new AbortController(), timer=setTimeout(()=>ac.abort(),controlBudget());
  try{
   const res=await fetch('https://api.kaggle.com/v1/kernels.KernelsApiService/DownloadKernelOutput',{
     method:'POST',redirect:'manual',signal:ac.signal,
     headers:{authorization:'Bearer '+kaggleToken,accept:'application/json','content-type':'application/json','user-agent':'nd-ace15-render-music/0.1'},
     body:JSON.stringify({ownerSlug:usr,kernelSlug:slug,filePath:file,versionNumber:version})});
   if(res.status>=300&&res.status<400){const loc=res.headers.get('location');if(loc?.startsWith('https://'))return loc;}
   const txt=(await res.text()).slice(0,8000);let d={};try{d=JSON.parse(txt)}catch{}
   if(!res.ok)throw error('KAGGLE_OUTPUT_HTTP_'+res.status,502);
   const u=d.url||d.redirectUrl||d.redirect_url||d.downloadUrl||d.download_url;
   if(typeof u!=='string'||!u.startsWith('https://'))throw error('PROVIDER_DOWNLOAD_URL_UNAVAILABLE',502);
   return u;
  }finally{clearTimeout(timer);}
 }
 async function identity(){const r=await rpc('security.OAuthService','IntrospectToken',{token:kaggleToken});if(!r.active||!r.username)throw error('KAGGLE_TOKEN_INACTIVE',503);if(username&&r.username!==username)throw error('KAGGLE_USERNAME_MISMATCH',503);return r.username;}
 async function quota(){const r=await rpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{});const g=r.gpuQuota||r.gpu_quota||{};const total=secs(g.totalTimeAllowed??g.total_time_allowed),used=secs(g.timeUsed??g.time_used),reserved=secs(g.timeReserved??g.time_reserved);return {total_hours:+(total/3600).toFixed(2),remaining_hours:+(Math.max(0,total-used-reserved)/3600).toFixed(2),refresh_at:r.quotaRefreshTime||null,seconds_remaining:Math.max(0,total-used-reserved)};}
 const terminalVideoVersions=new Set(); // Verified terminal version cache, process-local only.\n // Non-invasive one-sided admission: music must not consume shared Kaggle GPU while
 // a known LTX video session is active or provider visibility is insufficient.
 // This does NOT qualify bidirectional scheduling and MUST NOT edit closed video R01.
 async function videoGpuAdmission(usr){
   // One-sided music admission: exhaustive bounded LTX history, then Kaggle's
   // authoritative GPU reservation. NOT an atomic lease shared with closed LTX R01.
   const pageSize=50,maxPages=10,visible=new Map();
   let completed=false,unknownTitleRows=0;
   try{
     for(let page=1;page<=maxPages;page++){
       const data=await rpc('kernels.KernelsApiService','ListKernels',{user:usr,group:1,search:'nd-ltx2b',sortBy:2,page,pageSize});
       if(!Array.isArray(data.kernels))return {ok:false,reason:'VIDEO_LIST_UNVERIFIED'};
       for(const k of data.kernels){
         if(!k||typeof k!=='object')return {ok:false,reason:'VIDEO_ROW_INVALID'};
         const ref=String(k.ref||'').toLowerCase();
         const author=String(k.author||'').toLowerCase();
         const rawSlug=String(k.slug||'').toLowerCase();
         const refParts=ref.match(/^([a-z0-9_-]+)\/([a-z0-9-]+)$/);
         // Kaggle ListKernels live response gives ref but does not include slug.
         // Only derive slug from a validated, current-user-owned canonical ref.
         const slug=rawSlug?rawSlug.split('/').pop():(refParts&&refParts[1]===usr.toLowerCase()?refParts[2]:'');
         if(!slug&&!ref&&!author){
           const title=k.title;
           if(typeof title!=='string'||title.length===0||
              /(?:ltx|kaggle|video|(?:^|[^a-z0-9])nd(?:[^a-z0-9]|$))/i.test(title))
             return {ok:false,reason:'VIDEO_UNKNOWN_TITLE_ROW'};
           unknownTitleRows++;
           continue; // title-only non-LTX provider placeholder, verified against reservation below
         }
         if(!slug)return {ok:false,reason:'VIDEO_SLUG_UNKNOWN'};
         if(ref && (!refParts || refParts[1]!==usr.toLowerCase() || refParts[2]!==slug))
           return {ok:false,reason:'VIDEO_REF_MISMATCH'};
         if(!/^nd-ltx2b-(?:direct-)?[a-z0-9-]+$/.test(slug))continue;
         if(!ref&&author!==usr.toLowerCase())return {ok:false,reason:'VIDEO_OWNERSHIP_UNKNOWN'};
         const key=ref||usr.toLowerCase()+'/'+slug;
         if(visible.has(key))return {ok:false,reason:'VIDEO_PAGE_DUPLICATE'};
         visible.set(key,k);
       }
       if(data.kernels.length<pageSize){completed=true;break;}
     }
     if(!completed)return {ok:false,reason:'VIDEO_SCAN_INCOMPLETE'};
     // Provider docs: timeReserved = quota reserved by currently-running GPU sessions.
     // Reject absent/malformed or positive values, including independent non-LTX work.
     const q=await rpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{});
     const g=q.gpuQuota||q.gpu_quota||{};
     const raw=g.timeReserved??g.time_reserved;
     const valid=(typeof raw==='number'&&Number.isFinite(raw)&&raw>=0)||
       (typeof raw==='string'&&/^\d+(?:\.\d+)?s?$/.test(raw))||
       (raw&&typeof raw==='object'&&Number.isFinite(Number(raw.seconds??0))&&Number.isFinite(Number(raw.nanos??0)));
     if(!valid)return {ok:false,reason:'SHARED_GPU_RESERVATION_UNKNOWN'};
     if(secs(raw)>0)return {ok:false,reason:'SHARED_GPU_RESERVATION_ACTIVE'};
     // Terminal is immutable for a particular kernel ref+version. Retain only
     // confirmed provider evidence in process memory, never cache unknowns.
     const entries=[...visible.entries()];
     let cursor=0,denial=null;
     const inspectOne=async()=>{
       while(cursor<entries.length&&!denial){
         const [key,k]=entries[cursor++];
         const slug=key.split('/').pop();
         let version=Number(k.currentVersionNumber||k.current_version_number||0);
         if(!Number.isSafeInteger(version)||version<1){
           // Kaggle ListKernels omits version. Reuse R01-qualified read-only
           // GetKernel metadata resolution before requesting the exact session.
           try{
             const detail=await rpc('kernels.KernelsApiService','GetKernel',{userName:usr,kernelSlug:slug});
             version=Number(detail?.metadata?.currentVersionNumber??detail?.metadata?.current_version_number??detail?.currentVersionNumber??detail?.current_version_number??0);
           }catch{denial='VIDEO_VERSION_READ_UNAVAILABLE';break;}
         }
         if(!Number.isSafeInteger(version)||version<1){denial='VIDEO_VERSION_UNKNOWN';break;}
         const checkedKey=key+'#v'+version;
         if(terminalVideoVersions.has(checkedKey))continue;
         try{
           const status=await rpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:usr,kernelSlug:slug,versionLabel:'v'+version});
           const state=stateOf(status.status);
           if(!['COMPLETED','FAILED','CANCELLED'].includes(state)){
             denial='VIDEO_GPU_ACTIVE_OR_UNKNOWN';break;
           }
           if(terminalVideoVersions.size<1000)terminalVideoVersions.add(checkedKey);
         }catch{denial='VIDEO_STATUS_UNAVAILABLE';break;}
       }
     };
     await Promise.all(Array.from({length:Math.min(12,entries.length)},inspectOne));
     if(denial)return {ok:false,reason:denial};
     // Recheck global reservation following possibly slow history inspection.
     const q2=await rpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{});
     const g2=q2.gpuQuota||q2.gpu_quota||{};
     const r2=g2.timeReserved??g2.time_reserved;
     if(!(typeof r2==='number'&&Number.isFinite(r2)&&r2>=0) &&
        !(typeof r2==='string'&&/^\d+(?:\.\d+)?s?$/.test(r2)) &&
        !(r2&&typeof r2==='object'&&Number.isFinite(Number(r2.seconds??0))&&Number.isFinite(Number(r2.nanos??0))))
       return {ok:false,reason:'SHARED_GPU_RESERVATION_UNKNOWN'};
     if(secs(r2)>0)return {ok:false,reason:'SHARED_GPU_RESERVATION_ACTIVE'};
     return {ok:true,inspected:visible.size,non_ltx_title_rows:unknownTitleRows};
   }catch{return {ok:false,reason:'VIDEO_PROVIDER_UNAVAILABLE'};}
 }
 async function find(usr,slug){
  // Kaggle's exact search returns {} when no hits; independently inventory ALL of\n  // this user's kernels to guard against stale search results and return
  // >50 entries; never conclude that a private effect is absent from page one.
  const size=50,maxPages=10,matches=new Map(),pageKeys=new Set();
  let complete=false;
  for(let page=1;page<=maxPages;page++){
   const q=await rpc('kernels.KernelsApiService','ListKernels',{user:usr,search:'',group:1,sortBy:2,page,pageSize:size});
   if(!Array.isArray(q.kernels))throw error('KAGGLE_LIST_UNVERIFIED',503);
   for(const k of q.kernels){
    if(!k||typeof k!=='object')throw error('KAGGLE_LIST_ROW_UNKNOWN',503);
    const ref=String(k.ref||'').toLowerCase();
    const raw=String(k.slug||'').toLowerCase().split('/').pop();
    const owner=String(k.author||'').toLowerCase();
    const exact=ref===usr.toLowerCase()+'/'+slug||(!ref&&raw===slug&&owner===usr.toLowerCase());
    const title=String(k.title||'').toLowerCase();
    if(!ref&&!raw&&title.includes(slug))throw error('KAGGLE_LIST_POTENTIAL_EFFECT',503);
    if(!exact)continue;
    if(matches.has(ref||usr.toLowerCase()+'/'+raw))throw error('KAGGLE_MULTIPLE_IDENTICAL_KERNELS',409);
    const version=Number(k.currentVersionNumber||k.current_version_number||0);
    if(!Number.isSafeInteger(version)||version<1)throw error('KAGGLE_VERSION_UNVERIFIED',503);
    matches.set(ref||usr.toLowerCase()+'/'+raw,version);
   }
   // Bounded safety: page overlap of *nonmatching* rows may signal provider
   // pagination drift, so do not declare effect absent from incomplete history.
   const signature=q.kernels.map(k=>String(k?.ref||k?.slug||k?.title||'')).join('\n');
   if(pageKeys.has(signature))throw error('KAGGLE_LIST_REPEATED_PAGE',503);
   pageKeys.add(signature);
   if(q.kernels.length<size){complete=true;break;}
  }
  if(!complete)throw error('KAGGLE_LIST_INCOMPLETE',503);
  if(matches.size>1)throw error('KAGGLE_MULTIPLE_IDENTICAL_KERNELS',409);
  return matches.size===1?[...matches.values()][0]:null;
 }
 async function getStatus(usr,slug,version){
  try{const r=await rpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:usr,kernelSlug:slug,versionLabel:'v'+version});return {state:stateOf(r.status),provider_status:r.status??null,failure_message:r.failureMessage||null};}
  catch(e){if(String(e.message||'').startsWith('KAGGLE_HTTP_403'))return {state:'PROVIDER_VISIBILITY_PENDING',provider_status:null,retry_after_seconds:60,nonblocking:true,safe_to_resubmit:false};throw e;}
 }
 // Only one SaveKernel can be in-flight per hash per Render process.
 // Ambiguous outcomes are quarantined, not replayed; cross-instance persistence still required.
 async function submitOnce(usr,slug,script){
  let version;
  try{version=await find(usr,slug);}
  catch(e){return {code:503,body:{ok:false,state:'OUTCOME_UNKNOWN',slug,safe_to_resubmit:false,nonblocking:true,error_code:'KAGGLE_LIST_UNAVAILABLE'}};}
  if(version){outcomeUnknown.delete(slug);const st=await getStatus(usr,slug,version);return {code:200,body:{ok:true,reused_existing:true,job_id:slug+'-v'+version,slug,provider_ref:usr+'/'+slug+'/'+version,...st}};}
  if(outcomeUnknown.has(slug))return {code:409,body:{ok:false,state:'OUTCOME_UNKNOWN',slug,safe_to_resubmit:false,nonblocking:true,error_code:'RECONCILE_REQUIRED'}};
  const q=await quota();
  if(q.seconds_remaining<1200)return {code:409,body:{ok:false,state:'CAPACITY_BLOCKED',free_only:true,gpu:q,nonblocking:true}};
  const videoAdmission=await videoGpuAdmission(usr);
  if(!videoAdmission.ok)return {code:409,body:{ok:false,state:'SHARED_GPU_ADMISSION_BLOCKED',reason:videoAdmission.reason,slug,free_only:true,safe_to_resubmit:false,nonblocking:true}};
  // Durable INSERT / unique effect claim must succeed BEFORE SaveKernel.
  // A prior reservation, even after Render restart, is never replay authority.
  let claimNonce=null;
  if(ledgerRequired||ledgerUrl){
    claimNonce=crypto.randomUUID();
    let admitted;
    try{admitted=await ledger('acquire',{effect_key:slug,source_sha256:sha(script),slug,claim_nonce:claimNonce});}
    catch{return {code:503,body:{ok:false,state:'LEDGER_UNAVAILABLE',slug,safe_to_resubmit:false,nonblocking:true}};}
    if(!admitted||!admitted.granted){
      return {code:409,body:{ok:false,state:'OUTCOME_UNKNOWN',error_code:'DURABLE_EFFECT_ALREADY_CLAIMED',slug,safe_to_resubmit:false,nonblocking:true}};
    }
  }
  const body={slug:usr+'/'+slug,newTitle:'ND private ACE-Step music '+slug,text:script,language:'python',kernelType:'script',datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],modelDataSources:[],isPrivate:true,enableGpu:true,enableTpu:false,enableInternet:true,kernelExecutionType:'SaveAndRunAll',machineShape:'NvidiaTeslaT4',sessionTimeoutSeconds:3600};
  try{
   const saved=await rpc('kernels.KernelsApiService','SaveKernel',body);const v=Number(saved.versionNumber||saved.version_number||0);if(!v)throw error('KAGGLE_SUBMIT_UNVERIFIED_CHECK_SAME_SLUG',503);
   if(claimNonce)try{await ledger('touch',{effect_key:slug,claim_nonce:claimNonce,status:'SUBMITTED',provider_ref:usr+'/'+slug+'/'+v});}catch{/* RESERVATION persists: no replay */}
   return {code:202,body:{ok:true,state:'SUBMITTED',reused_existing:false,job_id:slug+'-v'+v,slug,provider_ref:usr+'/'+slug+'/'+v,free_only:true,gpu:q,nonblocking:true}};
  }catch(e){outcomeUnknown.add(slug);if(claimNonce)try{await ledger('touch',{effect_key:slug,claim_nonce:claimNonce,status:'SUBMIT_OUTCOME_UNKNOWN'});}catch{/* retain RESERVED */}return {code:503,body:{ok:false,state:'SUBMIT_OUTCOME_UNKNOWN',slug,safe_to_resubmit:false,nonblocking:true,error_code:'RECONCILE_REQUIRED'}};}
 }

 return http.createServer(async(req,res)=>{
  try{
   deadlineScope.enterWith(Date.now()+TOTAL_CONTROL_BUDGET);
   const url=new URL(req.url||'/',`http://${req.headers.host||'localhost'}`);
   if(url.pathname==='/health'&&req.method==='GET')return response(res,200,{ok:true,service:'nd-kaggle-music-bridge',version:VERSION,configured:!!(kaggleToken&&bridgeToken&&(!ledgerRequired||ledgerUrl.startsWith('https://'))),durable_admission_required:ledgerRequired,durable_admission_endpoint_configured:!!(ledgerUrl&&ledgerUrl.startsWith('https://')),durable_admission_live_qualified:false,free_only:true});
   if(!bridgeToken||!safeEqual(req.headers.authorization||'',`Bearer ${bridgeToken}`))return response(res,401,{ok:false,error:'UNAUTHORIZED'});
   if(url.pathname==='/mcp'&&req.method==='POST'){
     const msg=await readBody(req);
     const reply=result=>response(res,200,{jsonrpc:'2.0',id:msg.id??null,result});
     if(msg.method==='initialize')return reply({protocolVersion:'2025-03-26',capabilities:{tools:{}},serverInfo:{name:'nd-kaggle-music-bridge',version:VERSION}});
     if(msg.method==='notifications/initialized')return response(res,202,{});
     if(msg.method==='tools/list')return reply({tools:[
       {name:'kaggle_music_preflight',description:'Validate existing Kaggle token and free private GPU quota without running inference.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
       {name:'kaggle_music_submit',description:'Submit exactly one private free-only Kaggle T4 Python music generation script, idempotently. Provide entire PRIVATE python_source directly to the protected service; never put lyrics/source in GitHub. Never retry blindly if outcome unknown.',inputSchema:{type:'object',properties:{idempotency_key:{type:'string'},python_source:{type:'string'},confirm_private:{type:'boolean'}},required:['idempotency_key','python_source','confirm_private'],additionalProperties:false}},
       {name:'kaggle_music_reconcile',description:'Reconcile a potentially ambiguous prior submit by the SAME idempotency key and sha256 of the unchanged Python source. Does not create a new job.',inputSchema:{type:'object',properties:{idempotency_key:{type:'string'},source_sha256:{type:'string'}},required:['idempotency_key','source_sha256'],additionalProperties:false}},
       {name:'kaggle_music_status',description:'Check a submitted Kaggle music job by exact job_id; no new generation.',inputSchema:{type:'object',properties:{job_id:{type:'string'}},required:['job_id'],additionalProperties:false}},
       {name:'kaggle_music_result',description:'Get time-limited download URL of a completed PRIVATE Kaggle result by job_id and output file name.',inputSchema:{type:'object',properties:{job_id:{type:'string'},file_name:{type:'string'}},required:['job_id'],additionalProperties:false}}
     ]});
     if(msg.method==='tools/call'){
       const name=String(msg.params?.name||''),args=msg.params?.arguments||{};
       const route={kaggle_music_preflight:['GET','/v1/preflight'],kaggle_music_submit:['POST','/v1/submit'],kaggle_music_reconcile:['POST','/v1/reconcile'],kaggle_music_status:['POST','/v1/status'],kaggle_music_result:['POST','/v1/result']}[name];
       if(!route)return reply({content:[{type:'text',text:JSON.stringify({error:'UNKNOWN_TOOL'})}],isError:true});
       const upstream=await fetch(`http://127.0.0.1:${req.socket.localPort}${route[1]}`,{method:route[0],headers:{authorization:`Bearer ${bridgeToken}`,'content-type':'application/json'},body:route[0]==='POST'?JSON.stringify(args):undefined,signal:AbortSignal.timeout(60000)});
       const parsed=await upstream.json();
       return reply({content:[{type:'text',text:JSON.stringify(parsed)}],isError:!upstream.ok});
     }
     return response(res,200,{jsonrpc:'2.0',id:msg.id??null,error:{code:-32601,message:'METHOD_NOT_FOUND'}});
   }
   if(url.pathname==='/v1/preflight'&&req.method==='GET'){
    const usr=await identity(),q=await quota(),quotaReady=q.seconds_remaining>=1200;return response(res,200,{ok:true,provider:'kaggle',username:usr,gpu:q,free_only:true,quota_ready:quotaReady,submit_ready:quotaReady&&(!ledgerRequired||ledgerUrl.startsWith('https://')),preflight_proves_live_admission:false,durable_admission_required:ledgerRequired,durable_admission_live_qualified:false});
   }
   if(url.pathname==='/v1/submit'&&req.method==='POST'){
    const b=await readBody(req),key=b.idempotency_key,script=b.python_source;
    if(typeof key!=='string'||!/^[a-zA-Z0-9_.:-]{3,90}$/.test(key))throw error('idempotency_key invalid');
    if(typeof script!=='string'||!script.trim()||Buffer.byteLength(script)>150000)throw error('python_source size invalid');
    if(b.confirm_private!==true)throw error('confirm_private=true required');
    if(ledgerRequired&&!ledgerUrl.startsWith('https://'))return response(res,503,{ok:false,state:'LEDGER_UNAVAILABLE',safe_to_resubmit:false,nonblocking:true});
    const slug=slugFor(key,script);const usr=await identity();
    const prior=inFlight.get(slug);
    if(prior){const out=await prior;return response(res,out.code,{...out.body,reused_existing:out.body.ok?true:false,concurrent_replay:true});}
    const work=submitOnce(usr,slug,script);
    inFlight.set(slug,work);
    try{const out=await work;return response(res,out.code,out.body);}finally{inFlight.delete(slug);}
   }
   if(url.pathname==='/v1/reconcile'&&req.method==='POST'){
    const b=await readBody(req),key=b.idempotency_key,sourceHash=b.source_sha256;
    if(typeof key!=='string'||!/^[a-zA-Z0-9_.:-]{3,90}$/.test(key)||typeof sourceHash!=='string'||!/^[a-f0-9]{64}$/.test(sourceHash))throw error('invalid reconcile args');
    const slug='nd-ace15-'+sha(key+'\n'+sourceHash).slice(0,22);const usr=await identity(),v=await find(usr,slug);
    if(!v)return response(res,200,{ok:false,state:'OUTCOME_UNKNOWN',slug,safe_to_resubmit:false,nonblocking:true});
    const st=await getStatus(usr,slug,v);if(st.state!=='PROVIDER_VISIBILITY_PENDING')outcomeUnknown.delete(slug);
    return response(res,200,{ok:true,job_id:slug+'-v'+v,slug,provider_ref:usr+'/'+slug+'/'+v,...st});
   }
   if((url.pathname==='/v1/status'||url.pathname==='/v1/result')&&req.method==='POST'){
    const b=await readBody(req),m=String(b.job_id||'').match(/^(nd-ace15-[a-f0-9]{22})-v(\d+)$/);if(!m)throw error('invalid job_id');
    const [_,slug,version]=m,usr=await identity(),st=await getStatus(usr,slug,Number(version));
    if(url.pathname==='/v1/status')return response(res,200,{ok:true,job_id:b.job_id,...st});
    if(st.state!=='COMPLETED')return response(res,200,{ok:false,job_id:b.job,...st});
    const file=String(b.file_name||'result.wav');if(!/^[A-Za-z0-9_.-]{1,90}$/.test(file)||file.includes('..'))throw error('invalid output filename');
    const downloadUrl=await signedOutput(usr,slug,Number(version),file);
    return response(res,200,{ok:true,job_id:b.job_id,file_name:file,url:downloadUrl,expires_with_provider:true,persistence_state:'PROVIDER_REFERENCE_ONLY',artifact_ready:false,sonic_review:'UNKNOWN'});
   }
   return response(res,404,{ok:false,error:'NOT_FOUND'});
  }catch(e){return response(res,e.status&&e.status>=400&&e.status<=599?e.status:500,{ok:false,error:String(e.message||e).slice(0,650)});}
 });
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]){
 createServer().listen(Number(process.env.PORT||10000),'0.0.0.0',()=>console.log('ND private Kaggle music bridge ready'));
}