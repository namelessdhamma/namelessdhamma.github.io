import crypto from 'node:crypto';
import {ltxControlTimeout,withLtxControlDeadline,ltxFetch,ltxReadBoundedBytes,ltxReadBoundedText,LTX_CONTROL_TEXT_MAX_BYTES,LTX_CONTROL_INPUT_MAX_BYTES} from './ltx_control.mjs';

const KAGGLE_API_TOKEN=String(process.env.KAGGLE_API_TOKEN||'').trim();
const KAGGLE_USERNAME_SLUG=String(process.env.KAGGLE_USERNAME_SLUG||'').trim();
const LTX_INPUT_TOKEN=String(process.env.ND_LTX_INPUT_TOKEN||'').trim();
const LTX_PUBLIC_BASE=String(process.env.ND_LTX_PUBLIC_BASE||'https://nd-external-intelligence-production.up.railway.app').replace(/\/$/,'');
const LTX_INPUT_BASE=String(process.env.ND_LTX_INPUT_BASE||LTX_PUBLIC_BASE).replace(/\/$/,'');
const WORKER_URL='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx2b_direct_worker.py';

function errorText(e){return String(e?.message||e||'error').slice(0,1800);}
function json(res,status,obj){res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});return res.end(JSON.stringify(obj));}
function toolResult(value){return {content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value,isError:false};}
function durationSeconds(v){
  if(typeof v==='number')return v;
  if(typeof v==='string'){const m=v.match(/^(-?\d+(?:\.\d+)?)s$/);return m?Number(m[1]):Number(v)||0;}
  if(v&&typeof v==='object')return Number(v.seconds||0)+Number(v.nanos||0)/1e9;
  return 0;
}
function stateOf(status){
  const s=String(status??'').toUpperCase();
  if(s==='2'||s.includes('COMPLETE'))return 'COMPLETED';
  if(s==='3'||s.includes('ERROR')||s.includes('FAIL'))return 'FAILED';
  if(s==='4'||s==='5'||s.includes('CANCEL'))return 'CANCELLED';
  if(s==='1'||s.includes('RUN'))return 'RUNNING';
  return 'QUEUED';
}
function sha256(data){return crypto.createHash('sha256').update(data).digest('hex');}

async function rpc(service,method,body={},ctx){
  if(!KAGGLE_API_TOKEN)throw new Error('KAGGLE_API_TOKEN is not configured');
  const res=await ltxFetch('https://api.kaggle.com/v1/'+service+'/'+method,{
    method:'POST',
    headers:{authorization:'Bearer '+KAGGLE_API_TOKEN,accept:'application/json','content-type':'application/json','user-agent':'nd-ltx-primary-v2/1.0'},
    body:JSON.stringify(body)
  },ctx);
  const txt=await ltxReadBoundedText(res,ctx,LTX_CONTROL_TEXT_MAX_BYTES,'Kaggle RPC response');
  let data={};try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,1200)};}
  if(!res.ok){
    const raw=data?.message??data?.error??data??txt;let detail;
    try{detail=typeof raw==='string'?raw:JSON.stringify(raw);}catch{detail=String(raw);}
    const e=new Error('Kaggle HTTP '+res.status+': '+String(detail).slice(0,1800));
    e.status=res.status;e.code='PROVIDER_HTTP_ERROR';throw e;
  }
  return data;
}

async function outputUrl(ownerSlug,kernelSlug,filePath,versionNumber,ctx){
  const res=await ltxFetch('https://api.kaggle.com/v1/kernels.KernelsApiService/DownloadKernelOutput',{
    method:'POST',redirect:'manual',
    headers:{authorization:'Bearer '+KAGGLE_API_TOKEN,accept:'application/json','content-type':'application/json','user-agent':'nd-ltx-primary-v2/1.0'},
    body:JSON.stringify({ownerSlug,kernelSlug,filePath,versionNumber})
  },ctx);
  if(res.status>=300&&res.status<400){const loc=res.headers.get('location');if(loc)return loc;}
  const txt=await ltxReadBoundedText(res,ctx,LTX_CONTROL_TEXT_MAX_BYTES,'Kaggle output response');
  let data={};try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt};}
  if(!res.ok){const e=new Error('Kaggle output HTTP '+res.status+': '+String(data?.message||data?.error||txt).slice(0,1200));e.status=res.status;e.code='PROVIDER_HTTP_ERROR';throw e;}
  const u=data?.url||data?.redirectUrl||data?.redirect_url||data?.downloadUrl||data?.download_url||null;
  if(u)return String(u);
  const raw=String(txt||'').trim();if(/^https?:\/\//i.test(raw))return raw;
  throw new Error('Kaggle output returned no URL for '+filePath);
}

async function identity(ctx){
  const intro=await rpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN},ctx);
  if(!intro?.active||!intro?.username)throw new Error('Kaggle token inactive');
  const username=String(intro.username);
  if(KAGGLE_USERNAME_SLUG&&username!==KAGGLE_USERNAME_SLUG)throw new Error('Kaggle username mismatch');
  return username;
}
async function preflight(username,ctx){
  const quota=await rpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{},ctx);
  const g=quota?.gpuQuota||quota?.gpu_quota||{};
  const used=durationSeconds(g?.timeUsed??g?.time_used),reserved=durationSeconds(g?.timeReserved??g?.time_reserved),total=durationSeconds(g?.totalTimeAllowed??g?.total_time_allowed);
  const remaining=Math.max(0,total-used);
  if(total<=0)throw new Error('FREE_ONLY_BLOCKED: Kaggle GPU quota unavailable');
  if(remaining<15*60)throw new Error('FREE_ONLY_BLOCKED: less than 15 minutes Kaggle GPU quota remains');
  return {username,gpu:{used_hours:Number((used/3600).toFixed(3)),reserved_hours:Number((reserved/3600).toFixed(3)),total_hours:Number((total/3600).toFixed(3)),remaining_hours:Number((remaining/3600).toFixed(3)),refresh_at:quota?.quotaRefreshTime||quota?.quota_refresh_time||null}};
}
async function prepareInput(value,label,ctx){
  const ref=String(value||'').trim();
  if(/^https?:\/\//i.test(ref))return {url:ref,fingerprint:sha256(ref),size_bytes:null};
  const m=ref.match(/^drive:([A-Za-z0-9_-]{10,200})$/i);
  if(!m)throw new Error('image ref must be http(s) URL or drive:<fileId>');
  if(!LTX_INPUT_TOKEN)throw new Error('ND_LTX_INPUT_TOKEN is not configured');
  const publicUrl=LTX_INPUT_BASE+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  const res=await ltxFetch(publicUrl,{},ctx);
  if(!res.ok)throw new Error(label+' Drive input read failed HTTP '+res.status);
  const ct=String(res.headers.get('content-type')||'');
  if(!ct.startsWith('image/'))throw new Error(label+' Drive input is not an image');
  const bytes=await ltxReadBoundedBytes(res,ctx,LTX_CONTROL_INPUT_MAX_BYTES,label+' Drive input');
  if(!bytes.length)throw new Error(label+' Drive input is empty');
  return {url:publicUrl,fingerprint:sha256(bytes),size_bytes:bytes.length};
}
function effectRef({startInput,endInput,prompt,negativePrompt,duration,width,height,seed,idempotencyKey}){
  const canonical=JSON.stringify({version:1,start_sha256:startInput.fingerprint,end_sha256:endInput.fingerprint,prompt:String(prompt||''),negative_prompt:String(negativePrompt||''),duration_seconds:Number(duration),width:Number(width),height:Number(height),seed:Number(seed),direct:true,idempotency_key:String(idempotencyKey||'')});
  const hash=sha256(canonical),token='r'+hash.slice(0,12)+'-'+hash.slice(12,16);
  return {effect_id:'ltx2b:'+hash,token,kernel_slug:'nd-ltx2b-'+token};
}
function effectTokenFromId(effectId){
  const m=String(effectId||'').trim().match(/^ltx2b:([a-f0-9]{64})$/i);
  if(!m)throw new Error('valid ltx2b effect_id required');
  return 'r'+m[1].slice(0,12)+'-'+m[1].slice(12,16);
}
function requestRef(requestId){
  const id=String(requestId||'').trim(),m=id.match(/^k2b-(r[a-z0-9]+-[a-z0-9]+)-v(\d+)$/i);
  if(!m)throw new Error('valid k2b request_id required');
  return {request_id:id,kernel_slug:'nd-ltx2b-'+m[1],direct_kernel_slug:'nd-ltx2b-direct-'+m[1],version:Number(m[2])};
}
async function existing(username,kernelSlug,ctx){
  const listed=await rpc('kernels.KernelsApiService','ListKernels',{user:username,search:kernelSlug,pageSize:50},ctx);
  const kernels=Array.isArray(listed?.kernels)?listed.kernels:[],owner=username.toLowerCase(),target=kernelSlug.toLowerCase();
  const exact=kernels.filter(k=>{const slug=String(k?.slug||'').replace(/^.*\//,'').toLowerCase(),ref=String(k?.ref||'').toLowerCase(),author=String(k?.author||'').toLowerCase();return ref===owner+'/'+target||(slug===target&&(!author||author===owner||author==='savva savchenko'));});
  if(exact.length===0)return null;
  if(exact.length>1)throw new Error('Kaggle idempotency conflict: multiple exact kernels');
  const version=Number(exact[0]?.currentVersionNumber??exact[0]?.current_version_number??0);
  if(!version)throw new Error('Kaggle idempotency conflict: existing kernel has no version');
  const st=await rpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug,versionLabel:'v'+version},ctx);
  return {version,state:stateOf(st?.status),provider_status:st?.status??null};
}
async function resolveKernel(username,ref,ctx){
  let last=null;
  for(const slug of [ref.kernel_slug,ref.direct_kernel_slug]){
    try{return {slug,st:await rpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel:'v'+ref.version},ctx)};}
    catch(e){last=e;if(ctx?.isDeadline())throw e;}
  }
  throw last||new Error('Kaggle kernel resolution failed');
}

async function submit(args={}){
  return withLtxControlDeadline('ltx.primary.submit',ltxControlTimeout('submit'),async ctx=>{
    const [startInput,endInput]=await Promise.all([prepareInput(args.start_image_url,'start',ctx),prepareInput(args.end_image_url,'end',ctx)]);
    const username=await identity(ctx),seed=Number(args.seed??42),prompt=String(args.prompt||'').trim(),negativePrompt=String(args.negative_prompt||'').trim()||undefined,duration=Number(args.duration_seconds??2),width=Number(args.width??512),height=Number(args.height??288);
    const effect=effectRef({startInput,endInput,prompt,negativePrompt,duration,width,height,seed,idempotencyKey:args.idempotency_key});
    const prior=await existing(username,effect.kernel_slug,ctx);
    if(prior)return {ok:true,state:prior.state,reused_existing:true,request_id:'k2b-'+effect.token+'-v'+prior.version,effect_id:effect.effect_id,effect_token:effect.token,provider_ref:username+'/'+effect.kernel_slug+'/'+prior.version,provider_status:prior.provider_status,route:'kaggle_ltx2b_direct_f2l',cost_policy:'FREE_ONLY',seed,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK'};
    const pf=await preflight(username,ctx);
    const req={start_image_url:startInput.url,end_image_url:endInput.url,prompt,negative_prompt:negativePrompt,duration_seconds:duration,width,height,seed};
    const reqB64=Buffer.from(JSON.stringify(req),'utf8').toString('base64');
    const script=['import base64,sys,urllib.request','from pathlib import Path',"request_path=Path('/kaggle/working/nd-ltx2b-request.json')","request_path.write_bytes(base64.b64decode('"+reqB64+"'))","worker=Path('/kaggle/working/kaggle_ltx2b_direct_worker.py')","req=urllib.request.Request('"+WORKER_URL+"',headers={'User-Agent':'nd-kaggle-ltx2b/1.1'})","worker.write_bytes(urllib.request.urlopen(req,timeout=120).read())","sys.argv=['kaggle_ltx2b_direct_worker.py',str(request_path)]","exec(compile(worker.read_text(encoding='utf-8'),'kaggle_ltx2b_direct_worker.py','exec'),{'__name__':'__main__'})"].join('\n');
    if(Buffer.byteLength(script,'utf8')>=900000)throw new Error('Kaggle kernel source exceeds 900 KB');
    const cacheSources=[username+'/nd-ltx-2b-distilled-cache',username+'/nd-ltx2b-load-probe-fixed'];
    let save;
    try{save=await rpc('kernels.KernelsApiService','SaveKernel',{slug:username+'/'+effect.kernel_slug,newTitle:'ND LTX2B '+effect.token,text:script,language:'python',kernelType:'script',datasetDataSources:[],kernelDataSources:cacheSources,competitionDataSources:[],categoryIds:[],modelDataSources:[],isPrivate:true,enableGpu:true,enableTpu:false,enableInternet:true,kernelExecutionType:'SaveAndRunAll',machineShape:'NvidiaTeslaT4',sessionTimeoutSeconds:3600},ctx);}
    catch(e){
      const msg=String(e?.message||e);
      if(/429|RESOURCE_EXHAUSTED|maximum.*GPU|batch GPU session|capacity|quota/i.test(msg))return {ok:false,state:'CAPACITY_BLOCKED',effect_id:effect.effect_id,effect_token:effect.token,route:'kaggle_ltx2b_direct_f2l',cost_policy:'FREE_ONLY',retry_after_seconds:60,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK_AND_RETRY_LATER',error:msg.slice(0,1200)};
      if(e?.code==='CONTROL_DEADLINE'||ctx.isDeadline())return {ok:false,state:'SUBMIT_AMBIGUOUS',outcome_state:'OUTCOME_UNKNOWN',effect_id:effect.effect_id,effect_token:effect.token,kernel_slug:effect.kernel_slug,route:'kaggle_ltx2b_direct_f2l',cost_policy:'FREE_ONLY',retry_after_seconds:30,nonblocking:true,caller_action:'RECONCILE_SAME_EFFECT_LATER_DO_NOT_RESUBMIT',error:msg.slice(0,1200)};
      const st=Number(e?.status||0);
      if(!st||st===408||st===409||st>=500){try{if(ctx.remainingMs()>750){const found=await existing(username,effect.kernel_slug,ctx);if(found)return {ok:true,state:found.state,reused_existing:true,request_id:'k2b-'+effect.token+'-v'+found.version,effect_id:effect.effect_id,effect_token:effect.token,provider_ref:username+'/'+effect.kernel_slug+'/'+found.version,provider_status:found.provider_status,route:'kaggle_ltx2b_direct_f2l',cost_policy:'FREE_ONLY',gpu_quota:pf.gpu,seed,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK'};}}catch{}return {ok:false,state:'SUBMIT_AMBIGUOUS',outcome_state:'OUTCOME_UNKNOWN',effect_id:effect.effect_id,effect_token:effect.token,kernel_slug:effect.kernel_slug,route:'kaggle_ltx2b_direct_f2l',cost_policy:'FREE_ONLY',retry_after_seconds:30,nonblocking:true,caller_action:'RECONCILE_SAME_EFFECT_LATER_DO_NOT_RESUBMIT',error:msg.slice(0,1200)};}
      throw e;
    }
    const invalid=save?.invalidKernelSources||save?.invalid_kernel_sources||[],version=Number(save?.versionNumber||save?.version_number||0);
    if(save?.error||invalid.length)throw new Error('Kaggle submit failed '+JSON.stringify({error:save?.error||null,invalid_kernel_sources:invalid}));
    if(!version)throw new Error('Kaggle submit returned no version');
    return {ok:true,state:'SUBMITTED',reused_existing:false,request_id:'k2b-'+effect.token+'-v'+version,effect_id:effect.effect_id,effect_token:effect.token,provider_ref:username+'/'+effect.kernel_slug+'/'+version,route:'kaggle_ltx2b_direct_f2l',cache_sources:cacheSources,cost_policy:'FREE_ONLY',gpu_quota:pf.gpu,seed,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK'};
  });
}
async function reconcile(args={}){
  return withLtxControlDeadline('ltx.primary.reconcile',ltxControlTimeout('reconcile'),async ctx=>{
    const token=String(args.effect_token||'').trim()||effectTokenFromId(args.effect_id);
    if(!/^r[a-f0-9]{12}-[a-f0-9]{4}$/i.test(token))throw new Error('valid effect_token required');
    const username=await identity(ctx),kernelSlug='nd-ltx2b-'+token,found=await existing(username,kernelSlug,ctx);
    if(!found)return {ok:false,state:'OUTCOME_UNKNOWN',outcome_state:'OUTCOME_UNKNOWN',effect_id:String(args.effect_id||'')||null,effect_token:token,kernel_slug:kernelSlug,safe_to_resubmit:false,retry_after_seconds:30,nonblocking:true,caller_action:'RECHECK_SAME_EFFECT_LATER_DO_NOT_RESUBMIT'};
    return {ok:true,state:found.state,reused_existing:true,request_id:'k2b-'+token+'-v'+found.version,effect_id:String(args.effect_id||'')||null,effect_token:token,provider_ref:username+'/'+kernelSlug+'/'+found.version,provider_status:found.provider_status,nonblocking:true,caller_action:'CONTINUE_SAME_EFFECT'};
  });
}
async function status(args={}){
  return withLtxControlDeadline('ltx.primary.status',ltxControlTimeout('status'),async ctx=>{
    const ref=requestRef(args.request_id),username=await identity(ctx),resolved=await resolveKernel(username,ref,ctx),state=stateOf(resolved.st?.status);
    let diagnostics=null;
    if(state==='FAILED'||state==='CANCELLED'){try{const out=await rpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:resolved.slug,pageSize:100},ctx);diagnostics={files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],log_tail:String(out?.log||'').slice(-12000)};}catch(e){diagnostics={error:errorText(e)};}}
    return {ok:true,request_id:ref.request_id,state,provider_status:resolved.st?.status??null,failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,provider_ref:username+'/'+resolved.slug+'/'+ref.version,diagnostics,nonblocking:true,control_observed_at:new Date().toISOString(),next_check_after_seconds:state==='QUEUED'?30:(state==='RUNNING'?45:null)};
  });
}
async function result(args={}){
  return withLtxControlDeadline('ltx.primary.result',ltxControlTimeout('result'),async ctx=>{
    const ref=requestRef(args.request_id),username=await identity(ctx),resolved=await resolveKernel(username,ref,ctx),state=stateOf(resolved.st?.status);
    if(state!=='COMPLETED')return {ok:false,request_id:ref.request_id,state,provider_status:resolved.st?.status??null,failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,nonblocking:true};
    const video=await outputUrl(username,resolved.slug,'result.mp4',ref.version,ctx);
    let receiptUrl=null,receipt_state='READY';try{if(ctx.remainingMs()>500)receiptUrl=await outputUrl(username,resolved.slug,'result.json',ref.version,ctx);else receipt_state='DEFERRED_CONTROL_BUDGET';}catch(e){receipt_state=e?.code==='CONTROL_DEADLINE'||ctx.isDeadline()?'DEFERRED_CONTROL_BUDGET':'UNAVAILABLE';}
    return {ok:true,request_id:ref.request_id,state:'READY',route:'kaggle_ltx2b_direct_f2l',provider_ref:username+'/'+resolved.slug+'/'+ref.version,provider_video_url:video,provider_receipt_url:receiptUrl,receipt_state,video_ref:video,persistence_state:'NOT_REQUESTED',result_mode:'PROVIDER_REFERENCE',nonblocking:true};
  });
}

const TOOLS=[
  {name:'ltx_generate_keyframes',description:'DURABLE_ASYNC FREE_ONLY submit. Returns control with request/effect identity; never waits for inference.',inputSchema:{type:'object',properties:{start_image_url:{type:'string'},end_image_url:{type:'string'},prompt:{type:'string'},negative_prompt:{type:'string'},duration_seconds:{type:'number',default:2,minimum:1,maximum:6},width:{type:'integer',default:512},height:{type:'integer',default:288},seed:{type:'integer',default:42},idempotency_key:{type:'string'}},required:['start_image_url','end_image_url'],additionalProperties:false}},
  {name:'ltx_keyframe_reconcile',description:'Reconcile an ambiguous submit by stable effect identity. Never resubmits.',inputSchema:{type:'object',properties:{effect_id:{type:'string'},effect_token:{type:'string'}},anyOf:[{required:['effect_id']},{required:['effect_token']}],additionalProperties:false}},
  {name:'ltx_keyframe_status',description:'One bounded status read under a shared end-to-end control deadline.',inputSchema:{type:'object',properties:{request_id:{type:'string'}},required:['request_id'],additionalProperties:false}},
  {name:'ltx_keyframe_result',description:'One bounded provider-reference result read. Persistence is separate.',inputSchema:{type:'object',properties:{request_id:{type:'string'}},required:['request_id'],additionalProperties:false}}
];

export function createLtxMcpHandler(){
  return async function handle(req,res){
    if(req.method==='GET'){res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});res.write(': nd-kaggle-ltx-mcp durable-async-v2\n\n');return res.end();}
    if(req.method!=='POST')return json(res,405,{ok:false,error:'method_not_allowed'});
    const chunks=[];for await(const ch of req)chunks.push(ch);
    let msg={};try{msg=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}catch{return json(res,400,{jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}});}
    const id=msg.id??null,method=String(msg.method||'');
    try{
      if(method==='initialize')return json(res,200,{jsonrpc:'2.0',id,result:{protocolVersion:String(msg?.params?.protocolVersion||'2025-06-18'),capabilities:{tools:{}},serverInfo:{name:'ND Kaggle LTX MCP',version:'2.0.0'}}});
      if(method==='ping')return json(res,200,{jsonrpc:'2.0',id,result:{}});
      if(method.startsWith('notifications/')){res.writeHead(202,{'cache-control':'no-store'});return res.end();}
      if(method==='tools/list')return json(res,200,{jsonrpc:'2.0',id,result:{tools:TOOLS}});
      if(method==='tools/call'){
        const name=String(msg?.params?.name||''),args=(msg?.params?.arguments&&typeof msg.params.arguments==='object')?msg.params.arguments:{};
        let out;
        if(name==='ltx_generate_keyframes')out=await submit(args);
        else if(name==='ltx_keyframe_reconcile')out=await reconcile(args);
        else if(name==='ltx_keyframe_status')out=await status(args);
        else if(name==='ltx_keyframe_result')out=await result(args);
        else return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Unknown tool'}});
        return json(res,200,{jsonrpc:'2.0',id,result:toolResult(out)});
      }
      return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }catch(e){
      const out={ok:false,state:e?.code==='CONTROL_DEADLINE'?'CONTROL_DEADLINE':'ERROR',outcome_state:e?.outcome_state||null,error_code:e?.code||null,timeout_ms:e?.timeout_ms||null,error:errorText(e),nonblocking:true};
      return json(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(out)}],structuredContent:out,isError:true}});
    }
  };
}

export async function ltxHealth(){
  return {ok:true,mode:'production_nonblocking',runtime_profile:'DURABLE_ASYNC',production_tools:TOOLS.map(x=>x.name),cost_policy:'FREE_ONLY',route:'kaggle_ltx2b_direct_f2l',control_contract:{submit_timeout_ms:ltxControlTimeout('submit'),status_timeout_ms:ltxControlTimeout('status'),result_timeout_ms:ltxControlTimeout('result'),reconcile_timeout_ms:ltxControlTimeout('reconcile'),result_mode:'PROVIDER_REFERENCE',ambiguous_submit:'RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT'}};
}

export async function ltxResultBytes(requestId){
  return withLtxControlDeadline('ltx.primary.download',ltxControlTimeout('download'),async ctx=>{
    const out=await result({request_id:requestId});
    if(out?.state!=='READY')return {state:out?.state||'UNKNOWN',mp4:null,receipt:null};
    const res=await ltxFetch(String(out.provider_video_url||out.video_ref),{headers:{'user-agent':'nd-ltx-primary-v2/1.0'}},ctx);
    if(!res.ok)throw new Error('ltx result provider download HTTP '+res.status);
    const mp4=await ltxReadBoundedBytes(res,ctx,150*1024*1024,'ltx result');
    return {state:'READY',mp4,receipt:null};
  });
}
