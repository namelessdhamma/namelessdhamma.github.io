import crypto from "node:crypto";

const DEFAULT_RAILWAY_BASE="https://nd-external-intelligence-production.up.railway.app";
const WORKER_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx2b_direct_worker.py";

function err(message,status=0){
  const e=new Error(message);
  e.status=status;
  return e;
}

function sha256(data){
  return crypto.createHash("sha256").update(data).digest("hex");
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

async function rpc(token,service,method,body={}){
  if(!token) throw err("KAGGLE_API_TOKEN is not configured");
  const res=await fetch("https://api.kaggle.com/v1/"+service+"/"+method,{
    method:"POST",
    headers:{
      authorization:"Bearer "+token,
      accept:"application/json",
      "content-type":"application/json",
      "user-agent":"nd-ltx-multiroute/1.0"
    },
    body:JSON.stringify(body)
  });
  const txt=await res.text();
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,1200)}}
  if(!res.ok){
    const raw=data?.message??data?.error??data??txt;
    let detail;
    try{detail=typeof raw==="string"?raw:JSON.stringify(raw);}catch{detail=String(raw)}
    throw err("Kaggle HTTP "+res.status+": "+String(detail).slice(0,1800),res.status);
  }
  return data;
}

async function outputUrl(token,ownerSlug,kernelSlug,filePath,versionNumber=0){
  const res=await fetch("https://api.kaggle.com/v1/kernels.KernelsApiService/DownloadKernelOutput",{
    method:"POST",
    redirect:"manual",
    headers:{
      authorization:"Bearer "+token,
      accept:"application/json",
      "content-type":"application/json",
      "user-agent":"nd-ltx-multiroute/1.0"
    },
    body:JSON.stringify({ownerSlug,kernelSlug,filePath,versionNumber})
  });
  if(res.status>=300&&res.status<400){
    const loc=res.headers.get("location");
    if(loc) return loc;
  }
  const txt=await res.text();
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt}}
  if(!res.ok) throw err("Kaggle output HTTP "+res.status+": "+String(data?.message||data?.error||txt).slice(0,1000),res.status);
  const u=data?.url||data?.redirectUrl||data?.redirect_url||data?.downloadUrl||data?.download_url||null;
  if(u) return String(u);
  if(/^https?:\/\//i.test(String(txt||"").trim())) return String(txt).trim();
  throw err("Kaggle output returned no URL for "+filePath);
}

async function identity(cfg){
  const intro=await rpc(cfg.token,"security.OAuthService","IntrospectToken",{token:cfg.token});
  if(!intro?.active||!intro?.username) throw err("Kaggle token inactive");
  const username=String(intro.username);
  if(cfg.username&&username!==cfg.username) throw err("Kaggle username mismatch");
  return username;
}

async function preflight(cfg,username){
  const quota=await rpc(cfg.token,"kernels.KernelsApiService","GetAcceleratorQuotaStatistics",{});
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

async function prepareInput(value,cfg,label){
  const ref=String(value||"").trim();
  if(/^https?:\/\//i.test(ref)) return {url:ref,fingerprint:sha256(ref),size_bytes:null};
  const m=ref.match(/^drive:([A-Za-z0-9_-]{10,200})$/i);
  if(!m) throw err("image ref must be http(s) URL or drive:<fileId>");
  if(!cfg.inputToken) throw err("ND_LTX_INPUT_TOKEN is not configured for drive input");
  const url=(cfg.railwayBase||DEFAULT_RAILWAY_BASE)+"/ltx-input/"+encodeURIComponent(cfg.inputToken)+"/"+encodeURIComponent(m[1]);
  const res=await fetch(url);
  if(!res.ok) throw err(label+" Drive input read failed HTTP "+res.status,res.status);
  const ct=String(res.headers.get("content-type")||"");
  if(!ct.startsWith("image/")) throw err(label+" Drive input is not an image");
  const bytes=Buffer.from(await res.arrayBuffer());
  if(bytes.length<=0||bytes.length>20*1024*1024) throw err(label+" Drive input size invalid");
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

async function existing(cfg,username,kernelSlug){
  const listed=await rpc(cfg.token,"kernels.KernelsApiService","ListKernels",{user:username,search:kernelSlug,pageSize:50});
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
  const version=Number(exact[0]?.currentVersionNumber??exact[0]?.current_version_number??0);
  if(!version) throw err("Kaggle idempotency conflict: existing kernel has no version");
  const st=await rpc(cfg.token,"kernels.KernelsApiService","GetKernelSessionStatus",{userName:username,kernelSlug,versionLabel:"v"+version});
  return {version,state:stateOf(st?.status),provider_status:st?.status??null};
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

async function resolveKernel(cfg,username,ref){
  let last=null;
  for(const slug of [ref.kernel_slug,ref.direct_kernel_slug]){
    try{
      const st=await rpc(cfg.token,"kernels.KernelsApiService","GetKernelSessionStatus",{userName:username,kernelSlug:slug,versionLabel:"v"+ref.version});
      return {slug,st};
    }catch(e){last=e}
  }
  throw last||err("Kaggle kernel resolution failed");
}

export function configFromEnv(env=process.env){
  return {
    token:String(env.KAGGLE_API_TOKEN||"").trim(),
    username:String(env.KAGGLE_USERNAME_SLUG||"").trim(),
    inputToken:String(env.ND_LTX_INPUT_TOKEN||"").trim(),
    railwayBase:String(env.ND_LTX_RAILWAY_BASE||DEFAULT_RAILWAY_BASE).replace(/\/+$/,"")
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
    cost_policy:"FREE_ONLY"
  };
}

export async function submit(args={},cfg=configFromEnv()){
  const [startInput,endInput]=await Promise.all([
    prepareInput(args.start_image_url,cfg,"start"),
    prepareInput(args.end_image_url,cfg,"end")
  ]);
  const username=await identity(cfg);
  const seed=Number(args.seed??42);
  const prompt=String(args.prompt||"").trim();
  const negativePrompt=String(args.negative_prompt||"").trim()||undefined;
  const duration=Number(args.duration_seconds??2);
  const width=Number(args.width??512),height=Number(args.height??288);
  const effect=effectRef({
    startInput,endInput,prompt,negativePrompt,duration,width,height,seed,
    idempotencyKey:args.idempotency_key
  });
  const found=await existing(cfg,username,effect.kernel_slug);
  if(found){
    return {
      ok:true,state:found.state,reused_existing:true,
      request_id:"k2b-"+effect.token+"-v"+found.version,
      effect_id:effect.effect_id,
      provider_ref:username+"/"+effect.kernel_slug+"/"+found.version,
      provider_status:found.provider_status,
      route:"kaggle_ltx2b_direct_f2l",cost_policy:"FREE_ONLY",seed,
      nonblocking:true,caller_action:"CONTINUE_OTHER_USEFUL_WORK"
    };
  }
  const pf=await preflight(cfg,username);
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
    });
  }catch(e){
    const msg=String(e?.message||e);
    if(/429|RESOURCE_EXHAUSTED|maximum.*GPU|batch GPU session|capacity|quota/i.test(msg)){
      return {ok:false,state:"CAPACITY_BLOCKED",effect_id:effect.effect_id,route:"kaggle_ltx2b_direct_f2l",
        cost_policy:"FREE_ONLY",retry_after_seconds:60,nonblocking:true,
        caller_action:"CONTINUE_OTHER_USEFUL_WORK_AND_RETRY_LATER",error:msg.slice(0,1200)};
    }
    const s=Number(e?.status||0);
    if(!s||s===408||s===409||s>=500){
      try{
        const reconciled=await existing(cfg,username,effect.kernel_slug);
        if(reconciled){
          return {ok:true,state:reconciled.state,reused_existing:true,
            request_id:"k2b-"+effect.token+"-v"+reconciled.version,effect_id:effect.effect_id,
            provider_ref:username+"/"+effect.kernel_slug+"/"+reconciled.version,
            provider_status:reconciled.provider_status,route:"kaggle_ltx2b_direct_f2l",
            cost_policy:"FREE_ONLY",gpu_quota:pf.gpu,seed,nonblocking:true,
            caller_action:"CONTINUE_OTHER_USEFUL_WORK"};
        }
      }catch{}
      return {ok:false,state:"SUBMIT_AMBIGUOUS",effect_id:effect.effect_id,route:"kaggle_ltx2b_direct_f2l",
        cost_policy:"FREE_ONLY",retry_after_seconds:30,nonblocking:true,
        caller_action:"RECHECK_SAME_EFFECT_LATER_DO_NOT_RESUBMIT",error:msg.slice(0,1200)};
    }
    throw e;
  }
  const invalid=save?.invalidKernelSources||save?.invalid_kernel_sources||[];
  if(save?.error||invalid.length) throw err("Kaggle submit failed "+JSON.stringify({error:save?.error||null,invalid_kernel_sources:invalid}));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw err("Kaggle submit returned no version");
  return {
    ok:true,state:"SUBMITTED",reused_existing:false,
    request_id:"k2b-"+effect.token+"-v"+version,effect_id:effect.effect_id,
    provider_ref:username+"/"+effect.kernel_slug+"/"+version,
    route:"kaggle_ltx2b_direct_f2l",worker_mode:"DIRECT_LTX",
    cache_sources:cacheSources,machine_shape_requested:"NvidiaTeslaT4",
    cost_policy:"FREE_ONLY",gpu_quota:pf.gpu,seed,nonblocking:true,
    caller_action:"CONTINUE_OTHER_USEFUL_WORK"
  };
}

export async function status(args={},cfg=configFromEnv()){
  const ref=requestRef(args.request_id);
  const username=await identity(cfg);
  const resolved=await resolveKernel(cfg,username,ref);
  const state=stateOf(resolved.st?.status);
  return {
    ok:true,request_id:ref.request_id,state,
    provider_status:resolved.st?.status??null,
    failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,
    provider_ref:username+"/"+resolved.slug+"/"+ref.version,
    nonblocking:true,
    next_check_after_seconds:state==="QUEUED"?30:(state==="RUNNING"?45:null)
  };
}

export async function result(args={},cfg=configFromEnv()){
  const ref=requestRef(args.request_id);
  const username=await identity(cfg);
  const resolved=await resolveKernel(cfg,username,ref);
  const state=stateOf(resolved.st?.status);
  if(state!=="COMPLETED") return {
    ok:false,request_id:ref.request_id,state,
    provider_status:resolved.st?.status??null,
    failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,
    nonblocking:true
  };
  const files=[];
  let pageToken=null;
  for(let page=0;page<20;page++){
    const body={userName:username,kernelSlug:resolved.slug,pageSize:100};
    if(pageToken) body.pageToken=pageToken;
    const out=await rpc(cfg.token,"kernels.KernelsApiService","ListKernelSessionOutput",body);
    if(Array.isArray(out?.files)) files.push(...out.files);
    const next=String(out?.nextPageToken||out?.next_page_token||"").trim();
    if(!next||next===pageToken) break;
    pageToken=next;
  }
  const byName=name=>files.find(x=>(x?.fileName||x?.name||x?.path)===name);
  const mp4=byName("result.mp4"), receipt=byName("result.json");
  const videoUrl=mp4?.url||await outputUrl(cfg.token,username,resolved.slug,"result.mp4",ref.version);
  let receiptUrl=receipt?.url||null;
  if(!receiptUrl){try{receiptUrl=await outputUrl(cfg.token,username,resolved.slug,"result.json",ref.version)}catch{}}
  return {
    ok:true,request_id:ref.request_id,state:"READY",
    route:"kaggle_ltx2b_direct_f2l",
    provider_ref:username+"/"+resolved.slug+"/"+ref.version,
    provider_video_url:videoUrl,provider_receipt_url:receiptUrl,
    video_ref:videoUrl,persistence_state:"NOT_REQUESTED",
    nonblocking:true
  };
}
