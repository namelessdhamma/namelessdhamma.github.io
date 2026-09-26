import { Client, handle_file } from '@gradio/client';
import AdmZip from 'adm-zip';

const DEFAULT_SPACE = process.env.ND_WAN_DEFAULT_SPACE || 'Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom';
const HF_TOKEN = String(process.env.HF_TOKEN || '').trim();
const DEFAULT_LTX_SPACE = String(process.env.ND_LTX_PRIMARY_SPACE || 'DeepRat/LTX-Video-ZeroGPU-Optimized').trim();
const DEFAULT_LTX_RESERVES = String(process.env.ND_LTX_RESERVE_SPACES || 'Lightricks/ltx-video-distilled')
  .split(',').map(x => x.trim()).filter(Boolean);
const LTX_I2V_PRIMARY_SPACE = String(process.env.ND_LTX_I2V_PRIMARY_SPACE || 'DeepRat/LTX-Video-ZeroGPU-Optimized').trim();
const LTX_KEYFRAME_PRIMARY_SPACE = String(process.env.ND_LTX_KEYFRAME_PRIMARY_SPACE || '').trim();
const LTX_KEYFRAME_RESERVES = String(process.env.ND_LTX_KEYFRAME_RESERVE_SPACES || 'techfreakworm/LTX2.3-Studio,linoyts/ltx-2-first-last-frame')
  .split(',').map(x => x.trim()).filter(Boolean);

const KAGGLE_API_TOKEN = String(process.env.KAGGLE_API_TOKEN || '').trim();
const KAGGLE_USERNAME_SLUG = String(process.env.KAGGLE_USERNAME_SLUG || '').trim();
const KAGGLE_LTX_DATASET = 'damnyadav/ltxv13b-distilled-cache';
const KAGGLE_LTX_KERNEL = 'nd-ltx-first-last-production';
const KAGGLE_LTX_DRIVE_FOLDER = String(process.env.ND_LTX_DRIVE_FOLDER_ID || '1Qe6zqqZZzAohSt96_z4vkTcNAcGIThPh').trim();
const DRIVE_BRIDGE_KEY = String(process.env.ND_DRIVE_BRIDGE_TOKEN || '').trim();
const LTX_INPUT_TOKEN = String(process.env.ND_LTX_INPUT_TOKEN || '').trim();
const LTX_PUBLIC_BASE = String(process.env.ND_LTX_PUBLIC_BASE || 'https://nd-external-intelligence-production.up.railway.app').replace(/\/$/,'');
const OUTER_PORT = Number(process.env.PORT || 8080);

const GITHUB_PAT = String(process.env.ND_GITHUB_PAT || '').trim();
const LTX_HFJOBS_ENABLED = /^(1|true|yes)$/i.test(String(process.env.ND_LTX_HFJOBS_PAID_ENABLED || 'false').trim());
const LTX_HFJOBS_REPO = 'namelessdhamma/ND-app';
const LTX_HFJOBS_MAX_COST_USD = 0.405;

const STORYBOARD_REPO = 'namelessdhamma/namelessdhamma.github.io';
const STORYBOARD_EVENT = 'nd_storyboard_render';
const STORYBOARD_MCP_TOKEN = String(process.env.ND_STORYBOARD_MCP_PATH_TOKEN || '').trim();
const STORYBOARD_PUBLIC_BASE = String(process.env.ND_STORYBOARD_PUBLIC_BASE || 'https://nd-external-intelligence-production.up.railway.app').replace(/\/$/,'');

function configuredLtxSpaces(){
  return [...new Set([DEFAULT_LTX_SPACE, LTX_I2V_PRIMARY_SPACE, LTX_KEYFRAME_PRIMARY_SPACE, ...DEFAULT_LTX_RESERVES, ...LTX_KEYFRAME_RESERVES].filter(Boolean))];
}

function json(res,status,obj){
  const raw=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{'content-type':'application/json','content-length':raw.length,'cache-control':'no-store'});
  res.end(raw);
}
function errorText(e){return String(e?.stack||e?.message||e).slice(0,4000);}

async function githubJson(path,{method='GET',body}={}){
  if(!GITHUB_PAT) throw new Error('ND_GITHUB_PAT is not configured');
  const res=await fetch('https://api.github.com'+path,{
    method,
    headers:{
      'accept':'application/vnd.github+json',
      'authorization':'Bearer '+GITHUB_PAT,
      'x-github-api-version':'2022-11-28',
      ...(body?{'content-type':'application/json'}:{})
    },
    body:body?JSON.stringify(body):undefined
  });
  const txt=await res.text();
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,4000)};}
  if(!res.ok) throw new Error('GitHub API '+res.status+': '+JSON.stringify(data).slice(0,3000));
  return data;
}

async function ltxQuotaIndependentSubmit(args={}){
  if(!LTX_HFJOBS_ENABLED){
    return {
      ok:false,
      state:'DISABLED_REQUIRES_PAID_AUTHORIZATION',
      route:'HF Jobs / L4 / LTX 2B distilled FP8',
      daily_generation_quota:'NONE',
      billing:'pay_as_you_go_per_minute',
      max_job_timeout_minutes:30,
      estimated_max_cost_usd:LTX_HFJOBS_MAX_COST_USD,
      note:'Infrastructure is staged but paid compute is deliberately disabled.'
    };
  }
  if(args.paid_compute_authorized !== true) throw new Error('paid_compute_authorized=true required');
  const prompt=String(args.prompt||'').trim();
  if(!prompt) throw new Error('prompt required');
  const request={
    paid_authorized:true,
    prompt,
    conditioning_media_urls:Array.isArray(args.conditioning_media_urls)?args.conditioning_media_urls:[],
    conditioning_start_frames:Array.isArray(args.conditioning_start_frames)?args.conditioning_start_frames:[],
    conditioning_strengths:Array.isArray(args.conditioning_strengths)?args.conditioning_strengths:undefined,
    width:Number(args.width??512),
    height:Number(args.height??768),
    num_frames:Number(args.num_frames??49),
    frame_rate:Number(args.frame_rate??24),
    seed:Number(args.seed??42)
  };
  const issue=await githubJson('/repos/'+LTX_HFJOBS_REPO+'/issues',{
    method:'POST',
    body:{
      title:'[ND-LTX-HFJOB] '+new Date().toISOString(),
      body:JSON.stringify(request)
    }
  });
  return {
    ok:true,
    state:'SUBMITTED',
    route:'HF Jobs / L4 / LTX 2B distilled FP8',
    issue_number:issue.number,
    issue_url:issue.html_url,
    max_job_timeout_minutes:30,
    estimated_max_cost_usd:LTX_HFJOBS_MAX_COST_USD
  };
}

async function ltxQuotaIndependentStatus(args={}){
  const n=Number(args.issue_number);
  if(!Number.isInteger(n)||n<1) throw new Error('issue_number required');
  const [issue,comments]=await Promise.all([
    githubJson('/repos/'+LTX_HFJOBS_REPO+'/issues/'+n),
    githubJson('/repos/'+LTX_HFJOBS_REPO+'/issues/'+n+'/comments')
  ]);
  const latest=Array.isArray(comments)&&comments.length?comments[comments.length-1]:null;
  return {
    issue_number:n,
    state:issue.state,
    issue_url:issue.html_url,
    latest_comment:latest?.body||null,
    updated_at:issue.updated_at,
    paid_route_enabled:LTX_HFJOBS_ENABLED
  };
}


function normalizeStoryboardManifest(args={}){
  const frames=Array.isArray(args.frames)?args.frames:[];
  if(frames.length<2 || frames.length>40) throw new Error('frames must contain 2..40 items');
  const normalizedFrames=frames.map((f,i)=>{
    const url=String(f?.url||'').trim();
    if(!/^https?:\/\//i.test(url)) throw new Error('frame '+i+' requires http(s) url');
    return {
      url,
      duration:Number(f?.duration??args.default_duration??1.4),
      motion:String(f?.motion||'slow_push_in'),
      transition:String(f?.transition||'fade')
    };
  });
  return {
    width:Number(args.width??640),
    height:Number(args.height??360),
    fps:Number(args.fps??24),
    default_duration:Number(args.default_duration??1.4),
    transition_duration:Number(args.transition_duration??0.30),
    frames:normalizedFrames
  };
}

function storyboardRequestId(){
  return 'sb-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10);
}

async function storyboardRenderSubmit(args={}){
  const manifest=normalizeStoryboardManifest(args);
  const requestId=storyboardRequestId();
  await githubJson('/repos/'+STORYBOARD_REPO+'/dispatches',{
    method:'POST',
    body:{
      event_type:STORYBOARD_EVENT,
      client_payload:{request_id:requestId,manifest}
    }
  });
  return {
    ok:true,
    state:'SUBMITTED',
    request_id:requestId,
    route:'public_github_actions_ffmpeg_storyboard',
    cost_policy:'FREE_ONLY',
    daily_generation_quota:'NONE',
    renderer:'ffmpeg-storyboard-v1',
    rife_state:'NOT_YET_QUALIFIED'
  };
}

async function storyboardRenderStatus(args={}){
  const requestId=String(args.request_id||'').trim();
  if(!/^sb-[a-z0-9-]+$/i.test(requestId)) throw new Error('valid request_id required');
  const runs=await githubJson('/repos/'+STORYBOARD_REPO+'/actions/runs?event=repository_dispatch&per_page=50');
  const list=Array.isArray(runs?.workflow_runs)?runs.workflow_runs:[];
  const title='ND Storyboard '+requestId;
  const run=list.find(r=>r?.name==='ND Storyboard Renderer' && r?.display_title===title)
    || list.find(r=>String(r?.display_title||'').includes(requestId));
  if(!run){
    return {ok:true,state:'SUBMITTED_NOT_YET_VISIBLE',request_id:requestId};
  }
  let artifact=null;
  if(run.status==='completed'){
    const arts=await githubJson('/repos/'+STORYBOARD_REPO+'/actions/runs/'+run.id+'/artifacts');
    const arr=Array.isArray(arts?.artifacts)?arts.artifacts:[];
    artifact=arr.find(a=>a?.name==='nd-storyboard-'+requestId)||arr[0]||null;
  }
  return {
    ok:run.conclusion!=='failure',
    request_id:requestId,
    state:run.status==='completed'?(run.conclusion==='success'?'COMPLETED':'FAILED'):String(run.status||'UNKNOWN').toUpperCase(),
    conclusion:run.conclusion||null,
    run_id:run.id,
    run_url:run.html_url,
    artifact:artifact?{
      id:artifact.id,
      name:artifact.name,
      size_in_bytes:artifact.size_in_bytes,
      expired:artifact.expired,
      archive_download_api_url:artifact.archive_download_url
    }:null
  };
}


async function storyboardArtifactBundle(requestId){
  const status=await storyboardRenderStatus({request_id:requestId});
  if(status.state!=='COMPLETED' || !status.artifact?.id){
    return {status,mp4:null,receipt:null};
  }
  if(status.artifact.expired) throw new Error('storyboard artifact expired');
  if(Number(status.artifact.size_in_bytes||0) > 150*1024*1024) throw new Error('storyboard artifact exceeds 150 MB result proxy limit');
  if(!GITHUB_PAT) throw new Error('ND_GITHUB_PAT is not configured');
  const res=await fetch('https://api.github.com/repos/'+STORYBOARD_REPO+'/actions/artifacts/'+status.artifact.id+'/zip',{
    headers:{
      'accept':'application/vnd.github+json',
      'authorization':'Bearer '+GITHUB_PAT,
      'x-github-api-version':'2022-11-28'
    },
    redirect:'follow'
  });
  if(!res.ok) throw new Error('GitHub artifact download '+res.status);
  const buf=Buffer.from(await res.arrayBuffer());
  const zip=new AdmZip(buf);
  const mp4Entry=zip.getEntry('storyboard-output.mp4');
  const receiptEntry=zip.getEntry('storyboard-receipt.json');
  if(!mp4Entry) throw new Error('storyboard-output.mp4 missing from artifact');
  let receipt=null;
  if(receiptEntry){
    try{receipt=JSON.parse(receiptEntry.getData().toString('utf8'));}catch{}
  }
  return {status,mp4:mp4Entry.getData(),receipt};
}

async function storyboardRenderResult(args={}){
  const requestId=String(args.request_id||'').trim();
  if(!/^sb-[a-z0-9-]+$/i.test(requestId)) throw new Error('valid request_id required');
  const bundle=await storyboardArtifactBundle(requestId);
  if(!bundle.mp4){
    return {ok:false,request_id:requestId,state:bundle.status.state,status:bundle.status};
  }
  const base=STORYBOARD_PUBLIC_BASE+'/storyboard-result/'+STORYBOARD_MCP_TOKEN+'/'+requestId;
  return {
    ok:true,
    request_id:requestId,
    state:'READY',
    mp4_url:base+'.mp4',
    receipt_url:base+'.json',
    bytes:bundle.mp4.length,
    receipt:bundle.receipt,
    artifact:bundle.status.artifact
  };
}

export async function storyboardResultBytes(requestId){
  const id=String(requestId||'').trim();
  if(!/^sb-[a-z0-9-]+$/i.test(id)) throw new Error('valid request_id required');
  return storyboardArtifactBundle(id);
}

function connectOptions(){
  return HF_TOKEN ? { hf_token: HF_TOKEN } : {};
}

function transformFiles(value){
  if(Array.isArray(value)) return value.map(transformFiles);
  if(value && typeof value==='object'){
    const out={};
    for(const [k,v] of Object.entries(value)) out[k]=transformFiles(v);
    return out;
  }
  if(typeof value==='string' && value.startsWith('@file:')){
    return handle_file(value.slice(6));
  }
  return value;
}

function normalizeResult(result){
  const data=result?.data ?? result;
  return {
    data,
    endpoint: result?.endpoint || null,
    type: result?.type || null
  };
}

async function capabilities(spaceId){
  const app=await Client.connect(spaceId,connectOptions());
  const api=await app.view_api();
  return {space_id:spaceId,api};
}

async function generateVideo(args={}){
  const spaceId=String(args.space_id||DEFAULT_SPACE);
  const endpoint=String(args.api_name||'/generate_video');
  const input=String(args.input_image_url||'').trim();
  if(!input) throw new Error('input_image_url required');
  const last=String(args.last_image_url||'').trim();
  const app=await Client.connect(spaceId,connectOptions());
  const payload={
    input_image:handle_file(input),
    last_image:last?handle_file(last):null,
    prompt:String(args.prompt||''),
    steps:Number(args.steps??4),
    negative_prompt:String(args.negative_prompt||'static frame, slideshow, frozen body, morphing face, extra fingers, deformed hands, duplicate limbs, low quality, cartoon, text, watermark'),
    duration_seconds:Number(args.duration_seconds??2.5),
    guidance_scale:Number(args.guidance_scale??1),
    guidance_scale_2:Number(args.guidance_scale_2??1),
    seed:Number(args.seed??42),
    randomize_seed:Boolean(args.randomize_seed??false),
    quality:Number(args.quality??5),
    scheduler:String(args.scheduler||'UniPCMultistep'),
    flow_shift:Number(args.flow_shift??3),
    frame_multiplier:Number(args.frame_multiplier??16),
    safe_mode:Boolean(args.safe_mode??false),
    video_component:Boolean(args.video_component??true)
  };
  const result=await app.predict(endpoint,payload);
  return {space_id:spaceId,api_name:endpoint,...normalizeResult(result)};
}

async function ltxCapabilities(args={}){
  const spaceId=String(args.space_id||DEFAULT_LTX_SPACE).trim();
  if(!spaceId) throw new Error('LTX space_id required');
  return capabilities(spaceId);
}

async function ltxRawCall(args={}){
  return rawCall({...args,space_id:String(args.space_id||DEFAULT_LTX_SPACE)});
}

function findVideoRef(value){
  if(value == null) return null;
  if(typeof value === 'string' && /\.mp4(?:$|\?)/i.test(value)) return value;
  if(Array.isArray(value)){
    for(const v of value){ const hit=findVideoRef(v); if(hit) return hit; }
    return null;
  }
  if(typeof value === 'object'){
    for(const key of ['url','path','video','name']){
      if(key in value){ const hit=findVideoRef(value[key]); if(hit) return hit; }
    }
    for(const v of Object.values(value)){ const hit=findVideoRef(v); if(hit) return hit; }
  }
  return null;
}


async function kaggleRpc(service,method,body={}){
  if(!KAGGLE_API_TOKEN) throw new Error('KAGGLE_API_TOKEN is not configured');
  const res=await fetch('https://api.kaggle.com/v1/'+service+'/'+method,{
    method:'POST',
    headers:{
      authorization:'Bearer '+KAGGLE_API_TOKEN,
      accept:'application/json',
      'content-type':'application/json',
      'user-agent':'nd-ltx-kaggle/1.0'
    },
    body:JSON.stringify(body)
  });
  const txt=await res.text();
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,1200)};}
  if(!res.ok){
    const raw=data?.message??data?.error??data??txt;
    let detail;
    try{detail=typeof raw==='string'?raw:JSON.stringify(raw);}catch{detail=String(raw);}
    throw new Error('Kaggle HTTP '+res.status+': '+String(detail).slice(0,1800));
  }
  return data;
}

function kaggleDurationSeconds(v){
  if(typeof v==='number') return v;
  if(typeof v==='string'){
    const m=v.match(/^(-?\d+(?:\.\d+)?)s$/);
    return m?Number(m[1]):Number(v)||0;
  }
  if(v&&typeof v==='object') return Number(v.seconds||0)+Number(v.nanos||0)/1e9;
  return 0;
}

async function kaggleLtxIdentity(){
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('Kaggle token inactive');
  const username=String(intro.username);
  if(KAGGLE_USERNAME_SLUG && username!==KAGGLE_USERNAME_SLUG) throw new Error('Kaggle username mismatch');
  return {username};
}

async function kaggleLtxPreflight(){
  const {username}=await kaggleLtxIdentity();
  const quota=await kaggleRpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{});
  const g=quota?.gpuQuota||quota?.gpu_quota||{};
  const used=kaggleDurationSeconds(g?.timeUsed??g?.time_used);
  const total=kaggleDurationSeconds(g?.totalTimeAllowed??g?.total_time_allowed);
  const remaining=Math.max(0,total-used);
  if(total<=0) throw new Error('FREE_ONLY_BLOCKED: Kaggle GPU quota unavailable');
  if(remaining<15*60) throw new Error('FREE_ONLY_BLOCKED: less than 15 minutes Kaggle GPU quota remains');
  return {
    username,
    gpu:{
      used_hours:Number((used/3600).toFixed(3)),
      total_hours:Number((total/3600).toFixed(3)),
      remaining_hours:Number((remaining/3600).toFixed(3)),
      refresh_at:quota?.quotaRefreshTime||quota?.quota_refresh_time||null
    }
  };
}

function kaggleLtxRequestRef(requestId){
  const id=String(requestId||'').trim();
  let m=id.match(/^kltx-v(\d+)$/i);
  if(m) return {request_id:id,kernel_slug:KAGGLE_LTX_KERNEL,version:Number(m[1]),legacy:true};
  m=id.match(/^kltx-(r[a-z0-9]+-[a-z0-9]+)-v(\d+)$/i);
  if(m) return {request_id:id,kernel_slug:'nd-ltx-'+m[1],version:Number(m[2]),legacy:false};
  throw new Error('valid request_id required');
}

function newKaggleLtxKernelRef(){
  const token='r'+Date.now().toString(36)+'-'+Math.floor(Math.random()*1679616).toString(36).padStart(4,'0');
  return {token,kernel_slug:'nd-ltx-'+token};
}

function kaggleState(status){
  const s=String(status??'').toUpperCase();
  if(s==='2'||s.includes('COMPLETE')) return 'COMPLETED';
  if(s==='3'||s.includes('ERROR')||s.includes('FAIL')) return 'FAILED';
  if(s==='4'||s==='5'||s.includes('CANCEL')) return 'CANCELLED';
  if(s==='1'||s.includes('RUN')) return 'RUNNING';
  return 'QUEUED';
}

function extractKaggleMarker(log,marker){
  const chunks=[String(log||'')];
  const visit=v=>{
    if(v==null) return;
    if(typeof v==='string'){chunks.push(v);return;}
    if(Array.isArray(v)){for(const x of v) visit(x);return;}
    if(typeof v==='object'){for(const x of Object.values(v)) visit(x);}
  };
  try{visit(JSON.parse(String(log||'')));}catch{}
  for(const raw0 of chunks){
    for(const raw of [String(raw0),String(raw0).replace(/\\\"/g,'"').replace(/\\n/g,'\n')]){
      const p=raw.indexOf(marker);
      if(p<0) continue;
      const start=raw.indexOf('{',p+marker.length);
      if(start<0) continue;
      let depth=0,quote=null,esc=false;
      for(let i=start;i<raw.length;i++){
        const ch=raw[i];
        if(esc){esc=false;continue;}
        if(ch==='\\'){esc=true;continue;}
        if(quote){if(ch===quote)quote=null;continue;}
        if(ch==='"'||ch==="'"){quote=ch;continue;}
        if(ch==='{') depth++;
        else if(ch==='}'){
          depth--;
          if(depth===0){
            const candidate=raw.slice(start,i+1);
            try{return JSON.parse(candidate);}catch{}
            try{return JSON.parse(candidate.replace(/\\\"/g,'"'));}catch{}
            break;
          }
        }
      }
    }
  }
  return null;
}

function resolveLtxInputRef(value){
  const ref=String(value||'').trim();
  if(/^https?:\/\//i.test(ref)) return ref;
  const m=ref.match(/^drive:([A-Za-z0-9_-]{10,200})$/i);
  if(m){
    if(!LTX_INPUT_TOKEN) throw new Error('ND_LTX_MCP_PATH_TOKEN is not configured');
    return LTX_PUBLIC_BASE+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  }
  throw new Error('image ref must be http(s) URL or drive:<fileId>');
}

async function prepareLtxKernelInput(value,label){
  const ref=String(value||'').trim();
  const m=ref.match(/^drive:([A-Za-z0-9_-]{10,200})$/i);
  if(!m) return {url:resolveLtxInputRef(ref),base64:null};
  if(!LTX_INPUT_TOKEN) throw new Error('ND_LTX_INPUT_TOKEN is not configured');
  const publicUrl=LTX_PUBLIC_BASE+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  const local='http://127.0.0.1:'+OUTER_PORT+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  const res=await fetch(local);
  if(!res.ok) throw new Error(label+' Drive input read failed HTTP '+res.status);
  const ct=String(res.headers.get('content-type')||'');
  if(!ct.startsWith('image/')) throw new Error(label+' Drive input is not an image');
  const declared=Number(res.headers.get('content-length')||0);
  if(declared<=0||declared>20*1024*1024) throw new Error(label+' Drive input size invalid');
  return {url:publicUrl,base64:null,content_type:ct,size_bytes:declared};
}

async function ltxKaggleSubmit(args={}){
  const [startInput,endInput]=await Promise.all([
    prepareLtxKernelInput(args.start_image_url,'start'),
    prepareLtxKernelInput(args.end_image_url,'end')
  ]);
  const preflight=await kaggleLtxPreflight();
  const seed=args.randomize_seed===true?Math.floor(Math.random()*2147483647):Number(args.seed??42);
  const request={
    start_image_url:startInput.url||undefined,
    end_image_url:endInput.url||undefined,
    start_image_base64:startInput.base64||undefined,
    end_image_base64:endInput.base64||undefined,
    prompt:String(args.prompt||'').trim(),
    negative_prompt:String(args.negative_prompt||'').trim()||undefined,
    duration_seconds:Number(args.duration_seconds??2),
    width:Number(args.width??864),
    height:Number(args.height??480),
    seed
  };
  const reqB64=Buffer.from(JSON.stringify(request),'utf8').toString('base64');
  const workerUrl='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx_worker.py';
  const script=[
    'import base64,sys,urllib.request',
    'from pathlib import Path',
    "request_path=Path('/kaggle/working/nd-ltx-request.json')",
    "request_path.write_bytes(base64.b64decode('"+reqB64+"'))",
    "sys.argv=['kaggle_ltx_worker.py',str(request_path)]",
    "req=urllib.request.Request('"+workerUrl+"',headers={'User-Agent':'nd-kaggle-ltx/1.0'})",
    "source=urllib.request.urlopen(req,timeout=120).read().decode('utf-8')",
    "exec(compile(source,'kaggle_ltx_worker.py','exec'),{'__name__':'__main__'})"
  ].join('\n');
  if(Buffer.byteLength(script,'utf8')>=900000) throw new Error('Kaggle kernel source preflight exceeds 900 KB: '+Buffer.byteLength(script,'utf8'));
  const jobRef=newKaggleLtxKernelRef();
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:preflight.username+'/'+jobRef.kernel_slug,
    newTitle:'ND LTX '+jobRef.token,
    text:script,
    language:'python',
    kernelType:'script',
    datasetDataSources:[KAGGLE_LTX_DATASET],
    kernelDataSources:[],
    competitionDataSources:[],
    categoryIds:[],
    modelDataSources:[],
    isPrivate:true,enableTpu:false,enableInternet:true,
    machineShape:requestedShape,
    sessionTimeoutSeconds:3600
  });
  const invalid=save?.invalidDatasetSources||save?.invalid_dataset_sources||[];
  if(save?.error||invalid.length) throw new Error('Kaggle submit failed: '+JSON.stringify({error:save?.error||null,invalid_dataset_sources:invalid}));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('Kaggle submit returned no version');
  const requestId='kltx-'+jobRef.token+'-v'+version;
  setTimeout(()=>ltxKaggleAutoFinalize(requestId).catch(e=>console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:requestId,state:'ERROR',error:errorText(e)}))),10000);
  return {
    ok:true,
    state:'SUBMITTED',
    request_id:requestId,
    provider_ref:preflight.username+'/'+jobRef.kernel_slug+'/'+version,
    route:'kaggle_ltx13b_mounted_cache_f2l',
    cost_policy:'FREE_ONLY',
    gpu_quota:preflight.gpu,
    seed
  };
}

async function ltxKaggleStatus(args={}){
  const ref=kaggleLtxRequestRef(args.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
    userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version
  });
  const state=kaggleState(st?.status);
  let diagnostics=null;
  if(['QUEUED','RUNNING','FAILED','CANCELLED','COMPLETED'].includes(state)){
    try{
      const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
        userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version,pageSize:100
      });
      const files=Array.isArray(out?.files)?out.files.map(x=>({
        name:x?.fileName||x?.name||x?.path||null,
        size:x?.fileSize??x?.size??null
      })).filter(x=>x.name):[];
      diagnostics={files,log_tail:String(out?.log||'').slice(-12000)};
    }catch(e){diagnostics={error:errorText(e)};}
  }
  return {
    ok:true,
    request_id:ref.request_id,
    state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:username+'/'+ref.kernel_slug+'/'+ref.version,
    diagnostics
  };
}

async function driveImportKaggleOutput(url,name,mimeType){
  if(!DRIVE_BRIDGE_KEY) throw new Error('ND_DRIVE_BRIDGE_TOKEN is not configured');
  const res=await fetch('http://127.0.0.1:'+OUTER_PORT+'/internal/kaggle-ltx/import-output',{
    method:'POST',
    headers:{'content-type':'application/json','x-nd-bridge-key':DRIVE_BRIDGE_KEY},
    body:JSON.stringify({url,name,mime_type:mimeType,parent_id:KAGGLE_LTX_DRIVE_FOLDER})
  });
  const txt=await res.text();
  let data={};
  try{data=txt?JSON.parse(txt):{};}catch{}
  if(!res.ok||data?.ok!==true) throw new Error('Drive import failed: '+String(data?.error||txt).slice(0,1000));
  return data.result;
}

async function ltxKaggleResult(args={}){
  const ref=kaggleLtxRequestRef(args.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
    userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version
  });
  const state=kaggleState(st?.status);
  if(state!=='COMPLETED') return {
    ok:false,request_id:ref.request_id,state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null
  };
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version,pageSize:100
  });
  const files=Array.isArray(out?.files)?out.files:[];
  const byName=name=>files.find(x=>(x?.fileName||x?.name||x?.path)===name);
  const mp4=byName('result.mp4');
  const receiptFile=byName('result.json');
  if(!mp4?.url) throw new Error('result.mp4 missing from Kaggle output');
  const receipt=extractKaggleMarker(out?.log||'','ND_LTX_F2L_JSON=');
  const driveVideo=await driveImportKaggleOutput(mp4.url,'nd-ltx-'+ref.request_id+'.mp4','video/mp4');
  let driveReceipt=null;
  if(receiptFile?.url){
    driveReceipt=await driveImportKaggleOutput(receiptFile.url,'nd-ltx-'+ref.request_id+'.json','application/json');
  }
  const file=driveVideo?.file||{};
  return {
    ok:true,
    request_id:ref.request_id,
    state:'READY',
    route:'kaggle_ltx13b_mounted_cache_f2l',
    provider_ref:username+'/'+ref.kernel_slug+'/'+ref.version,
    receipt,
    video_ref:file.webViewLink||null,
    drive_video:{
      id:file.id||null,name:file.name||null,size:Number(file.size||0),
      mime_type:file.mimeType||null,url:file.webViewLink||null,reused:driveVideo?.reused===true
    },
    drive_receipt:driveReceipt?.file?{
      id:driveReceipt.file.id||null,name:driveReceipt.file.name||null,
      url:driveReceipt.file.webViewLink||null,reused:driveReceipt?.reused===true
    }:null
  };
}

async function ltxKaggleBuild2bCache(){
  const {username}=await kaggleLtxIdentity();
  const slug='nd-ltx-2b-distilled-cache';
  const fullSlug=username+'/'+slug;
  const title='ND LTX 2B Distilled Cache';
  const script=[
    'from pathlib import Path',
    'import hashlib,json,urllib.request',
    "root=Path('/kaggle/working/ltxv-2b-distilled')",
    "(root/'transformer').mkdir(parents=True,exist_ok=True)",
    "(root/'scheduler').mkdir(parents=True,exist_ok=True)",
    "files={",
    " 'transformer/config.json':'https://huggingface.co/multimodalart/ltxv-2b-0.9.6-distilled/resolve/main/transformer/config.json?download=true',",
    " 'transformer/diffusion_pytorch_model.bf16.safetensors':'https://huggingface.co/multimodalart/ltxv-2b-0.9.6-distilled/resolve/main/transformer/diffusion_pytorch_model.bf16.safetensors?download=true',",
    " 'scheduler/scheduler_config.json':'https://huggingface.co/multimodalart/ltxv-2b-0.9.6-distilled/resolve/main/scheduler/scheduler_config.json?download=true'",
    "}",
    "out={}",
    "for rel,url in files.items():",
    "    dest=root/rel",
    "    req=urllib.request.Request(url,headers={'User-Agent':'nd-kaggle-ltx-cache/1.0'})",
    "    h=hashlib.sha256(); n=0",
    "    with urllib.request.urlopen(req,timeout=300) as src, dest.open('wb') as dst:",
    "        while True:",
    "            chunk=src.read(4*1024*1024)",
    "            if not chunk: break",
    "            dst.write(chunk); h.update(chunk); n+=len(chunk)",
    "    out[rel]={'size_bytes':n,'sha256':h.hexdigest()}",
    "print('ND_LTX_2B_CACHE_JSON='+json.dumps(out,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:title,text:script,language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],modelDataSources:[],
    isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:true,sessionTimeoutSeconds:1800
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version||save?.error) throw new Error('Kaggle 2B cache submit failed '+JSON.stringify({error:save?.error||null}));
  return {ok:true,state:'SUBMITTED',provider_ref:fullSlug+'/'+version,kernel_source:fullSlug,version};
}

async function ltxKaggle2bCacheStatus(){
  const {username}=await kaggleLtxIdentity();
  const slug='nd-ltx-2b-distilled-cache';
  const fullSlug=username+'/'+slug;
  const version=1;
  const versionLabel='v'+version;
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
  const state=kaggleState(st?.status);
  let receipt=null,diagnostics=null;
  if(['COMPLETED','FAILED','CANCELLED'].includes(state)){
    const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
    receipt=extractKaggleMarker(out?.log||'','ND_LTX_2B_CACHE_JSON=');
    diagnostics={
      files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],
      log_tail:String(out?.log||'').slice(-8000)
    };
  }
  return {
    ok:state==='COMPLETED'&&!!receipt,
    state,provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:fullSlug+'/'+version,kernel_source:fullSlug,receipt,diagnostics
  };
}

async function ltxKaggleRetry(args={}){
  const ref=kaggleLtxRequestRef(args.request_id);
  if(ref.legacy) throw new Error('retry is supported only for isolated Kaggle LTX requests');
  if(ref.version>=3) throw new Error('retry limit reached for '+ref.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await ltxKaggleStatus({request_id:ref.request_id});
  if(!['FAILED','CANCELLED'].includes(st.state)) throw new Error('retry requires FAILED or CANCELLED state');
  const files=st?.diagnostics?.files||[];
  const logTail=String(st?.diagnostics?.log_tail||'').trim();
  const emptyLog=logTail===''||logTail==='[]'||logTail==='{}'||logTail==='null';
  if(files.length||!emptyLog) throw new Error('retry blocked because provider produced files or logs; diagnose actual execution failure instead');
  const preflight=await kaggleLtxPreflight();
  const pulled=await kaggleRpc('kernels.KernelsApiService','GetKernel',{
    userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version
  });
  const source=String(pulled?.blob?.source||pulled?.blob?.text||'');
  if(!source) throw new Error('retry source unavailable from Kaggle GetKernel');
  if(Buffer.byteLength(source,'utf8')>=900000) throw new Error('retry source exceeds Kaggle limit');
  const title=String(pulled?.metadata?.title||('ND LTX '+ref.kernel_slug.replace(/^nd-ltx-/,''))).slice(0,120);
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:username+'/'+ref.kernel_slug,
    newTitle:title,
    text:source,
    language:'python',
    kernelType:'script',
    datasetDataSources:[KAGGLE_LTX_DATASET],
    kernelDataSources:[],
    competitionDataSources:[],
    categoryIds:[],
    modelDataSources:[],
    isPrivate:true,enableTpu:false,enableInternet:true,
    machineShape:'NvidiaTeslaT4',
    sessionTimeoutSeconds:3600
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version||save?.error) throw new Error('Kaggle retry submit failed '+JSON.stringify({error:save?.error||null}));
  const base=ref.request_id.replace(/-v\d+$/i,'');
  const requestId=base+'-v'+version;
  setTimeout(()=>ltxKaggleAutoFinalize(requestId).catch(e=>console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:requestId,state:'ERROR',error:errorText(e)}))),10000);
  return {
    ok:true,
    state:'RETRIED',
    previous_request_id:ref.request_id,
    request_id:requestId,
    provider_ref:username+'/'+ref.kernel_slug+'/'+version,
    route:'kaggle_ltx13b_mounted_cache_f2l',
    cost_policy:'FREE_ONLY',
    gpu_quota:preflight.gpu,
    retry_number:version-1
  };
}

function newKaggleLtxBatchRef(){
  const token='r'+Date.now().toString(36)+'-'+Math.floor(Math.random()*1679616).toString(36).padStart(4,'0');
  return {token,kernel_slug:'nd-ltx-batch-'+token};
}

function kaggleLtxBatchRequestRef(requestId){
  const id=String(requestId||'').trim();
  const m=id.match(/^kbatch-(r[a-z0-9]+-[a-z0-9]+)-v(\d+)$/i);
  if(!m) throw new Error('valid batch request_id required');
  return {request_id:id,kernel_slug:'nd-ltx-batch-'+m[1],version:Number(m[2])};
}

async function ltxKaggleBatchSubmit(spec={}){
  const segments=Array.isArray(spec.segments)?spec.segments:[];
  if(segments.length<1||segments.length>8) throw new Error('batch requires 1-8 segments');
  const preflight=await kaggleLtxPreflight();
  const prepared=[];
  for(let i=0;i<segments.length;i++){
    const seg=segments[i]||{};
    const [a,b]=await Promise.all([
      prepareLtxKernelInput(seg.start_image_url,'segment '+(i+1)+' start'),
      prepareLtxKernelInput(seg.end_image_url,'segment '+(i+1)+' end')
    ]);
    prepared.push({
      start_image_url:a.url,
      end_image_url:b.url,
      prompt:String(seg.prompt||'').trim(),
      negative_prompt:String(seg.negative_prompt||'').trim()||undefined,
      duration_seconds:Number(seg.duration_seconds??1),
      width:Number(seg.width??512),
      height:Number(seg.height??288),
      seed:Number(seg.seed??(200+i))
    });
  }
  const payload=Buffer.from(JSON.stringify({segments:prepared}),'utf8').toString('base64');
  const adaptive=spec.adaptive===true;
  const requestedShape=['NvidiaTeslaT4','NvidiaTeslaP100'].includes(String(spec.machine_shape||''))?String(spec.machine_shape):'NvidiaTeslaT4';
  const workerUrl=adaptive
    ? 'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx_worker_adaptive.py'
    : 'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx_worker.py';
  const script=[
    'import base64,json,os,subprocess,sys,urllib.request',
    'from pathlib import Path',
    "cfg=json.loads(base64.b64decode('"+payload+"').decode('utf-8'))",
    "worker=Path('/kaggle/working/kaggle_ltx_worker.py')",
    "req=urllib.request.Request('"+workerUrl+"',headers={'User-Agent':'nd-kaggle-ltx-batch/1.0'})",
    "worker.write_bytes(urllib.request.urlopen(req,timeout=120).read())",
    "receipts=[]",
    "for idx,seg in enumerate(cfg['segments'],start=1):",
    "    req_path=Path(f'/kaggle/working/segment-{idx:02d}-request.json')",
    "    req_path.write_text(json.dumps(seg),encoding='utf-8')",
    "    print(f'ND_LTX_BATCH_SEGMENT_START={idx:02d}',flush=True)",
    "    p=subprocess.run([sys.executable,'-u',str(worker),str(req_path)],timeout=3300)",
    "    print(f'ND_LTX_BATCH_SEGMENT_DONE={idx:02d} rc={p.returncode}',flush=True)",
    "    if p.returncode!=0: raise RuntimeError(f'segment {idx} failed rc={p.returncode}')",
    "    src_mp4=Path('/kaggle/working/result.mp4'); src_json=Path('/kaggle/working/result.json')",
    "    if not src_mp4.exists() or not src_json.exists(): raise RuntimeError(f'segment {idx} outputs missing')",
    "    dst_mp4=Path(f'/kaggle/working/segment-{idx:02d}.mp4'); dst_json=Path(f'/kaggle/working/segment-{idx:02d}.json')",
    "    if dst_mp4.exists(): dst_mp4.unlink()",
    "    if dst_json.exists(): dst_json.unlink()",
    "    src_mp4.replace(dst_mp4); src_json.replace(dst_json)",
    "    receipts.append(json.loads(dst_json.read_text(encoding='utf-8')))",
    "summary={'ok':True,'segment_count':len(receipts),'segments':receipts}",
    "Path('/kaggle/working/batch-result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')",
    "print('ND_LTX_BATCH_JSON='+json.dumps(summary,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  if(Buffer.byteLength(script,'utf8')>=900000) throw new Error('Kaggle batch source exceeds provider limit');
  const jobRef=newKaggleLtxBatchRef();
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:preflight.username+'/'+jobRef.kernel_slug,
    newTitle:'ND LTX Batch '+jobRef.token,
    text:script,
    language:'python',
    kernelType:'script',
    datasetDataSources:[KAGGLE_LTX_DATASET],
    kernelDataSources:[],
    competitionDataSources:[],
    categoryIds:[],
    modelDataSources:[],
    isPrivate:true,enableTpu:false,enableInternet:true,
    machineShape:'NvidiaTeslaT4',
    sessionTimeoutSeconds:3600
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version||save?.error) throw new Error('Kaggle batch submit failed '+JSON.stringify({error:save?.error||null}));
  const requestId='kbatch-'+jobRef.token+'-v'+version;
  setTimeout(()=>ltxKaggleBatchAutoFinalize(requestId).catch(e=>console.error(JSON.stringify({event:'ND_LTX_BATCH_AUTO_FINALIZE',request_id:requestId,state:'ERROR',error:errorText(e)}))),10000);
  return {
    ok:true,state:'SUBMITTED',request_id:requestId,
    provider_ref:preflight.username+'/'+jobRef.kernel_slug+'/'+version,
    route:adaptive?'kaggle_ltx13b_mounted_cache_batch_adaptive':'kaggle_ltx13b_mounted_cache_batch',
    machine_shape_requested:requestedShape,
    adaptive_worker:adaptive,
    segment_count:segments.length,cost_policy:'FREE_ONLY',gpu_quota:preflight.gpu
  };
}

async function ltxKaggleBatchStatus(args={}){
  const ref=kaggleLtxBatchRequestRef(args.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
    userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version
  });
  const state=kaggleState(st?.status);
  let diagnostics=null;
  if(['QUEUED','RUNNING','FAILED','CANCELLED','COMPLETED'].includes(state)){
    try{
      const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
        userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version,pageSize:100
      });
      diagnostics={
        files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],
        log_tail:String(out?.log||'').slice(-16000)
      };
    }catch(e){diagnostics={error:errorText(e)};}
  }
  return {
    ok:true,request_id:ref.request_id,state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:username+'/'+ref.kernel_slug+'/'+ref.version,
    diagnostics
  };
}

async function ltxKaggleBatchResult(args={}){
  const ref=kaggleLtxBatchRequestRef(args.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await ltxKaggleBatchStatus({request_id:ref.request_id});
  if(st.state!=='COMPLETED') return {ok:false,request_id:ref.request_id,state:st.state,failure_message:st.failure_message||null};
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version,pageSize:100
  });
  const files=Array.isArray(out?.files)?out.files:[];
  const receipt=extractKaggleMarker(out?.log||'','ND_LTX_BATCH_JSON=');
  const imported=[];
  for(let i=1;i<=8;i++){
    const tag=String(i).padStart(2,'0');
    const mp4=files.find(x=>(x?.fileName||x?.name||x?.path)==='segment-'+tag+'.mp4');
    const js=files.find(x=>(x?.fileName||x?.name||x?.path)==='segment-'+tag+'.json');
    if(!mp4?.url) break;
    const v=await driveImportKaggleOutput(mp4.url,'nd-ltx-'+ref.request_id+'-segment-'+tag+'.mp4','video/mp4');
    let j=null;
    if(js?.url) j=await driveImportKaggleOutput(js.url,'nd-ltx-'+ref.request_id+'-segment-'+tag+'.json','application/json');
    imported.push({
      segment:i,
      video:v?.file?{id:v.file.id||null,name:v.file.name||null,size:Number(v.file.size||0),url:v.file.webViewLink||null}:null,
      receipt:j?.file?{id:j.file.id||null,name:j.file.name||null,url:j.file.webViewLink||null}:null
    });
  }
  const batchJson=files.find(x=>(x?.fileName||x?.name||x?.path)==='batch-result.json');
  let batchReceiptDrive=null;
  if(batchJson?.url) batchReceiptDrive=await driveImportKaggleOutput(batchJson.url,'nd-ltx-'+ref.request_id+'-batch-result.json','application/json');
  return {
    ok:true,request_id:ref.request_id,state:'READY',
    route:'kaggle_ltx13b_mounted_cache_batch',
    provider_ref:username+'/'+ref.kernel_slug+'/'+ref.version,
    receipt,segments:imported,
    batch_receipt:batchReceiptDrive?.file?{id:batchReceiptDrive.file.id||null,name:batchReceiptDrive.file.name||null,url:batchReceiptDrive.file.webViewLink||null}:null
  };
}

async function ltxKaggleBatchAutoFinalize(requestId){
  for(let i=0;i<280;i++){
    const st=await ltxKaggleBatchStatus({request_id:requestId});
    if(st.state==='COMPLETED'){
      const result=await ltxKaggleBatchResult({request_id:requestId});
      console.log(JSON.stringify({event:'ND_LTX_BATCH_AUTO_FINALIZE',request_id:requestId,state:'READY',segments:result?.segments?.length||0}));
      return result;
    }
    if(st.state==='FAILED'||st.state==='CANCELLED'){
      console.error(JSON.stringify({event:'ND_LTX_BATCH_AUTO_FINALIZE',request_id:requestId,state:st.state,failure_message:st.failure_message||null,diagnostics:st.diagnostics||null}));
      return st;
    }
    await new Promise(r=>setTimeout(r,15000));
  }
  return {ok:false,request_id:requestId,state:'TIMEOUT'};
}

function decodeBatchSpec(encoded){
  try{return JSON.parse(Buffer.from(String(encoded||''),'base64url').toString('utf8'));}
  catch{throw new Error('invalid batch specification');}
}

async function ltxKaggleCacheInventory(){
  const owner='damnyadav',dataset='ltxv13b-distilled-cache';
  const queue=[''];
  const seen=new Set();
  const files=[];
  const dirs=[];
  while(queue.length){
    const path=queue.shift();
    if(seen.has(path)) continue;
    seen.add(path);
    let token='';
    do{
      const out=await kaggleRpc('datasets.DatasetApiService','ListTreeDatasetFiles',{
        ownerSlug:owner,
        datasetSlug:dataset,
        path,
        pageSize:200,
        ...(token?{pageToken:token}:{})
      });
      for(const d of (out?.directories||[])){
        const rel=String(d?.relativeUrl||d?.relative_url||d?.name||'').replace(/^\/+|\/+$/g,'');
        if(rel&&!seen.has(rel)){queue.push(rel);dirs.push({path:rel,total_files:d?.totalFiles??d?.total_files??null,total_children:d?.totalChildren??d?.total_children??null});}
      }
      for(const f of (out?.files||[])){
        const rel=String(f?.relativeUrl||f?.relative_url||f?.name||'').replace(/^\/+/, '');
        files.push({path:rel,size:Number(f?.totalBytes??f?.total_bytes??0)});
      }
      token=String(out?.nextPageToken||out?.next_page_token||'');
    }while(token);
  }
  files.sort((a,b)=>b.size-a.size);
  const neededRoots=['transformer/','text_encoder/','vae/','tokenizer/','scheduler/'];
  const needed=files.filter(f=>neededRoots.some(r=>f.path===r.slice(0,-1)||f.path.startsWith(r)));
  const total=files.reduce((a,f)=>a+f.size,0);
  const neededTotal=needed.reduce((a,f)=>a+f.size,0);
  const byRoot={};
  for(const r of neededRoots){
    const key=r.slice(0,-1);
    const xs=files.filter(f=>f.path===key||f.path.startsWith(r));
    byRoot[key]={files:xs.length,bytes:xs.reduce((a,f)=>a+f.size,0)};
  }
  return {
    ok:true,
    dataset:owner+'/'+dataset,
    total_files:files.length,
    total_bytes:total,
    total_gib:Number((total/2**30).toFixed(3)),
    minimal_runtime_files:needed.length,
    minimal_runtime_bytes:neededTotal,
    minimal_runtime_gib:Number((neededTotal/2**30).toFixed(3)),
    minimal_fits_19_5_gib:neededTotal<19.0*2**30,
    by_root:byRoot,
    top_files:files.slice(0,40),
    directories:dirs.slice(0,100)
  };
}

async function ltxKaggle2bLatestProbe(){
  const {username}=await kaggleLtxIdentity();
  const pages=[];
  for(let page=1;page<=5;page++){
    const listed=await kaggleRpc('kernels.KernelsApiService','ListKernels',{
      user:username,page,pageSize:100
    });
    pages.push(...(listed?.kernels||[]));
    if((listed?.kernels||[]).length<100) break;
  }
  const candidates=pages.filter(k=>String(k?.slug||'').startsWith('nd-ltx2b-load-probe-') || String(k?.title||'').startsWith('ND LTX2B Load Probe '));
  candidates.sort((a,b)=>String(b?.lastRunTime||b?.last_run_time||'').localeCompare(String(a?.lastRunTime||a?.last_run_time||'')));
  const k=candidates[0];
  if(!k) return {ok:false,state:'NOT_FOUND'};
  const slug=String(k.slug);
  const version=Number(k?.currentVersionNumber||k?.current_version_number||1);
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel:'v'+version});
  const state=kaggleState(st?.status);
  let output=null;
  if(['RUNNING','FAILED','CANCELLED','COMPLETED'].includes(state)){
    try{
      const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel:'v'+version,pageSize:100});
      output={
        receipt:extractKaggleMarker(out?.log||'','ND_LTX2B_LOAD_JSON='),
        files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],
        log_tail:String(out?.log||'').slice(-16000)
      };
    }catch(e){output={error:errorText(e)};}
  }
  return {
    ok:state==='COMPLETED'&&!!output?.receipt,
    state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:username+'/'+slug+'/'+version,
    metadata:{
      title:k?.title||null,
      machine_shape:k?.machineShape||k?.machine_shape||null,
      last_run_time:k?.lastRunTime||k?.last_run_time||null
    },
    output
  };
}

async function ltxKaggle2bLoadProbe(){
  const preflight=await kaggleLtxIdentity();
  const token='fixed';
  const slug='nd-ltx2b-load-probe-fixed';
  const marker='ND_LTX2B_LOAD_JSON=';
  const commit='2345ae148f82740f66e82c41292dbbdd592e713d';
  const script=[
    "from pathlib import Path",
    "import json,os,platform,shutil,subprocess,sys,urllib.request",
    "ROOT=Path('/kaggle/working/Wan2GP'); CK=ROOT/'ckpts'; T5=CK/'T5_xxl_1.1'",
    "COMMIT='"+commit+"'",
    "def run(cmd,timeout):",
    "    env={**os.environ,'PIP_NO_CACHE_DIR':'1','HF_HUB_DISABLE_XET':'1','HF_HOME':'/kaggle/working/hf-cache'}",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,env=env)",
    "    if p.returncode!=0:",
    "        print('ND_LTX2B_CMD_FAIL '+str(cmd)+'\\n'+p.stdout[-12000:]); raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "run(['git','clone','--filter=blob:none','https://github.com/deepbeepmeep/Wan2GP.git',str(ROOT)],240)",
    "run(['git','-C',str(ROOT),'checkout',COMMIT],90)",
    "run([sys.executable,'-m','pip','install','--no-cache-dir','-q','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],1200)",
    "from huggingface_hub import hf_hub_download",
    "CK.mkdir(parents=True,exist_ok=True); T5.mkdir(parents=True,exist_ok=True)",
    "model=hf_hub_download('Lightricks/LTX-Video','ltxv-2b-0.9.8-distilled-fp8.safetensors',local_dir=str(CK))",
    "te=hf_hub_download('DeepBeepMeep/LTX_Video','T5_xxl_1.1/T5_xxl_1.1_enc_quanto_bf16_int8.safetensors',local_dir=str(CK))",
    "for f in ['T5_xxl_1.1/added_tokens.json','T5_xxl_1.1/special_tokens_map.json','T5_xxl_1.1/spiece.model','T5_xxl_1.1/tokenizer_config.json','ltxv_0.9.7_VAE.safetensors','ltxv_0.9.7_spatial_upscaler.safetensors','ltxv_scheduler.json']:",
    "    hf_hub_download('DeepBeepMeep/LTX_Video',f,local_dir=str(CK))",
    "cfg=Path('/kaggle/working/ltxv-2b-0.9.8-distilled-fp8.yaml')",
    "cfg.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/Lightricks/LTX-Video/4b2d053057623ddd4d0a1d3e9cd28890e9ef487f/configs/ltxv-2b-0.9.8-distilled-fp8.yaml',timeout=60).read())",
    "sys.path.insert(0,str(ROOT)); os.chdir(ROOT)",
    "import torch",
    "from shared.utils import files_locator as fl",
    "fl.set_checkpoints_paths([str(CK)])",
    "from models.ltx_video.ltxv import LTXV",
    "print('ND_LTX2B_STAGE=instantiate')",
    "obj=LTXV(model_filepath=str(model),text_encoder_filepath=str(te),model_type='ltxv_2B',base_model_type='ltxv_2B',model_def={'LTXV_config':str(cfg),'text_encoder_folder':'T5_xxl_1.1'},dtype=torch.bfloat16,VAE_dtype=torch.bfloat16)",
    "u=shutil.disk_usage('/kaggle/working')",
    "sizes={}",
    "for p in [Path(model),Path(te),CK/'ltxv_0.9.7_VAE.safetensors',CK/'ltxv_0.9.7_spatial_upscaler.safetensors']:",
    "    sizes[p.name]=p.stat().st_size",
    "out={'ok':True,'python':platform.python_version(),'model_class':type(obj.model).__name__,'vae_class':type(obj.vae).__name__,'pipeline_class':type(obj.pipeline).__name__,'files':sizes,'working_free_bytes':int(u.free),'working_total_bytes':int(u.total)}",
    "print('"+marker+"'+json.dumps(out,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:preflight.username+'/'+slug,newTitle:'ND LTX2B Load Probe '+token,text:script,
    language:'python',kernelType:'script',datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],modelDataSources:[],
    isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:true,sessionTimeoutSeconds:2400
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version||save?.error) throw new Error('LTX2B load probe submit failed '+JSON.stringify({error:save?.error||null}));
  return {
    ok:true,
    state:'SUBMITTED',
    request_id:'ltx2b-load-v'+version,
    provider_ref:preflight.username+'/'+slug+'/'+version
  };
}

async function ltxKaggle2bFixedStatus(args={}){
  const {username}=await kaggleLtxIdentity();
  const slug='nd-ltx2b-load-probe-fixed';
  const m=String(args.request_id||'').trim().match(/^ltx2b-load-v(\d+)$/i);
  if(!m) throw new Error('valid ltx2b-load-vN request_id required');
  const version=Number(m[1]);
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel:'v'+version});
  const state=kaggleState(st?.status);
  let output=null;
  if(['RUNNING','FAILED','CANCELLED','COMPLETED'].includes(state)){
    try{
      const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel:'v'+version,pageSize:100});
      output={
        receipt:extractKaggleMarker(out?.log||'','ND_LTX2B_LOAD_JSON='),
        files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],
        log_tail:String(out?.log||'').slice(-18000)
      };
    }catch(e){output={error:errorText(e)};}
  }
  return {
    ok:state==='COMPLETED'&&!!output?.receipt,
    request_id:'ltx2b-load-v'+version,
    state,provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:username+'/'+slug+'/'+version,
    output
  };
}

async function ltxKaggleAbandonQueued(args={}){
  const requestId=String(args.request_id||'').trim();
  let ref;
  if(/^kbatch-/i.test(requestId)) ref=kaggleLtxBatchRequestRef(requestId);
  else ref=kaggleLtxRequestRef(requestId);
  const status=/^kbatch-/i.test(requestId)
    ? await ltxKaggleBatchStatus({request_id:requestId})
    : await ltxKaggleStatus({request_id:requestId});
  if(status.state!=='QUEUED') throw new Error('abandon allowed only for QUEUED jobs');
  const found=await ltxKaggleFindSession({request_id:requestId});
  if(!Array.isArray(found.exact_matches)||found.exact_matches.length!==1) throw new Error('abandon requires exactly one matching kernel');
  const match=found.exact_matches[0];
  if(match.session_id!=null) throw new Error('abandon blocked because provider session already exists');
  const {username}=await kaggleLtxIdentity();
  const del=await kaggleRpc('kernels.KernelsApiService','DeleteKernel',{
    userName:username,
    kernelSlug:ref.kernel_slug
  });
  let remaining=null;
  try{remaining=await ltxKaggleFindSession({request_id:requestId});}catch{}
  return {
    ok:true,
    state:'ABANDONED_QUEUED',
    request_id:requestId,
    kernel_slug:ref.kernel_slug,
    delete_response:del||{},
    remaining_exact_matches:remaining?.exact_matches||[]
  };
}

async function ltxKaggleDiagnoseSessions(){
  const {username}=await kaggleLtxIdentity();
  const listed=await kaggleRpc('kernels.KernelsApiService','ListKernels',{user:username,pageSize:100});
  const kernels=Array.isArray(listed?.kernels)?listed.kernels:[];
  const targets=kernels.map(k=>({
    id:k?.id??null,
    ref:k?.ref||null,
    title:k?.title||null,
    author:k?.author||null,
    slug:String(k?.slug||k?.ref||'').replace(/^.*\//,''),
    is_private:k?.isPrivate??k?.is_private??null,
    current_version_number:Number(k?.currentVersionNumber??k?.current_version_number??0),
    machine_shape:k?.machineShape??k?.machine_shape??null,
    last_run_time:k?.lastRunTime??k?.last_run_time??null
  })).filter(k=>/^nd-ltx-/i.test(k.slug)).slice(0,100);
  const sessions=[];
  for(const k of targets){
    let version=k.current_version_number;
    let pulledMeta=null;
    try{
      const pulled=await kaggleRpc('kernels.KernelsApiService','GetKernel',{
        userName:username,
        kernelSlug:k.slug
      });
      pulledMeta=pulled?.metadata||null;
      version=Number(
        pulledMeta?.currentVersionNumber ??
        pulledMeta?.current_version_number ??
        version ??
        0
      );
    }catch(e){
      sessions.push({...k,kernel_slug:k.slug,state:'PULL_ERROR',pull_error:errorText(e)});
      continue;
    }
    if(!version){
      sessions.push({...k,kernel_slug:k.slug,state:'NO_VERSION',pulled_metadata:pulledMeta});
      continue;
    }
    try{
      const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
        userName:username,kernelSlug:k.slug,versionLabel:'v'+version
      });
      sessions.push({
        ...k,
        current_version_number:version,
        kernel_slug:k.slug,
        state:kaggleState(st?.status),
        provider_status:st?.status??null,
        failure_message:st?.failureMessage||st?.failure_message||null,
        pulled_machine_shape:pulledMeta?.machineShape??pulledMeta?.machine_shape??null
      });
    }catch(e){
      sessions.push({...k,current_version_number:version,kernel_slug:k.slug,state:'STATUS_ERROR',status_error:errorText(e)});
    }
  }
  return {
    ok:true,
    owner:username,
    kernel_count:kernels.length,
    ltx_kernel_count:targets.length,
    sessions,
    active_or_queued:sessions.filter(x=>['QUEUED','RUNNING'].includes(x.state))
  };
}

async function ltxKaggleRetireSlug(args={}){
  const slug=String(args.slug||'').trim();
  if(!/^nd-ltx-[a-z0-9-]+$/i.test(slug)) throw new Error('retire-slug restricted to nd-ltx-* transient kernels');
  const {username}=await kaggleLtxIdentity();
  const listed=await kaggleRpc('kernels.KernelsApiService','ListKernels',{user:username,pageSize:100});
  const kernels=Array.isArray(listed?.kernels)?listed.kernels:[];
  const exact=kernels.map(k=>({
    id:k?.id??null,
    ref:k?.ref||null,
    title:k?.title||null,
    author:k?.author||null,
    slug:String(k?.slug||k?.ref||'').replace(/^.*\//,''),
    is_private:k?.isPrivate??k?.is_private??null,
    current_version_number:Number(k?.currentVersionNumber??k?.current_version_number??0)
  })).filter(k=>k.slug.toLowerCase()===slug.toLowerCase());
  if(exact.length!==1) throw new Error('retire-slug blocked: exact match count='+exact.length);
  const hit=exact[0];
  const exactRef=String(hit.ref||'').toLowerCase()===username.toLowerCase()+'/'+slug.toLowerCase();
  const ownedByUser=!hit.author||String(hit.author).toLowerCase()===username.toLowerCase()||String(hit.author).toLowerCase()==='savva savchenko';
  const ndTitle=/^ND LTX\b/i.test(String(hit.title||''));
  if(!exactRef||!ownedByUser||!ndTitle) throw new Error('retire-slug blocked: ownership/title guard failed');
  const out=await kaggleRpc('kernels.KernelsApiService','DeleteKernel',{userName:username,kernelSlug:slug});
  const verify=await kaggleRpc('kernels.KernelsApiService','ListKernels',{user:username,pageSize:100});
  const remains=(Array.isArray(verify?.kernels)?verify.kernels:[]).filter(k=>{
    const s=String(k?.slug||k?.ref||'').replace(/^.*\//,'').toLowerCase();
    return s===slug.toLowerCase();
  });
  return {ok:remains.length===0,retired_kernel_slug:slug,provider_response:out,remaining_exact_matches:remains.length};
}

async function ltxKaggleInspectKernel(args={}){
  const requestId=String(args.request_id||'').trim();
  let ref;
  if(/^kbatch-/i.test(requestId)) ref=kaggleLtxBatchRequestRef(requestId);
  else ref=kaggleLtxRequestRef(requestId);
  const {username}=await kaggleLtxIdentity();
  const listed=await kaggleRpc('kernels.KernelsApiService','ListKernels',{
    user:username,
    search:ref.kernel_slug,
    pageSize:50
  });
  const kernels=Array.isArray(listed?.kernels)?listed.kernels:[];
  const simplified=kernels.map(k=>({
    id:k?.id??null,
    ref:k?.ref||null,
    title:k?.title||null,
    author:k?.author||null,
    slug:k?.slug||null,
    is_private:k?.isPrivate??k?.is_private??null,
    current_version_number:k?.currentVersionNumber??k?.current_version_number??null,
    machine_shape:k?.machineShape??k?.machine_shape??null,
    last_run_time:k?.lastRunTime??k?.last_run_time??null
  }));
  const targetSlug=ref.kernel_slug.toLowerCase();
  const exact=simplified.filter(k=>{
    const slug=String(k.slug||'').toLowerCase();
    const author=String(k.author||'').toLowerCase();
    const full=String(k.ref||'').toLowerCase();
    return (slug===targetSlug || full===username.toLowerCase()+'/'+targetSlug) &&
           (!author || author===username.toLowerCase());
  });
  return {
    ok:true,
    request_id:requestId,
    kernel_slug:ref.kernel_slug,
    version:ref.version,
    owner:username,
    exact_matches:exact,
    candidates:simplified.slice(0,50)
  };
}

async function ltxKaggleForceRetireBatch(args={}){
  const requestId=String(args.request_id||'').trim();
  if(!/^kbatch-/i.test(requestId)) throw new Error('force retire is restricted to isolated batch requests');
  const ref=kaggleLtxBatchRequestRef(requestId);
  const {username}=await kaggleLtxIdentity();
  if(!/^nd-ltx-batch-r[a-z0-9]+-[a-z0-9]+$/i.test(ref.kernel_slug)) throw new Error('force retire blocked: unexpected batch slug');
  const out=await kaggleRpc('kernels.KernelsApiService','DeleteKernel',{
    userName:username,
    kernelSlug:ref.kernel_slug
  });
  let statusReadback=null;
  try{
    statusReadback=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
      userName:username,kernelSlug:ref.kernel_slug,versionLabel:'v'+ref.version
    });
  }catch(e){
    statusReadback={error:errorText(e)};
  }
  let listReadback=null;
  try{
    listReadback=await kaggleRpc('kernels.KernelsApiService','ListKernels',{
      user:username,search:ref.kernel_slug,pageSize:50
    });
  }catch(e){
    listReadback={error:errorText(e)};
  }
  const remaining=(Array.isArray(listReadback?.kernels)?listReadback.kernels:[]).filter(k=>{
    const slug=String(k?.slug||'').toLowerCase();
    const full=String(k?.ref||'').toLowerCase();
    return slug===ref.kernel_slug.toLowerCase() || full===username.toLowerCase()+'/'+ref.kernel_slug.toLowerCase();
  });
  return {
    ok:remaining.length===0,
    request_id:requestId,
    retired_kernel_slug:ref.kernel_slug,
    provider_response:out,
    status_readback:statusReadback,
    remaining_exact_matches:remaining.length
  };
}

async function ltxKaggleRetireKernel(args={}){
  const requestId=String(args.request_id||'').trim();
  if(!/^kbatch-/i.test(requestId)) throw new Error('retire is restricted to isolated batch requests');
  const ref=kaggleLtxBatchRequestRef(requestId);
  const inspect=await ltxKaggleInspectKernel({request_id:requestId});
  if(inspect.exact_matches.length!==1) throw new Error('retire blocked: exact kernel match count='+inspect.exact_matches.length);
  const hit=inspect.exact_matches[0];
  if(hit.is_private!==true) throw new Error('retire blocked: kernel is not private');
  if(Number(hit.current_version_number||0)!==Number(ref.version)) throw new Error('retire blocked: current version mismatch');
  const out=await kaggleRpc('kernels.KernelsApiService','DeleteKernel',{
    userName:inspect.owner,
    kernelSlug:ref.kernel_slug
  });
  const verify=await kaggleRpc('kernels.KernelsApiService','ListKernels',{
    user:inspect.owner,
    search:ref.kernel_slug,
    pageSize:50
  });
  const remains=(Array.isArray(verify?.kernels)?verify.kernels:[]).filter(k=>{
    const slug=String(k?.slug||'').toLowerCase();
    const full=String(k?.ref||'').toLowerCase();
    return slug===ref.kernel_slug.toLowerCase() || full===inspect.owner.toLowerCase()+'/'+ref.kernel_slug.toLowerCase();
  });
  return {
    ok:remains.length===0,
    request_id:requestId,
    retired_kernel_slug:ref.kernel_slug,
    provider_response:out,
    remaining_exact_matches:remains.length
  };
}

async function ltxKaggleFindSession(args={}){
  const requestId=String(args.request_id||'').trim();
  let ref;
  if(/^kbatch-/i.test(requestId)) ref=kaggleLtxBatchRequestRef(requestId);
  else ref=kaggleLtxRequestRef(requestId);
  const {username}=await kaggleLtxIdentity();
  const query=ref.kernel_slug;
  const attempts=[
    {filters:{query,privacy:1,documentTypes:[5]},pageSize:50},
    {filters:{query,privacy:0,documentTypes:[5]},pageSize:50},
    {filters:{query},pageSize:50}
  ];
  let lastError=null, response=null;
  for(const body of attempts){
    try{
      response=await kaggleRpc('search.SearchApiService','ListEntities',body);
      if(response) break;
    }catch(e){lastError=errorText(e);}
  }
  if(!response) throw new Error('Kaggle search lookup failed: '+String(lastError||'unknown'));
  const docs=Array.isArray(response?.documents)?response.documents:[];
  const simplified=docs.map(d=>({
    id:d?.id??null,
    title:d?.title||null,
    slug:d?.slug||null,
    is_private:d?.isPrivate??d?.is_private??null,
    owner:d?.ownerUser?.userName||d?.owner_user?.user_name||d?.ownerUser?.username||null,
    session_id:d?.kernelDocument?.sessionId??d?.kernel_document?.session_id??null
  }));
  const exact=simplified.filter(d=>{
    const slug=String(d.slug||'').toLowerCase();
    const target=ref.kernel_slug.toLowerCase();
    return slug===target || slug===username.toLowerCase()+'/'+target || slug.endsWith('/'+target);
  });
  return {
    ok:true,
    request_id:requestId,
    kernel_slug:ref.kernel_slug,
    version:ref.version,
    documents:simplified.slice(0,50),
    exact_matches:exact
  };
}

async function ltxKaggleAcceleratorProbe(shape='NvidiaTeslaP100'){
  const preflight=await kaggleLtxPreflight();
  const token='r'+Date.now().toString(36)+'-'+Math.floor(Math.random()*1679616).toString(36).padStart(4,'0');
  const slug='nd-ltx-accel-probe-'+token;
  const marker='ND_LTX_ACCEL_PROBE_JSON=';
  const script=[
    'import json,torch,platform',
    'out={"python":platform.python_version(),"cuda_available":torch.cuda.is_available(),"gpu_count":torch.cuda.device_count(),"gpus":[]}',
    'for i in range(torch.cuda.device_count()):',
    '    p=torch.cuda.get_device_properties(i)',
    '    out["gpus"].append({"index":i,"name":torch.cuda.get_device_name(i),"total_memory_bytes":int(p.total_memory),"major":int(p.major),"minor":int(p.minor)})',
    'print("'+marker+'"+json.dumps(out,separators=(",",":"),sort_keys=True))'
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:preflight.username+'/'+slug,
    newTitle:'ND LTX Accel Probe '+token,
    text:script,language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],modelDataSources:[],
    isPrivate:true,enableTpu:false,enableInternet:false,machineShape:shape,sessionTimeoutSeconds:600
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version||save?.error) throw new Error('accelerator probe submit failed '+JSON.stringify({error:save?.error||null}));
  const deadline=Date.now()+12*60*1000;
  let st=null;
  while(Date.now()<deadline){
    st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:preflight.username,kernelSlug:slug,versionLabel:'v'+version});
    if(['COMPLETED','FAILED','CANCELLED'].includes(kaggleState(st?.status))) break;
    await new Promise(r=>setTimeout(r,5000));
  }
  const state=kaggleState(st?.status);
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:preflight.username,kernelSlug:slug,versionLabel:'v'+version,pageSize:50});
  return {
    ok:state==='COMPLETED',
    state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:preflight.username+'/'+slug+'/'+version,
    machine_shape_requested:shape,
    receipt:extractKaggleMarker(out?.log||'',marker),
    diagnostics:{
      files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],
      log_tail:String(out?.log||'').slice(-8000)
    },
    gpu_quota:preflight.gpu
  };
}

async function ltxKaggleInputProbe(args={}){
  const start=resolveLtxInputRef(args.start_image_url);
  const end=resolveLtxInputRef(args.end_image_url);
  const {username}=await kaggleLtxIdentity();
  const slug='nd-ltx-input-probe';
  const fullSlug=username+'/'+slug;
  const payload=Buffer.from(JSON.stringify({start,end}),'utf8').toString('base64');
  const script=[
    'import base64,hashlib,json,urllib.request',
    'cfg=json.loads(base64.b64decode("'+payload+'").decode("utf-8"))',
    'out={}',
    'for key in ["start","end"]:',
    '    req=urllib.request.Request(cfg[key],headers={"User-Agent":"nd-kaggle-ltx-input-probe/1.0"})',
    '    with urllib.request.urlopen(req,timeout=120) as r:',
    '        data=r.read()',
    '        out[key]={"status":getattr(r,"status",200),"content_type":r.headers.get("Content-Type"),"size_bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}',
    'print("ND_LTX_INPUT_PROBE_JSON="+json.dumps(out,separators=(",",":"),sort_keys=True))'
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:'ND LTX Input Probe',text:script,
    language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],modelDataSources:[],
    isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:true,sessionTimeoutSeconds:900
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version||save?.error) throw new Error('Kaggle input probe submit failed '+JSON.stringify({error:save?.error||null}));
  const versionLabel='v'+version;
  let st=null;
  const deadline=Date.now()+12*60*1000;
  while(Date.now()<deadline){
    st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    const state=kaggleState(st?.status);
    if(['COMPLETED','FAILED','CANCELLED'].includes(state)) break;
    await new Promise(r=>setTimeout(r,5000));
  }
  const state=kaggleState(st?.status);
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
  const receipt=extractKaggleMarker(out?.log||'','ND_LTX_INPUT_PROBE_JSON=');
  return {
    ok:state==='COMPLETED'&&!!receipt,
    state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:fullSlug+'/'+version,
    receipt,
    diagnostics:{
      files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],
      log_tail:String(out?.log||'').slice(-8000)
    }
  };
}
async function ltxKaggleAutoFinalize(requestId){
  let id=String(requestId||'').trim();
  for(let cycle=0;cycle<3;cycle++){
    for(let i=0;i<280;i++){
      const st=await ltxKaggleStatus({request_id:id});
      if(st.state==='COMPLETED'){
        const result=await ltxKaggleResult({request_id:id});
        console.log(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:id,state:'READY',drive_video:result?.drive_video||null}));
        return result;
      }
      if(st.state==='FAILED'||st.state==='CANCELLED'){
        const files=st?.diagnostics?.files||[];
        const logTail=String(st?.diagnostics?.log_tail||'').trim();
        const emptyLog=logTail===''||logTail==='[]'||logTail==='{}'||logTail==='null';
        const ref=kaggleLtxRequestRef(id);
        if(st.state==='CANCELLED' && files.length===0 && emptyLog && !ref.legacy && ref.version<3){
          await new Promise(r=>setTimeout(r,45000));
          const retry=await ltxKaggleRetry({request_id:id});
          console.warn(JSON.stringify({event:'ND_LTX_KAGGLE_SCHEDULER_RETRY',previous_request_id:id,request_id:retry.request_id,retry_number:retry.retry_number}));
          id=retry.request_id;
          break;
        }
        console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:id,state:st.state,failure_message:st.failure_message||null,diagnostics:st.diagnostics||null}));
        return st;
      }
      await new Promise(r=>setTimeout(r,15000));
    }
    const ref=kaggleLtxRequestRef(id);
    if(ref.version>=3) break;
  }
  console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:id,state:'TIMEOUT'}));
  return {ok:false,request_id:id,state:'TIMEOUT'};
}

async function ltxGenerateKeyframes(args={}){
  const compat=String(args.space_id||'').trim();
  if(compat==='probe-inputs') return ltxKaggleInputProbe(args);
  if(compat==='probe-p100') return ltxKaggleAcceleratorProbe('NvidiaTeslaP100');
  const findSession=compat.match(/^find-session:(k(?:ltx|batch)-[a-z0-9-]+)$/i);
  if(findSession) return ltxKaggleFindSession({request_id:findSession[1]});
  const inspectKernel=compat.match(/^inspect-kernel:(k(?:ltx|batch)-[a-z0-9-]+)$/i);
  if(inspectKernel) return ltxKaggleInspectKernel({request_id:inspectKernel[1]});
  if(compat==='diagnose-sessions') return ltxKaggleDiagnoseSessions();
  const retireSlug=compat.match(/^retire-slug:(nd-ltx-[a-z0-9-]+)$/i);
  if(retireSlug) return ltxKaggleRetireSlug({slug:retireSlug[1]});
  const retireKernel=compat.match(/^retire-kernel:(kbatch-[a-z0-9-]+)$/i);
  if(retireKernel) return ltxKaggleRetireKernel({request_id:retireKernel[1]});
  const forceRetireKernel=compat.match(/^force-retire-kernel:(kbatch-[a-z0-9-]+)$/i);
  if(forceRetireKernel) return ltxKaggleForceRetireBatch({request_id:forceRetireKernel[1]});
  const abandonQueued=compat.match(/^abandon:(k(?:ltx|batch)-[a-z0-9-]+)$/i);
  if(abandonQueued) return ltxKaggleAbandonQueued({request_id:abandonQueued[1]});
  if(compat==='inspect-cache') return ltxKaggleCacheInventory();
  if(compat==='probe-2b-load') return ltxKaggle2bLoadProbe();
  const load2bStatus=compat.match(/^probe-2b-status:(ltx2b-load-v\d+)$/i);
  if(load2bStatus) return ltxKaggle2bFixedStatus({request_id:load2bStatus[1]});
  if(compat==='probe-2b-latest') return ltxKaggle2bLatestProbe();
  const batchSubmit=compat.match(/^batch:([A-Za-z0-9_-]+)$/);
  if(batchSubmit) return ltxKaggleBatchSubmit(decodeBatchSpec(batchSubmit[1]));
  const batchP100=compat.match(/^batch-p100:([A-Za-z0-9_-]+)$/);
  if(batchP100){
    const spec=decodeBatchSpec(batchP100[1]);
    return ltxKaggleBatchSubmit({...spec,adaptive:true,machine_shape:'NvidiaTeslaP100'});
  }
  const batchStatus=compat.match(/^batch-status:(kbatch-[a-z0-9-]+)$/i);
  if(batchStatus) return ltxKaggleBatchStatus({request_id:batchStatus[1]});
  const batchResult=compat.match(/^batch-result:(kbatch-[a-z0-9-]+)$/i);
  if(batchResult) return ltxKaggleBatchResult({request_id:batchResult[1]});
  const retryMatch=compat.match(/^retry:(kltx-[a-z0-9-]+)$/i);
  if(retryMatch) return ltxKaggleRetry({request_id:retryMatch[1]});
  if(compat==='build-2b-cache') return ltxKaggleBuild2bCache();
  if(compat==='build-2b-cache-status') return ltxKaggle2bCacheStatus();
  const statusMatch=compat.match(/^status:(kltx-[a-z0-9-]+)$/i);
  if(statusMatch) return ltxKaggleStatus({request_id:statusMatch[1]});
  const resultMatch=compat.match(/^result:(kltx-[a-z0-9-]+)$/i);
  if(resultMatch) return ltxKaggleResult({request_id:resultMatch[1]});
  return ltxKaggleSubmit(args);
}


export async function ltxKeyframeSelftest(){
  const started=Date.now();
  try{
    const preflight=await kaggleLtxPreflight();
    return {
      ok:true,
      elapsed_ms:Date.now()-started,
      route:'kaggle_ltx13b_mounted_cache_f2l',
      live_field_qualification:'PASS_2026-09-26',
      provider:'Kaggle',
      dataset_source:KAGGLE_LTX_DATASET,
      gpu_quota:preflight.gpu,
      note:'Readiness selftest does not start a GPU generation.'
    };
  }catch(e){
    return {ok:false,elapsed_ms:Date.now()-started,route:'kaggle_ltx13b_mounted_cache_f2l',error:errorText(e)};
  }
}

async function rawCall(args={}){
  const spaceId=String(args.space_id||DEFAULT_SPACE);
  const endpoint=String(args.api_name||'').trim();
  if(!endpoint) throw new Error('api_name required');
  const app=await Client.connect(spaceId,connectOptions());
  let payload=args.payload;
  if(payload===undefined && typeof args.payload_json==='string') payload=JSON.parse(args.payload_json||'{}');
  if(payload===undefined) payload={};
  payload=transformFiles(payload);
  const result=await app.predict(endpoint,payload);
  return {space_id:spaceId,api_name:endpoint,...normalizeResult(result)};
}

const TOOLS=[
  {
    name:'storyboard_render_submit',
    description:'Submit a free storyboard-to-MP4 render to the public GitHub Actions FFmpeg renderer. Uses deterministic camera motion and transitions; no generative-video credits or browser are required.',
    inputSchema:{
      type:'object',
      properties:{
        frames:{
          type:'array',minItems:2,maxItems:40,
          items:{
            type:'object',
            properties:{
              url:{type:'string'},
              duration:{type:'number',minimum:0.2,maximum:20},
              motion:{type:'string',enum:['static','slow_push_in','slow_pull_out','pan_left','pan_right']},
              transition:{type:'string',enum:['fade','cut','wipeleft','wiperight','fadeblack','slideleft','slideright']}
            },
            required:['url'],
            additionalProperties:false
          }
        },
        width:{type:'integer',default:640,minimum:256,maximum:1920},
        height:{type:'integer',default:360,minimum:256,maximum:1920},
        fps:{type:'integer',default:24,minimum:12,maximum:60},
        default_duration:{type:'number',default:1.4,minimum:0.2,maximum:20},
        transition_duration:{type:'number',default:0.3,minimum:0.05,maximum:1.0}
      },
      required:['frames'],
      additionalProperties:false
    }
  },
  {
    name:'storyboard_render_status',
    description:'Read GitHub Actions status and artifact metadata for a storyboard render request.',
    inputSchema:{
      type:'object',
      properties:{request_id:{type:'string'}},
      required:['request_id'],
      additionalProperties:false
    }
  },
  {
    name:'storyboard_render_result',
    description:'Return the completed storyboard render receipt plus a protected direct MP4 URL served through the ND storyboard result proxy.',
    inputSchema:{
      type:'object',
      properties:{request_id:{type:'string'}},
      required:['request_id'],
      additionalProperties:false
    }
  },
  {
    name:'ltx_generate_quota_independent',
    description:'Submit an open-weight LTX 2B distilled FP8 generation to a quota-independent Hugging Face GPU Job. This route has no daily generation quota but uses paid GPU compute; it is hard-disabled until the owner explicitly authorizes paid compute.',
    inputSchema:{
      type:'object',
      properties:{
        prompt:{type:'string'},
        conditioning_media_urls:{type:'array',items:{type:'string'}},
        conditioning_start_frames:{type:'array',items:{type:'integer'}},
        conditioning_strengths:{type:'array',items:{type:'number'}},
        width:{type:'integer',default:512,minimum:256,maximum:1280},
        height:{type:'integer',default:768,minimum:256,maximum:1280},
        num_frames:{type:'integer',default:49,minimum:9,maximum:121},
        frame_rate:{type:'integer',default:24,minimum:1,maximum:60},
        seed:{type:'integer',default:42},
        paid_compute_authorized:{type:'boolean',default:false}
      },
      required:['prompt','paid_compute_authorized'],
      additionalProperties:false
    }
  },
  {
    name:'ltx_quota_independent_status',
    description:'Read status/comments for a quota-independent LTX Hugging Face GPU Job submission.',
    inputSchema:{type:'object',properties:{issue_number:{type:'integer',minimum:1}},required:['issue_number'],additionalProperties:false}
  },
  {
    name:'ltx_generate_keyframes',
    description:'Submit a FREE_ONLY first-to-last-keyframe LTX 13B generation to Kaggle T4x2 using the mounted model cache. Returns a request_id; use ltx_keyframe_status and ltx_keyframe_result. Completed results are copied to Google Drive.',
    inputSchema:{
      type:'object',
      properties:{
        start_image_url:{type:'string',description:'http(s) URL or drive:<Google Drive file id>'},
        end_image_url:{type:'string',description:'http(s) URL or drive:<Google Drive file id>'},
        prompt:{type:'string'},
        duration_seconds:{type:'number',default:2,minimum:1,maximum:6},
        width:{type:'integer',default:512},
        height:{type:'integer',default:512},
        seed:{type:'integer',default:42},
        randomize_seed:{type:'boolean',default:false},
        enhance_prompt:{type:'boolean',default:false},
        space_id:{type:'string',default:LTX_KEYFRAME_PRIMARY_SPACE}
      },
      required:['start_image_url','end_image_url'],
      additionalProperties:false
    }
  },
  {
    name:'ltx_keyframe_status',
    description:'Read provider status for a Kaggle LTX first/last-frame generation request.',
    inputSchema:{type:'object',properties:{request_id:{type:'string'}},required:['request_id'],additionalProperties:false}
  },
  {
    name:'ltx_keyframe_result',
    description:'Return the completed Kaggle LTX first/last-frame receipt and Google Drive video link. The output is copied to Drive idempotently on first successful result read.',
    inputSchema:{type:'object',properties:{request_id:{type:'string'}},required:['request_id'],additionalProperties:false}
  },
  {
    name:'ltx_list_routes',
    description:'List configured free LTX Hugging Face Space routes. This is configuration exposure only; live operation must be qualified separately.',
    inputSchema:{type:'object',properties:{},additionalProperties:false}
  },
  {
    name:'ltx_get_capabilities',
    description:'Return the complete Gradio API schema for the configured primary LTX Space or an explicitly selected LTX reserve Space.',
    inputSchema:{type:'object',properties:{space_id:{type:'string',default:DEFAULT_LTX_SPACE}},additionalProperties:false}
  },
  {
    name:'ltx_call_space_raw',
    description:'Direct full Gradio call to the primary or selected reserve LTX Space. Pass arbitrary endpoint payload; prefix file URL/path strings with @file: for Gradio file handling.',
    inputSchema:{
      type:'object',
      properties:{space_id:{type:'string',default:DEFAULT_LTX_SPACE},api_name:{type:'string'},payload:{},payload_json:{type:'string'}},
      required:['api_name'],additionalProperties:false
    }
  },
  {
    name:'wan_get_capabilities',
    description:'Return the complete Gradio API schema for any public Hugging Face Space. No capability allowlist is applied.',
    inputSchema:{type:'object',properties:{space_id:{type:'string',default:DEFAULT_SPACE}},additionalProperties:false}
  },
  {
    name:'wan_generate_video',
    description:'Generate a real image-to-video clip with Wan 2.2 I2V using a start frame and optional end frame. Full generation controls are exposed; no trial/read-only mode is used.',
    inputSchema:{
      type:'object',
      properties:{
        input_image_url:{type:'string'},
        last_image_url:{type:'string'},
        prompt:{type:'string'},
        negative_prompt:{type:'string'},
        duration_seconds:{type:'number',default:2.5},
        steps:{type:'integer',default:4},
        guidance_scale:{type:'number',default:1},
        guidance_scale_2:{type:'number',default:1},
        seed:{type:'integer',default:42},
        randomize_seed:{type:'boolean',default:false},
        quality:{type:'integer',default:5},
        scheduler:{type:'string',default:'UniPCMultistep'},
        flow_shift:{type:'number',default:3},
        frame_multiplier:{type:'integer',default:16},
        safe_mode:{type:'boolean',default:false},
        video_component:{type:'boolean',default:true},
        space_id:{type:'string',default:DEFAULT_SPACE},
        api_name:{type:'string',default:'/generate_video'}
      },
      required:['input_image_url','prompt'],
      additionalProperties:false
    }
  },
  {
    name:'wan_call_space_raw',
    description:'Direct full Gradio call to any public Hugging Face Space endpoint. Pass arbitrary payload. Prefix any file URL/path string with @file: to have it uploaded/handled as a Gradio file input.',
    inputSchema:{
      type:'object',
      properties:{
        space_id:{type:'string',default:DEFAULT_SPACE},
        api_name:{type:'string'},
        payload:{},
        payload_json:{type:'string'}
      },
      required:['api_name'],
      additionalProperties:false
    }
  }
];

const STORYBOARD_TOOLS=TOOLS.filter(x=>x.name.startsWith('storyboard_'));

function toolResult(value){
  return {content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value,isError:false};
}


export function createStoryboardMcpHandler(){
  return async function handleStoryboardMcp(req,res){
    if(req.method==='GET'){
      res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});
      res.write(': nd-storyboard-renderer-mcp\n\n');
      return res.end();
    }
    if(req.method!=='POST') return json(res,405,{ok:false,error:'method_not_allowed'});
    const chunks=[]; for await(const ch of req) chunks.push(ch);
    let msg={};
    try{msg=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}
    catch{return json(res,400,{jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}});}
    const id=msg.id??null, method=String(msg.method||'');
    try{
      if(method==='initialize'){
        return json(res,200,{jsonrpc:'2.0',id,result:{
          protocolVersion:String(msg?.params?.protocolVersion||'2025-06-18'),
          capabilities:{tools:{}},
          serverInfo:{name:'ND Storyboard Renderer MCP',version:'1.0.0'}
        }});
      }
      if(method==='ping') return json(res,200,{jsonrpc:'2.0',id,result:{}});
      if(method.startsWith('notifications/')){res.writeHead(202,{'cache-control':'no-store'});return res.end();}
      if(method==='tools/list') return json(res,200,{jsonrpc:'2.0',id,result:{tools:STORYBOARD_TOOLS}});
      if(method==='tools/call'){
        const name=String(msg?.params?.name||'');
        const args=(msg?.params?.arguments&&typeof msg.params.arguments==='object')?msg.params.arguments:{};
        let result;
        if(name==='storyboard_render_submit') result=await storyboardRenderSubmit(args);
        else if(name==='storyboard_render_status') result=await storyboardRenderStatus(args);
        else if(name==='storyboard_render_result') result=await storyboardRenderResult(args);
        else return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Unknown tool'}});
        return json(res,200,{jsonrpc:'2.0',id,result:toolResult(result)});
      }
      return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }catch(e){
      return json(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:errorText(e)}],isError:true}});
    }
  };
}

export async function storyboardHealth(){
  return {
    ok:true,
    route:'public_github_actions_ffmpeg_storyboard',
    repository:STORYBOARD_REPO,
    workflow:'.github/workflows/nd-storyboard-render.yml',
    cost_policy:'FREE_ONLY',
    daily_generation_quota:'NONE',
    renderer:'ffmpeg-storyboard-v1',
    rife_state:'CPU_COMPONENT_QUALIFIED / Practical-RIFE-4.25.lite / 3.228s_pair_512x256',
    tools:STORYBOARD_TOOLS.map(x=>x.name)
  };
}

export function createWanMcpHandler(){
  return async function handleWanMcp(req,res){
    if(req.method==='GET'){
      res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});
      res.write(': nd-wan-video-mcp full-access\n\n');
      return res.end();
    }
    if(req.method!=='POST') return json(res,405,{ok:false,error:'method_not_allowed'});
    const chunks=[]; for await(const ch of req) chunks.push(ch);
    let msg={};
    try{msg=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}
    catch{return json(res,400,{jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}});}
    const id=msg.id??null;
    const method=String(msg.method||'');
    try{
      if(method==='initialize'){
        return json(res,200,{
          jsonrpc:'2.0',id,
          result:{
            protocolVersion:String(msg?.params?.protocolVersion||'2025-06-18'),
            capabilities:{tools:{}},
            serverInfo:{name:'ND Wan Video MCP',version:'1.0.0'}
          }
        });
      }
      if(method==='ping') return json(res,200,{jsonrpc:'2.0',id,result:{}});
      if(method.startsWith('notifications/')){res.writeHead(202,{'cache-control':'no-store'});return res.end();}
      if(method==='tools/list') return json(res,200,{jsonrpc:'2.0',id,result:{tools:TOOLS}});
      if(method==='tools/call'){
        const name=String(msg?.params?.name||'');
        const args=(msg?.params?.arguments&&typeof msg.params.arguments==='object')?msg.params.arguments:{};
        let result;
        if(name==='storyboard_render_submit') result=await storyboardRenderSubmit(args);
        else if(name==='storyboard_render_status') result=await storyboardRenderStatus(args);
        else if(name==='storyboard_render_result') result=await storyboardRenderResult(args);
        else if(name==='ltx_generate_quota_independent') result=await ltxQuotaIndependentSubmit(args);
        else if(name==='ltx_quota_independent_status') result=await ltxQuotaIndependentStatus(args);
        else if(name==='ltx_generate_keyframes') result=await ltxGenerateKeyframes(args);
        else if(name==='ltx_keyframe_status') result=await ltxKaggleStatus(args);
        else if(name==='ltx_keyframe_result') result=await ltxKaggleResult(args);
        else if(name==='ltx_list_routes') result={
          primary:DEFAULT_LTX_SPACE,
          i2v:{primary:LTX_I2V_PRIMARY_SPACE,reserves:DEFAULT_LTX_RESERVES},
          keyframe:{primary:'kaggle_ltx13b_mounted_cache_f2l',provider:'Kaggle',dataset_source:KAGGLE_LTX_DATASET,reserves:LTX_KEYFRAME_RESERVES,state:'LIVE_QUALIFIED_FREE_ONLY'},
          all:configuredLtxSpaces(),
          state:'CONFIGURED / VERIFY_AT_USE',
          quota_independent:{
            route:'HF Jobs / L4 / LTX 2B distilled FP8',
            state:LTX_HFJOBS_ENABLED?'ENABLED_REQUIRES_PER_CALL_PAID_AUTH':'STAGED_DISABLED_REQUIRES_OWNER_AUTH',
            daily_generation_quota:'NONE',
            max_job_timeout_minutes:30,
            estimated_max_cost_usd:LTX_HFJOBS_MAX_COST_USD
          }
        };
        else if(name==='ltx_get_capabilities') result=await ltxCapabilities(args);
        else if(name==='ltx_call_space_raw') result=await ltxRawCall(args);
        else if(name==='wan_get_capabilities') result=await capabilities(String(args.space_id||DEFAULT_SPACE));
        else if(name==='wan_generate_video') result=await generateVideo(args);
        else if(name==='wan_call_space_raw') result=await rawCall(args);
        else return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Unknown tool'}});
        return json(res,200,{jsonrpc:'2.0',id,result:toolResult(result)});
      }
      return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }catch(e){
      return json(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:errorText(e)}],isError:true}});
    }
  };
}

export async function wanHealth(){
  return {ok:true,mode:'full',default_space:DEFAULT_SPACE,hf_token_configured:!!HF_TOKEN,tools:TOOLS.map(x=>x.name)};
}

export async function ltxHealth({probe=false,spaceId}={}){
  const selected=String(spaceId||DEFAULT_LTX_SPACE).trim();
  const base={ok:true,mode:'full',primary_space:DEFAULT_LTX_SPACE,i2v_primary_space:LTX_I2V_PRIMARY_SPACE,keyframe_primary_space:'kaggle_ltx13b_mounted_cache_f2l',keyframe_provider:'Kaggle',keyframe_dataset_source:KAGGLE_LTX_DATASET,reserve_spaces:DEFAULT_LTX_RESERVES,keyframe_reserve_spaces:LTX_KEYFRAME_RESERVES,selected_space:selected,hf_token_configured:!!HF_TOKEN,quota_independent:{enabled:LTX_HFJOBS_ENABLED,route:'HF Jobs / L4 / LTX 2B distilled FP8',daily_generation_quota:'NONE',estimated_max_cost_usd:LTX_HFJOBS_MAX_COST_USD},tools:TOOLS.filter(x=>x.name.startsWith('ltx_')).map(x=>x.name)};
  if(!probe) return {...base,upstream:'VERIFY_AT_USE'};
  try{
    const cap=await capabilities(selected);
    const named=cap?.api?.named_endpoints && typeof cap.api.named_endpoints==='object' ? Object.keys(cap.api.named_endpoints) : [];
    const unnamed=cap?.api?.unnamed_endpoints && typeof cap.api.unnamed_endpoints==='object' ? Object.keys(cap.api.unnamed_endpoints) : [];
    return {...base,upstream:'EXPOSED',api_names:[...named,...unnamed],api:cap.api};
  }catch(e){
    return {...base,ok:false,upstream:'DEGRADED_OR_BLOCKED',error:errorText(e)};
  }
}