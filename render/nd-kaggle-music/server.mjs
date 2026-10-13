import http from 'node:http';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { AsyncLocalStorage } from 'node:async_hooks';

// ND Music Studio: private Kaggle GPU bridge. Render holds no GPU, no job database,
// no lyrics, and no persistent files. Kaggle's private kernels are the job ledger.
const VERSION='0.1.2-durable-p0';
const MAX_BODY=300_000;
const TMO=22_000;
const TOTAL_CONTROL_BUDGET=45_000;
const deadlineScope=new AsyncLocalStorage();
function controlBudget(){const d=deadlineScope.getStore();const remain=d===undefined?TMO:d-Date.now();if(remain<=0)throw error('CONTROL_DEADLINE_OUTCOME_UNKNOWN',504);return Math.min(remain,TMO);}
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const slugFor=(key,script)=>'nd-ace15-'+sha(String(key)+'\n'+sha(script)).slice(0,22);
const states={0:'QUEUED',1:'RUNNING',2:'COMPLETED',3:'FAILED',4:'CANCELLED',5:'CANCELLED'};
const stateOf=x=>states[Number(x)]||String(x||'QUEUED').toUpperCase();
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
 async function find(usr,slug){const q=await rpc('kernels.KernelsApiService','ListKernels',{user:usr,search:slug,pageSize:50});const a=(q.kernels||[]).filter(k=>String(k.slug||'').split('/').pop().toLowerCase()===slug&&(!k.ref||String(k.ref).toLowerCase()===usr.toLowerCase()+'/'+slug));if(a.length>1)throw error('KAGGLE_MULTIPLE_IDENTICAL_KERNELS',409);if(!a.length)return null;return Number(a[0].currentVersionNumber||a[0].current_version_number||0)||null;}
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
   if(url.pathname==='/health'&&req.method==='GET')return response(res,200,{ok:true,service:'nd-kaggle-music-bridge',version:VERSION,configured:!!(kaggleToken&&bridgeToken),free_only:true});
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
    const usr=await identity(),q=await quota();return response(res,200,{ok:true,provider:'kaggle',username:usr,gpu:q,free_only:true,submit_ready:q.seconds_remaining>=1200});
   }
   if(url.pathname==='/v1/submit'&&req.method==='POST'){
    const b=await readBody(req),key=b.idempotency_key,script=b.python_source;
    if(typeof key!=='string'||!/^[a-zA-Z0-9_.:-]{3,90}$/.test(key))throw error('idempotency_key invalid');
    if(typeof script!=='string'||!script.trim()||Buffer.byteLength(script)>150000)throw error('python_source size invalid');
    if(b.confirm_private!==true)throw error('confirm_private=true required');
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