import crypto from "node:crypto";

const DEFAULT_RAILWAY_BASE="https://nd-external-intelligence-production.up.railway.app";
const WORKER_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx2b_direct_worker.py";

function err(message,status=0,code=""){
  const e=new Error(message);
  e.status=status;
  if(code) e.code=code;
  return e;
}

function sha256(data){
  return crypto.createHash("sha256").update(data).digest("hex");
}

const DEFAULT_CONTROL_TIMEOUT_MS={submit:30000,status:20000,result:25000,reconcile:20000};
const DEFAULT_TEXT_LIMIT_BYTES=2*1024*1024;
const DEFAULT_INPUT_LIMIT_BYTES=20*1024*1024;

function envMs(value,fallback){
  const n=Number(value);
  if(!Number.isFinite(n)||n<=0) return fallback;
  return Math.max(250,Math.floor(n));
}

function opTimeout(cfg,kind){
  const key=kind+"TimeoutMs";
  const n=Number(cfg?.[key]);
  return Number.isFinite(n)&&n>0?Math.max(250,Math.floor(n)):(DEFAULT_CONTROL_TIMEOUT_MS[kind]||20000);
}

function deadlineError(label,timeoutMs){
  const e=err("CONTROL_DEADLINE: "+label+" exceeded "+timeoutMs+"ms",408,"CONTROL_DEADLINE");
  e.timeout_ms=timeoutMs;
  e.outcome_state="OUTCOME_UNKNOWN";
  return e;
}

function makeControlContext(label,timeoutMs){
  const controller=new AbortController();
  const startedAt=Date.now();
  const deadlineAt=startedAt+timeoutMs;
  let deadlineTriggered=false;
  const timer=setTimeout(()=>{
    deadlineTriggered=true;
    try{controller.abort(deadlineError(label,timeoutMs));}catch{}
  },timeoutMs);
  return {
    label,timeoutMs,startedAt,deadlineAt,controller,signal:controller.signal,
    isDeadline(){return deadlineTriggered||Date.now()>=deadlineAt;},
    remainingMs(){return Math.max(0,deadlineAt-Date.now());},
    throwIfExpired(){if(this.isDeadline()){const de=deadlineError(label,timeoutMs);this.abort(de);throw de;}},
    abort(reason){if(!controller.signal.aborted){try{controller.abort(reason);}catch{}}},
    close(){clearTimeout(timer);}
  };
}

async function withControlDeadline(label,timeoutMs,fn){
  const ctx=makeControlContext(label,timeoutMs);
  try{
    return await fn(ctx);
  }catch(e){
    if(ctx.isDeadline()){const de=deadlineError(label,timeoutMs);ctx.abort(de);throw de;}
    ctx.abort(e);
    throw e;
  }finally{
    ctx.close();
  }
}

async function fetchCtx(url,opts,ctx){
  ctx?.throwIfExpired();
  try{
    return await fetch(url,{...opts,signal:ctx?.signal});
  }catch(e){
    if(ctx?.isDeadline()){const de=deadlineError(ctx.label,ctx.timeoutMs);ctx.abort(de);throw de;}
    throw e;
  }
}

async function readBoundedBytes(res,ctx,maxBytes,label="response"){
  const cap=Math.max(1,Number(maxBytes)||1);
  if(!res.body?.getReader){
    const buf=Buffer.from(await res.arrayBuffer());
    if(ctx?.isDeadline()){const de=deadlineError(ctx.label,ctx.timeoutMs);ctx.abort(de);throw de;}
    if(buf.length>cap) throw err(label+" exceeds "+cap+" bytes",413,"BODY_TOO_LARGE");
    return buf;
  }
  const reader=res.body.getReader();
  const chunks=[];
  let total=0;
  const onAbort=()=>{try{reader.cancel(ctx?.signal?.reason||"aborted").catch(()=>{});}catch{}};
  if(ctx?.signal) ctx.signal.addEventListener("abort",onAbort,{once:true});
  try{
    while(true){
      ctx?.throwIfExpired();
      const part=await reader.read();
      if(ctx?.isDeadline()){const de=deadlineError(ctx.label,ctx.timeoutMs);ctx.abort(de);throw de;}
      if(part.done) break;
      const b=Buffer.from(part.value);
      total+=b.length;
      if(total>cap){
        try{await reader.cancel("body_limit");}catch{}
        throw err(label+" exceeds "+cap+" bytes",413,"BODY_TOO_LARGE");
      }
      chunks.push(b);
    }
    return Buffer.concat(chunks,total);
  }catch(e){
    if(ctx?.isDeadline()){const de=deadlineError(ctx.label,ctx.timeoutMs);ctx.abort(de);throw de;}
    throw e;
  }finally{
    if(ctx?.signal) ctx.signal.removeEventListener("abort",onAbort);
  }
}

async function readBoundedText(res,ctx,maxBytes=DEFAULT_TEXT_LIMIT_BYTES,label="response"){
  return (await readBoundedBytes(res,ctx,maxBytes,label)).toString("utf8");
}

function stateOf(status){
  const s=String(status??"").toUpperCase();
  if(s==="2"||s.includes("COMPLETE")) return "COMPLETED";
  if(s==="3"||s.includes("ERROR")||s.includes("FAIL")) return "FAILED";
  if(s==="4"||s==="5"||s.includes("CANCEL")) return "CANCELLED";
  if(s==="1"||s.includes("RUN")) return "RUNNING";
  return "QUEUED";
}

function durationSeconds(v){
  if(typeof v==="number") return v;
  if(typeof v==="string"){
    const m=v.match(/^(-?\d+(?:\.\d+)?)s$/);
    return m?Number(m[1]):Number(v)||0;
  }
  if(v&&typeof v==="object") return Number(v.seconds||0)+Number(v.nanos||0)/1e9;
  return 0;
}

async function rpc(token,service,method,body={},ctx){
  if(!token) throw err("KAGGLE_API_TOKEN is not configured");
  const res=await fetchCtx("https://api.kaggle.com/v1/"+service+"/"+method,{
    method:"POST",
    headers:{
      authorization:"Bearer "+token,
      accept:"application/json",
      "content-type":"application/json",
      "user-agent":"nd-ltx-multiroute/1.1"
    },
    body:JSON.stringify(body)
  },ctx);
  const txt=await readBoundedText(res,ctx,DEFAULT_TEXT_LIMIT_BYTES,"Kaggle RPC response");
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,1200)}}
  if(!res.ok){
    const raw=data?.message??data?.error??data??txt;
    let detail;
    try{detail=typeof raw==="string"?raw:JSON.stringify(raw);}catch{detail=String(raw)}
    throw err("Kaggle HTTP "+res.status+": "+String(detail).slice(0,1800),res.status,"PROVIDER_HTTP_ERROR");
  }
  return data;
}

async function outputUrl(token,ownerSlug,kernelSlug,filePath,versionNumber=0,ctx){
  const res=await fetchCtx("https://api.kaggle.com/v1/kernels.KernelsApiService/DownloadKernelOutput",{
    method:"POST",
    redirect:"manual",
    headers:{
      authorization:"Bearer "+token,
      accept:"application/json",
      "content-type":"application/json",
      "user-agent":"nd-ltx-multiroute/1.1"
    },
    body:JSON.stringify({ownerSlug,kernelSlug,filePath,versionNumber})
  },ctx);
  if(res.status>=300&&res.status<400){
    const loc=res.headers.get("location");
    if(loc) return loc;
  }
  const txt=await readBoundedText(res,ctx,DEFAULT_TEXT_LIMIT_BYTES,"Kaggle output response");
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt}}
  if(!res.ok) throw err("Kaggle output HTTP "+res.status+": "+String(data?.message||data?.error||txt).slice(0,1000),res.status,"PROVIDER_HTTP_ERROR");
  const u=data?.url||data?.redirectUrl||data?.redirect_url||data?.downloadUrl||data?.download_url||null;
  if(u) return String(u);
  if(/^https?:\/\//i.test(String(txt||"").trim())) return String(txt).trim();
  throw err("Kaggle output returned no URL for "+filePath);
}

async function identity(cfg,ctx){
  const intro=await rpc(cfg.token,"security.OAuthService","IntrospectToken",{token:cfg.token},ctx);
  if(!intro?.active||!intro?.username) throw err("Kaggle token inactive");
  const username=String(intro.username);
  if(cfg.username&&username!==cfg.username) throw err("Kaggle username mismatch");
  return username;
}

async function preflight(cfg,username,ctx){
  const quota=await rpc(cfg.token,"kernels.KernelsApiService","GetAcceleratorQuotaStatistics",{},ctx);
  const g=quota?.gpuQuota||quota?.gpu_quota||{};
  const used=durationSeconds(g?.timeUsed??g?.time_used);
  const reserved=durationSeconds(g?.timeReserved??g?.time_reserved);
  const total=durationSeconds(g?.totalTimeAllowed??g?.total_time_allowed);
  const remaining=Math.max(0,total-used);
  if(total<=0) throw err("FREE_ONLY_BLOCKED: Kaggle GPU quota unavailable");
  if(remaining<15*60) throw err("FREE_ONLY_BLOCKED: less than 15 minutes Kaggle GPU quota remains");
  return {
    username,
    gpu:{
      used_hours:Number((used/3600).toFixed(3)),
      reserved_hours:Number((reserved/3600).toFixed(3)),
      total_hours:Number((total/3600).toFixed(3)),
      remaining_hours:Number((remaining/3600).toFixed(3)),
      refresh_at:quota?.quotaRefreshTime||quota?.quota_refresh_time||null
    }
  };
}

async function prepareInput(value,cfg,label,ctx){
  const ref=String(value||"").trim();
  if(/^https?:\/\//i.test(ref)) return {url:ref,fingerprint:sha256(ref),size_bytes:null};
  const m=ref.match(/^drive:([A-Za-z0-9_-]{10,200})$/i);
  if(!m) throw err("image ref must be http(s) URL or drive:<fileId>");
  if(!cfg.inputToken) throw err("ND_LTX_INPUT_TOKEN is not configured for drive input");
  const url=(cfg.railwayBase||DEFAULT_RAILWAY_BASE)+"/ltx-input/"+encodeURIComponent(cfg.inputToken)+"/"+encodeURIComponent(m[1]);
  const res=await fetchCtx(url,{},ctx);
  if(!res.ok) throw err(label+" Drive input read failed HTTP "+res.status,res.status,"PROVIDER_HTTP_ERROR");
  const ct=String(res.headers.get("content-type")||"");
  if(!ct.startsWith("image/")) throw err(label+" Drive input is not an image");
  const bytes=await readBoundedBytes(res,ctx,Number(cfg.inputMaxBytes)||DEFAULT_INPUT_LIMIT_BYTES,label+" Drive input");
  if(bytes.length<=0) throw err(label+" Drive input is empty");
  return {url,fingerprint:sha256(bytes),size_bytes:bytes.length};
}



function effectRef({startInput,endInput,prompt,negativePrompt,duration,width,height,seed,idempotencyKey}){
  const canonical=JSON.stringify({
    version:1,
    start_sha256:startInput.fingerprint,
    end_sha256:endInput.fingerprint,
    prompt:String(prompt||""),
    negative_prompt:String(negativePrompt||""),
    duration_seconds:Number(duration),
    width:Number(width),
    height:Number(height),
    seed:Number(seed),
    direct:true,
    idempotency_key:String(idempotencyKey||"")
  });
  const hash=sha256(canonical);
  const token="r"+hash.slice(0,12)+"-"+hash.slice(12,16);
  return {effect_id:"ltx2b:"+hash,token,kernel_slug:"nd-ltx2b-"+token};
}

async function existing(cfg,username,kernelSlug,ctx,fallbackVersion=0){
  const listed=await rpc(cfg.token,"kernels.KernelsApiService","ListKernels",{user:username,search:kernelSlug,pageSize:50},ctx);
  const kernels=Array.isArray(listed?.kernels)?listed.kernels:[];
  const owner=username.toLowerCase(), target=kernelSlug.toLowerCase();
  const exact=kernels.filter(k=>{
    const slug=String(k?.slug||"").replace(/^.*\//,"").toLowerCase();
    const ref=String(k?.ref||"").toLowerCase();
    const author=String(k?.author||"").toLowerCase();
    return ref===owner+"/"+target || (slug===target&&(!author||author===owner||author==="savva savchenko"));
  });
  if(exact.length===0) return null;
  if(exact.length>1) throw err("Kaggle idempotency conflict: multiple exact kernels");
  const version=Number(exact[0]?.currentVersionNumber??exact[0]?.current_version_number??fallbackVersion??0);
  if(!version) throw err("Kaggle idempotency conflict: existing kernel has no version");
  const st=await rpc(cfg.token,"kernels.KernelsApiService","GetKernelSessionStatus",{userName:username,kernelSlug,versionLabel:"v"+version},ctx);
  return {version,state:stateOf(st?.status),provider_status:st?.status??null};
}

function effectTokenFromId(effectId){
  const m=String(effectId||"").trim().match(/^ltx2b:([a-f0-9]{64})$/i);
  if(!m) throw err("valid ltx2b effect_id required");
  return "r"+m[1].slice(0,12)+"-"+m[1].slice(12,16);
}



function requestRef(requestId){
  const id=String(requestId||"").trim();
  const m=id.match(/^k2b-(r[a-z0-9]+-[a-z0-9]+)-v(\d+)$/i);
  if(!m) throw err("valid k2b request_id required");
  return {
    request_id:id,
    kernel_slug:"nd-ltx2b-"+m[1],
    direct_kernel_slug:"nd-ltx2b-direct-"+m[1],
    version:Number(m[2])
  };
}

async function resolveKernel(cfg,username,ref,ctx){
  let last=null;
  for(const slug of [ref.kernel_slug,ref.direct_kernel_slug]){
    try{
      const st=await rpc(cfg.token,"kernels.KernelsApiService","GetKernelSessionStatus",{userName:username,kernelSlug:slug,versionLabel:"v"+ref.version},ctx);
      return {slug,st};
    }catch(e){
      last=e;
      if(ctx?.isDeadline()) throw e;
    }
  }
  throw last||err("Kaggle kernel resolution failed");
}



export function configFromEnv(env=process.env){
  return {
    token:String(env.KAGGLE_API_TOKEN||"").trim(),
    username:String(env.KAGGLE_USERNAME_SLUG||"").trim(),
    inputToken:String(env.ND_LTX_INPUT_TOKEN||"").trim(),
    railwayBase:String(env.ND_LTX_RAILWAY_BASE||DEFAULT_RAILWAY_BASE).replace(/\/+$/,""),
    submitTimeoutMs:envMs(env.ND_LTX_SUBMIT_CONTROL_TIMEOUT_MS,DEFAULT_CONTROL_TIMEOUT_MS.submit),
    statusTimeoutMs:envMs(env.ND_LTX_STATUS_CONTROL_TIMEOUT_MS,DEFAULT_CONTROL_TIMEOUT_MS.status),
    resultTimeoutMs:envMs(env.ND_LTX_RESULT_CONTROL_TIMEOUT_MS,DEFAULT_CONTROL_TIMEOUT_MS.result),
    reconcileTimeoutMs:envMs(env.ND_LTX_RECONCILE_CONTROL_TIMEOUT_MS,DEFAULT_CONTROL_TIMEOUT_MS.reconcile),
    inputMaxBytes:Math.max(1024,Number(env.ND_LTX_INPUT_MAX_BYTES)||DEFAULT_INPUT_LIMIT_BYTES)
  };
}

export function health(cfg=configFromEnv()){
  return {
    ok:true,
    capability:"kaggle-ltx",
    configured:Boolean(cfg.token),
    username_configured:Boolean(cfg.username),
    drive_input_configured:Boolean(cfg.inputToken),
    route:"kaggle_ltx2b_direct_f2l",
    mode:"nonblocking",
    cost_policy:"FREE_ONLY",
    runtime_profile:"DURABLE_ASYNC",
    control_contract:{
      submit_timeout_ms:opTimeout(cfg,"submit"),
      status_timeout_ms:opTimeout(cfg,"status"),
      result_timeout_ms:opTimeout(cfg,"result"),
      reconcile_timeout_ms:opTimeout(cfg,"reconcile"),
      result_mode:"PROVIDER_REFERENCE",
      ambiguous_submit:"RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT"
    }
  };
}

export async function submit(args={},cfg=configFromEnv()){
  return withControlDeadline("ltx.submit",opTimeout(cfg,"submit"),async ctx=>{
    const [startInput,endInput]=await Promise.all([
      prepareInput(args.start_image_url,cfg,"start",ctx),
      prepareInput(args.end_image_url,cfg,"end",ctx)
    ]);
    const username=await identity(cfg,ctx);
    const seed=Number(args.seed??42);
    const prompt=String(args.prompt||"").trim();
    const negativePrompt=String(args.negative_prompt||"").trim()||undefined;
    const duration=Number(args.duration_seconds??2);
    const width=Number(args.width??512),height=Number(args.height??288);
    const effect=effectRef({
      startInput,endInput,prompt,negativePrompt,duration,width,height,seed,
      idempotencyKey:args.idempotency_key
    });
    const found=await existing(cfg,username,effect.kernel_slug,ctx,args.retry_failed===true?Number(args.retry_version||0):0);
    if(found && !(args.retry_failed === true && found.state === "FAILED")){
      return {
        ok:true,state:found.state,reused_existing:true,
        request_id:"k2b-"+effect.token+"-v"+found.version,
        effect_id:effect.effect_id,effect_token:effect.token,
        provider_ref:username+"/"+effect.kernel_slug+"/"+found.version,
        provider_status:found.provider_status,
        route:"kaggle_ltx2b_direct_f2l",cost_policy:"FREE_ONLY",seed,
        nonblocking:true,caller_action:"CONTINUE_OTHER_USEFUL_WORK"
      };
    }
    const pf=await preflight(cfg,username,ctx);
    const request={
      start_image_url:startInput.url,end_image_url:endInput.url,
      prompt,negative_prompt:negativePrompt,duration_seconds:duration,width,height,seed
    };
    const reqB64=Buffer.from(JSON.stringify(request),"utf8").toString("base64");
    const script=[
      "import base64,sys,urllib.request",
      "from pathlib import Path",
      "request_path=Path('/kaggle/working/nd-ltx2b-request.json')",
      "request_path.write_bytes(base64.b64decode('"+reqB64+"'))",
      "worker=Path('/kaggle/working/kaggle_ltx2b_direct_worker.py')",
      "req=urllib.request.Request('"+WORKER_URL+"',headers={'User-Agent':'nd-kaggle-ltx2b/1.0'})",
      "worker.write_bytes(urllib.request.urlopen(req,timeout=120).read())",
      "sys.argv=['kaggle_ltx2b_direct_worker.py',str(request_path)]",
      "exec(compile(worker.read_text(encoding='utf-8'),'kaggle_ltx2b_direct_worker.py','exec'),{'__name__':'__main__'})"
    ].join("\n");
    if(Buffer.byteLength(script,"utf8")>=900000) throw err("Kaggle kernel source exceeds 900 KB");
    const cacheSources=[username+"/nd-ltx-2b-distilled-cache",username+"/nd-ltx2b-load-probe-fixed"];
    let save;
    try{
      save=await rpc(cfg.token,"kernels.KernelsApiService","SaveKernel",{
        slug:username+"/"+effect.kernel_slug,
        newTitle:"ND LTX2B "+effect.token,
        text:script,language:"python",kernelType:"script",
        datasetDataSources:[],kernelDataSources:cacheSources,competitionDataSources:[],
        categoryIds:[],modelDataSources:[],isPrivate:true,enableGpu:true,enableTpu:false,
        enableInternet:true,kernelExecutionType:"SaveAndRunAll",machineShape:"NvidiaTeslaT4",
        sessionTimeoutSeconds:3600
      },ctx);
    }catch(e){
      const msg=String(e?.message||e);
      if(/429|RESOURCE_EXHAUSTED|maximum.*GPU|batch GPU session|capacity|quota/i.test(msg)){
        return {ok:false,state:"CAPACITY_BLOCKED",effect_id:effect.effect_id,effect_token:effect.token,route:"kaggle_ltx2b_direct_f2l",
          cost_policy:"FREE_ONLY",retry_after_seconds:60,nonblocking:true,
          caller_action:"CONTINUE_OTHER_USEFUL_WORK_AND_RETRY_LATER",error:msg.slice(0,1200)};
      }
      if(e?.code==="CONTROL_DEADLINE"||ctx.isDeadline()){
        return {ok:false,state:"SUBMIT_AMBIGUOUS",outcome_state:"OUTCOME_UNKNOWN",
          effect_id:effect.effect_id,effect_token:effect.token,kernel_slug:effect.kernel_slug,
          route:"kaggle_ltx2b_direct_f2l",cost_policy:"FREE_ONLY",retry_after_seconds:30,nonblocking:true,
          caller_action:"RECONCILE_SAME_EFFECT_LATER_DO_NOT_RESUBMIT",error:msg.slice(0,1200)};
      }
      const st=Number(e?.status||0);
      if(!st||st===408||st===409||st>=500){
        try{
          if(ctx.remainingMs()>750){
            const reconciled=await existing(cfg,username,effect.kernel_slug,ctx);
            if(reconciled){
              return {ok:true,state:reconciled.state,reused_existing:true,
                request_id:"k2b-"+effect.token+"-v"+reconciled.version,effect_id:effect.effect_id,effect_token:effect.token,
                provider_ref:username+"/"+effect.kernel_slug+"/"+reconciled.version,
                provider_status:reconciled.provider_status,route:"kaggle_ltx2b_direct_f2l",
                cost_policy:"FREE_ONLY",gpu_quota:pf.gpu,seed,nonblocking:true,
                caller_action:"CONTINUE_OTHER_USEFUL_WORK"};
            }
          }
        }catch{}
        return {ok:false,state:"SUBMIT_AMBIGUOUS",outcome_state:"OUTCOME_UNKNOWN",
          effect_id:effect.effect_id,effect_token:effect.token,kernel_slug:effect.kernel_slug,
          route:"kaggle_ltx2b_direct_f2l",cost_policy:"FREE_ONLY",retry_after_seconds:30,nonblocking:true,
          caller_action:"RECONCILE_SAME_EFFECT_LATER_DO_NOT_RESUBMIT",error:msg.slice(0,1200)};
      }
      throw e;
    }
    const invalid=save?.invalidKernelSources||save?.invalid_kernel_sources||[];
    if(save?.error||invalid.length) throw err("Kaggle submit failed "+JSON.stringify({error:save?.error||null,invalid_kernel_sources:invalid}));
    const version=Number(save?.versionNumber||save?.version_number||0);
    if(!version) throw err("Kaggle submit returned no version");
    return {
      ok:true,state:"SUBMITTED",reused_existing:false,
      request_id:"k2b-"+effect.token+"-v"+version,effect_id:effect.effect_id,effect_token:effect.token,
      provider_ref:username+"/"+effect.kernel_slug+"/"+version,
      route:"kaggle_ltx2b_direct_f2l",worker_mode:"DIRECT_LTX",
      cache_sources:cacheSources,machine_shape_requested:"NvidiaTeslaT4",
      cost_policy:"FREE_ONLY",gpu_quota:pf.gpu,seed,nonblocking:true,
      caller_action:"CONTINUE_OTHER_USEFUL_WORK"
    };
  });
}

export async function reconcile(args={},cfg=configFromEnv()){
  return withControlDeadline("ltx.reconcile",opTimeout(cfg,"reconcile"),async ctx=>{
    const token=String(args.effect_token||"").trim()||effectTokenFromId(args.effect_id);
    if(!/^r[a-f0-9]{12}-[a-f0-9]{4}$/i.test(token)) throw err("valid effect_token required");
    const username=await identity(cfg,ctx);
    const kernelSlug="nd-ltx2b-"+token;
    const found=await existing(cfg,username,kernelSlug,ctx);
    if(!found){
      return {
        ok:false,state:"OUTCOME_UNKNOWN",outcome_state:"OUTCOME_UNKNOWN",
        effect_id:String(args.effect_id||"")||null,effect_token:token,kernel_slug:kernelSlug,
        safe_to_resubmit:false,retry_after_seconds:30,nonblocking:true,
        caller_action:"RECHECK_SAME_EFFECT_LATER_DO_NOT_RESUBMIT"
      };
    }
    return {
      ok:true,state:found.state,reused_existing:true,
      request_id:"k2b-"+token+"-v"+found.version,
      effect_id:String(args.effect_id||"")||null,effect_token:token,
      provider_ref:username+"/"+kernelSlug+"/"+found.version,
      provider_status:found.provider_status,nonblocking:true,
      caller_action:"CONTINUE_SAME_EFFECT"
    };
  });
}

export async function status(args={},cfg=configFromEnv()){
  return withControlDeadline("ltx.status",opTimeout(cfg,"status"),async ctx=>{
    const ref=requestRef(args.request_id);
    const username=await identity(cfg,ctx);
    const resolved=await resolveKernel(cfg,username,ref,ctx);
    const state=stateOf(resolved.st?.status);
    let terminal_diagnostics=null;
    if(state==="FAILED"||state==="CANCELLED"||args.include_diagnostics===true){
      try{
        const out=await rpc(cfg.token,"kernels.KernelsApiService","ListKernelSessionOutput",{
          userName:username,kernelSlug:resolved.slug,versionLabel:"v"+ref.version,pageSize:100
        },ctx);
        terminal_diagnostics={
          output_files:(Array.isArray(out?.files)?out.files:[]).map(x=>({
            name:x?.fileName||x?.name||x?.path||null,
            size:x?.fileSize??x?.size??null
          })).filter(x=>x.name),
          log_tail:String(out?.log||"").slice(-12000)
        };
      }catch(e){
        terminal_diagnostics={diagnostic_error:String(e?.message||e).slice(0,1200)};
      }
    }
    return {
      ok:true,request_id:ref.request_id,state,
      provider_status:resolved.st?.status??null,
      failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,
      provider_ref:username+"/"+resolved.slug+"/"+ref.version,
      terminal_diagnostics,
      nonblocking:true,
      control_observed_at:new Date().toISOString(),
      next_check_after_seconds:state==="QUEUED"?30:(state==="RUNNING"?45:null)
    };
  });
}

export async function result(args={},cfg=configFromEnv()){
  return withControlDeadline("ltx.result",opTimeout(cfg,"result"),async ctx=>{
    const ref=requestRef(args.request_id);
    const username=await identity(cfg,ctx);
    const resolved=await resolveKernel(cfg,username,ref,ctx);
    const state=stateOf(resolved.st?.status);
    if(state!=="COMPLETED") return {
      ok:false,request_id:ref.request_id,state,
      provider_status:resolved.st?.status??null,
      failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,
      nonblocking:true
    };
    const videoUrl=await outputUrl(cfg.token,username,resolved.slug,"result.mp4",ref.version,ctx);
    let receiptUrl=null,receipt_state="READY";
    try{
      if(ctx.remainingMs()>500) receiptUrl=await outputUrl(cfg.token,username,resolved.slug,"result.json",ref.version,ctx);
      else receipt_state="DEFERRED_CONTROL_BUDGET";
    }catch(e){
      receipt_state=e?.code==="CONTROL_DEADLINE"||ctx.isDeadline()?"DEFERRED_CONTROL_BUDGET":"UNAVAILABLE";
    }
    return {
      ok:true,request_id:ref.request_id,state:"READY",
      route:"kaggle_ltx2b_direct_f2l",
      provider_ref:username+"/"+resolved.slug+"/"+ref.version,
      provider_video_url:videoUrl,provider_receipt_url:receiptUrl,receipt_state,
      video_ref:videoUrl,persistence_state:"NOT_REQUESTED",
      result_mode:"PROVIDER_REFERENCE",
      nonblocking:true
    };
  });
}

