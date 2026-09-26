import { Client, handle_file } from '@gradio/client';
import AdmZip from 'adm-zip';
import { readFile } from 'node:fs/promises';

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
const LTX_INPUT_TOKEN = String(process.env.ND_LTX_MCP_PATH_TOKEN || '').trim();
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
  if(!res.ok) throw new Error('Kaggle HTTP '+res.status+': '+String(data?.message||data?.error||txt).slice(0,1000));
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

function kaggleLtxRequestVersion(requestId){
  const m=String(requestId||'').trim().match(/^kltx-v(\d+)$/i);
  if(!m) throw new Error('valid request_id required, e.g. kltx-v3');
  return Number(m[1]);
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
  if(!LTX_INPUT_TOKEN) throw new Error('ND_LTX_MCP_PATH_TOKEN is not configured');
  const local='http://127.0.0.1:'+OUTER_PORT+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  const res=await fetch(local);
  if(!res.ok) throw new Error(label+' Drive input read failed HTTP '+res.status);
  const ct=String(res.headers.get('content-type')||'');
  if(!ct.startsWith('image/')) throw new Error(label+' Drive input is not an image');
  const buf=Buffer.from(await res.arrayBuffer());
  if(!buf.length||buf.length>20*1024*1024) throw new Error(label+' Drive input is empty or too large');
  return {url:null,base64:buf.toString('base64'),content_type:ct,size_bytes:buf.length};
}

async function ltxKaggleSubmit(args={}){
  const [startInput,endInput]=await Promise.all([
    prepareLtxKernelInput(args.start_image_url,'start'),
    prepareLtxKernelInput(args.end_image_url,'end')
  ]);
  const preflight=await kaggleLtxPreflight();
  const worker=await readFile(new URL('./kaggle_ltx_worker.py',import.meta.url),'utf8');
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
  const workerB64=Buffer.from(worker,'utf8').toString('base64');
  const script=[
    'import base64,sys',
    'from pathlib import Path',
    "request_path=Path('/kaggle/working/nd-ltx-request.json')",
    "request_path.write_bytes(base64.b64decode('"+reqB64+"'))",
    "sys.argv=['kaggle_ltx_worker.py',str(request_path)]",
    "source=base64.b64decode('"+workerB64+"').decode('utf-8')",
    "exec(compile(source,'kaggle_ltx_worker.py','exec'),{'__name__':'__main__'})"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:preflight.username+'/'+KAGGLE_LTX_KERNEL,
    newTitle:'ND LTX First Last Production',
    text:script,
    language:'python',
    kernelType:'script',
    datasetDataSources:[KAGGLE_LTX_DATASET],
    kernelDataSources:[],
    competitionDataSources:[],
    categoryIds:[],
    modelDataSources:[],
    isPrivate:true,
    enableGpu:true,
    enableTpu:false,
    enableInternet:true,
    machineShape:'NvidiaTeslaT4',
    sessionTimeoutSeconds:3600
  });
  const invalid=save?.invalidDatasetSources||save?.invalid_dataset_sources||[];
  if(save?.error||invalid.length) throw new Error('Kaggle submit failed: '+JSON.stringify({error:save?.error||null,invalid_dataset_sources:invalid}));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('Kaggle submit returned no version');
  setTimeout(()=>ltxKaggleAutoFinalize(version).catch(e=>console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:'kltx-v'+version,state:'ERROR',error:errorText(e)}))),10000);
  return {
    ok:true,
    state:'SUBMITTED',
    request_id:'kltx-v'+version,
    provider_ref:preflight.username+'/'+KAGGLE_LTX_KERNEL+'/'+version,
    route:'kaggle_ltx13b_mounted_cache_f2l',
    cost_policy:'FREE_ONLY',
    gpu_quota:preflight.gpu,
    seed
  };
}

async function ltxKaggleStatus(args={}){
  const version=kaggleLtxRequestVersion(args.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
    userName:username,kernelSlug:KAGGLE_LTX_KERNEL,versionLabel:'v'+version
  });
  const state=kaggleState(st?.status);
  let diagnostics=null;
  if(['FAILED','CANCELLED','COMPLETED'].includes(state)){
    try{
      const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
        userName:username,kernelSlug:KAGGLE_LTX_KERNEL,versionLabel:'v'+version,pageSize:100
      });
      const files=Array.isArray(out?.files)?out.files.map(x=>({
        name:x?.fileName||x?.name||x?.path||null,
        size:x?.fileSize??x?.size??null
      })).filter(x=>x.name):[];
      diagnostics={
        files,
        log_tail:String(out?.log||'').slice(-12000)
      };
    }catch(e){
      diagnostics={error:errorText(e)};
    }
  }
  return {
    ok:true,
    request_id:'kltx-v'+version,
    state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    provider_ref:username+'/'+KAGGLE_LTX_KERNEL+'/'+version,
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
  const version=kaggleLtxRequestVersion(args.request_id);
  const {username}=await kaggleLtxIdentity();
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
    userName:username,kernelSlug:KAGGLE_LTX_KERNEL,versionLabel:'v'+version
  });
  const state=kaggleState(st?.status);
  if(state!=='COMPLETED') return {
    ok:false,request_id:'kltx-v'+version,state,
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null
  };
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:KAGGLE_LTX_KERNEL,versionLabel:'v'+version,pageSize:100
  });
  const files=Array.isArray(out?.files)?out.files:[];
  const byName=name=>files.find(x=>(x?.fileName||x?.name||x?.path)===name);
  const mp4=byName('result.mp4');
  const receiptFile=byName('result.json');
  if(!mp4?.url) throw new Error('result.mp4 missing from Kaggle output');
  const receipt=extractKaggleMarker(out?.log||'','ND_LTX_F2L_JSON=');
  const driveVideo=await driveImportKaggleOutput(
    mp4.url,
    'nd-ltx-'+('kltx-v'+version)+'.mp4',
    'video/mp4'
  );
  let driveReceipt=null;
  if(receiptFile?.url){
    driveReceipt=await driveImportKaggleOutput(
      receiptFile.url,
      'nd-ltx-'+('kltx-v'+version)+'.json',
      'application/json'
    );
  }
  const file=driveVideo?.file||{};
  return {
    ok:true,
    request_id:'kltx-v'+version,
    state:'READY',
    route:'kaggle_ltx13b_mounted_cache_f2l',
    provider_ref:username+'/'+KAGGLE_LTX_KERNEL+'/'+version,
    receipt,
    video_ref:file.webViewLink||null,
    drive_video:{
      id:file.id||null,
      name:file.name||null,
      size:Number(file.size||0),
      mime_type:file.mimeType||null,
      url:file.webViewLink||null,
      reused:driveVideo?.reused===true
    },
    drive_receipt:driveReceipt?.file?{
      id:driveReceipt.file.id||null,
      name:driveReceipt.file.name||null,
      url:driveReceipt.file.webViewLink||null,
      reused:driveReceipt?.reused===true
    }:null
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
async function ltxKaggleAutoFinalize(version){
  const requestId='kltx-v'+Number(version);
  for(let i=0;i<280;i++){
    const st=await ltxKaggleStatus({request_id:requestId});
    if(st.state==='COMPLETED'){
      const result=await ltxKaggleResult({request_id:requestId});
      console.log(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:requestId,state:'READY',drive_video:result?.drive_video||null}));
      return result;
    }
    if(st.state==='FAILED'||st.state==='CANCELLED'){
      console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:requestId,state:st.state,failure_message:st.failure_message||null}));
      return st;
    }
    await new Promise(r=>setTimeout(r,15000));
  }
  console.error(JSON.stringify({event:'ND_LTX_KAGGLE_AUTO_FINALIZE',request_id:requestId,state:'TIMEOUT'}));
  return {ok:false,request_id:requestId,state:'TIMEOUT'};
}

async function ltxGenerateKeyframes(args={}){
  const compat=String(args.space_id||'').trim();
  if(compat==='probe-inputs') return ltxKaggleInputProbe(args);
  const statusMatch=compat.match(/^status:(kltx-v\d+)$/i);
  if(statusMatch) return ltxKaggleStatus({request_id:statusMatch[1]});
  const resultMatch=compat.match(/^result:(kltx-v\d+)$/i);
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