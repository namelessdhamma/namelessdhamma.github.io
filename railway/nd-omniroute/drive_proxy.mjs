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
    const rawDetail=obj?.message??obj?.error??obj??text;
    let detail;
    try{detail=typeof rawDetail==='string'?rawDetail:JSON.stringify(rawDetail);}catch{detail=String(rawDetail);}
    const e=new Error('kaggle HTTP '+res.status+': '+String(detail).slice(0,1200));
    e.status=res.status;
    e.kaggle_body=obj;
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


function extractKaggleProbePayload(log){
  const marker='ND_GPU_PROBE_JSON=';
  const raw=String(log||'');
  const chunks=[raw];
  try{
    const parsed=JSON.parse(raw);
    const visit=v=>{
      if(v==null) return;
      if(typeof v==='string') chunks.push(v);
      else if(Array.isArray(v)) for(const x of v) visit(x);
      else if(typeof v==='object'){
        for(const key of ['data','message','text','log']) if(typeof v[key]==='string') chunks.push(v[key]);
      }
    };
    visit(parsed);
  }catch{}
  for(const chunk0 of chunks){
    const chunk=String(chunk0||'');
    const pos=chunk.indexOf(marker);
    if(pos<0) continue;
    let candidate=chunk.slice(pos+marker.length).trim();
    candidate=candidate.split(/\r?\n/,1)[0].trim();
    // Common persisted-log encodings may leave a trailing quote/comma/bracket.
    candidate=candidate.replace(/\\n.*$/s,'').replace(/["']?\s*[,}\]]*\s*$/,'').trim();
    const attempts=[candidate];
    if(candidate.startsWith('{\\"')) attempts.push(candidate.replace(/\\"/g,'"'));
    if(candidate.startsWith("{'")) attempts.push(candidate.replace(/'/g,'"'));
    for(const a of attempts){
      try{return JSON.parse(a);}catch{}
    }
    // Last-resort balanced-object extraction from the marker onward.
    const start=chunk.indexOf('{',pos+marker.length);
    if(start>=0){
      let depth=0, quote=null, esc=false;
      for(let i=start;i<chunk.length;i++){
        const ch=chunk[i];
        if(esc){esc=false;continue;}
        if(ch==='\\'){esc=true;continue;}
        if(quote){if(ch===quote)quote=null;continue;}
        if(ch==='"'||ch==="'"){quote=ch;continue;}
        if(ch==='{') depth++;
        else if(ch==='}'){
          depth--;
          if(depth===0){
            const objText=chunk.slice(start,i+1);
            for(const a of [objText,objText.replace(/\\"/g,'"'),objText.replace(/'/g,'"')]){
              try{return JSON.parse(a);}catch{}
            }
            break;
          }
        }
      }
    }
  }
  throw new Error('kaggle_gpu_probe_payload_unparseable');
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
  const payload=extractKaggleProbePayload(out?.log||'');
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


async function kaggleGpuProbeReadback(version){
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_probe_readback_auth_failed');
  const username=String(intro.username);
  const slug='nd-gpu-probe';
  const versionLabel='v'+Number(version);
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
    userName:username,kernelSlug:slug,versionLabel
  });
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:slug,versionLabel,pageSize:20
  });
  const payload=extractKaggleProbePayload(out?.log||'');
  const result={
    state:'PASS',
    username,
    ref:username+'/'+slug+'/'+Number(version),
    version:Number(version),
    provider_status:st?.status??null,
    failure_message:st?.failureMessage||st?.failure_message||null,
    gpu:payload
  };
  console.log(JSON.stringify({event:'ND_KAGGLE_GPU_PROBE_READBACK',...result}));
  return result;
}


function extractKaggleJsonMarker(log,marker,errorName='kaggle_marker_payload_unparseable'){
  const raw=String(log||'');
  const chunks=[raw];
  const visit=v=>{
    if(v==null) return;
    if(typeof v==='string'){chunks.push(v);return;}
    if(Array.isArray(v)){for(const x of v) visit(x);return;}
    if(typeof v==='object'){for(const x of Object.values(v)) visit(x);}
  };
  try{visit(JSON.parse(raw));}catch{}
  for(const chunk0 of chunks){
    const chunk=String(chunk0||'');
    const pos=chunk.indexOf(marker);
    if(pos<0) continue;
    const start=chunk.indexOf('{',pos+marker.length);
    if(start<0) continue;
    for(const normalized of [chunk,chunk.replace(/\\\"/g,'"'),chunk.replace(/\\n/g,'\n')]){
      const s=normalized.indexOf('{',normalized.indexOf(marker)+marker.length);
      if(s<0) continue;
      let depth=0, quote=null, esc=false;
      for(let i=s;i<normalized.length;i++){
        const ch=normalized[i];
        if(esc){esc=false;continue;}
        if(ch==='\\'){esc=true;continue;}
        if(quote){if(ch===quote) quote=null;continue;}
        if(ch==='"'||ch==="'"){quote=ch;continue;}
        if(ch==='{') depth++;
        else if(ch==='}'){
          depth--;
          if(depth===0){
            const objText=normalized.slice(s,i+1);
            for(const a of [objText,objText.replace(/\\\"/g,'"'),objText.replace(/'/g,'"')]){
              try{return JSON.parse(a);}catch{}
            }
            break;
          }
        }
      }
    }
  }
  throw new Error(errorName);
}

async function kaggleWanGPBootstrap(){
  const enabled=String(process.env.ND_KAGGLE_WANGP_BOOTSTRAP_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_wangp_bootstrap_auth_failed');
  const username=String(intro.username);
  const slug='nd-wangp-bootstrap';
  const fullSlug=username+'/'+slug;
  const script=[
    "from pathlib import Path",
    "import json, os, platform, subprocess, sys, time",
    "ROOT=Path('/kaggle/working/Wan2GP')",
    "OUT=Path('/kaggle/working/wangp-bootstrap-out')",
    "COMMIT='2345ae148f82740f66e82c41292dbbdd592e713d'",
    "def run(cmd,timeout):",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)",
    "    if p.returncode!=0:",
    "        print('ND_WANGP_COMMAND_FAIL '+str(cmd)+'\\n'+p.stdout[-6000:])",
    "        raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "if ROOT.exists():",
    "    run(['git','-C',str(ROOT),'fetch','--depth','1','origin',COMMIT],180)",
    "else:",
    "    run(['git','clone','--filter=blob:none','https://github.com/deepbeepmeep/Wan2GP.git',str(ROOT)],240)",
    "run(['git','-C',str(ROOT),'checkout',COMMIT],90)",
    "run([sys.executable,'-m','pip','install','-q','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],1200)",
    "sys.path.insert(0,str(ROOT))",
    "os.chdir(ROOT)",
    "from shared.api import init",
    "OUT.mkdir(parents=True,exist_ok=True)",
    "session=init(root=ROOT,output_dir=OUT,cli_args=['--profile','4','--attention','sdpa','--fp16','--perc-reserved-mem-max','0.2'],console_output=False)",
    "records=[]",
    "seen=set()",
    "for query in ['H3','Wan 2.2','Wan2.2']:",
    "    for m in session.list_model_defs(query=query,main_output='video',limit=250):",
    "        mt=str(m.get('model_type') or '')",
    "        if not mt or mt in seen: continue",
    "        seen.add(mt)",
    "        md=m.get('metadata') or {}",
    "        image=((md.get('media_inputs') or {}).get('image') or {})",
    "        caps=md.get('capabilities') or {}",
    "        sv=(md.get('setting_values') or {}).get('image_prompt_type')",
    "        records.append({'model_type':mt,'name':m.get('name'),'family':md.get('family'),'inputs':md.get('inputs'),'image':image,'capabilities':caps,'image_prompt_type':sv})",
    "dual=[r for r in records if bool((r.get('image') or {}).get('start')) and bool((r.get('image') or {}).get('end'))]",
    "out={'python':platform.python_version(),'wangp_commit':COMMIT,'model_count':len(records),'dual_endpoint_count':len(dual),'dual_endpoint_models':dual[:80]}",
    "print('ND_WANGP_BOOTSTRAP_JSON='+json.dumps(out,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,
    newTitle:'ND WanGP Bootstrap',
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
    enableInternet:true,
    modelDataSources:[],
    sessionTimeoutSeconds:1800,
    machineShape:'NvidiaTeslaT4'
  });
  if(save?.error) throw new Error('kaggle_wangp_bootstrap_save_error: '+String(save.error).slice(0,500));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_wangp_bootstrap_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null, failureMessage=null;
  const deadline=Date.now()+22*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
      userName:username,kernelSlug:slug,versionLabel
    });
    lastStatus=st?.status;
    failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,8000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:slug,versionLabel,pageSize:20
  });
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_wangp_bootstrap_timeout status='+String(lastStatus));
  const statusText=String(lastStatus??'').toUpperCase();
  if(statusText==='3'||statusText.includes('ERROR')){
    throw new Error('kaggle_wangp_bootstrap_failed: '+String(failureMessage||'')+' log_tail='+String(out?.log||'').slice(-7000));
  }
  const payload=extractKaggleJsonMarker(out?.log||'','ND_WANGP_BOOTSTRAP_JSON=','kaggle_wangp_bootstrap_payload_unparseable');
  const result={
    state:'PASS',
    username,
    ref:fullSlug+'/'+version,
    version,
    provider_url:save?.url||null,
    provider_status:lastStatus,
    bootstrap:payload
  };
  console.log(JSON.stringify({event:'ND_KAGGLE_WANGP_BOOTSTRAP',...result}));
  return result;
}



async function kaggleWan21Cache(){
  const enabled=String(process.env.ND_KAGGLE_WAN21_CACHE_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_wan21_cache_auth_failed');
  const username=String(intro.username);
  const slug='nd-wan21-weight-cache';
  const fullSlug=username+'/'+slug;
  const filename='wan2.1_image2video_480p_14B_quanto_mfp16_int8.safetensors';
  const script=[
    "from pathlib import Path",
    "import hashlib,json,requests,shutil,time",
    "name='"+filename+"'",
    "url='https://huggingface.co/DeepBeepMeep/Wan2.1/resolve/main/'+name",
    "dst=Path('/kaggle/working')/name",
    "du=shutil.disk_usage('/kaggle/working')",
    "print('ND_WAN21_CACHE_DISK='+json.dumps({'free_gb':round(du.free/1e9,2),'total_gb':round(du.total/1e9,2)}))",
    "if du.free < 18.5*10**9: raise RuntimeError('insufficient disk for transformer cache')",
    "t0=time.time(); h=hashlib.sha256(); size=0",
    "with requests.get(url,stream=True,timeout=(30,300),allow_redirects=True) as r:",
    "    r.raise_for_status()",
    "    with dst.open('wb') as f:",
    "        for chunk in r.iter_content(chunk_size=16*1024*1024):",
    "            if not chunk: continue",
    "            f.write(chunk); h.update(chunk); size+=len(chunk)",
    "receipt={'ok':True,'filename':name,'size_bytes':size,'sha256':h.hexdigest(),'elapsed_seconds':round(time.time()-t0,2)}",
    "Path('/kaggle/working/cache-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')",
    "print('ND_WAN21_CACHE_JSON='+json.dumps(receipt,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:'ND Wan21 Weight Cache',text:script,language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],
    isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:true,modelDataSources:[],
    sessionTimeoutSeconds:3600
  });
  if(save?.error) throw new Error('kaggle_wan21_cache_save_error: '+String(save.error).slice(0,500));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_wan21_cache_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null,failureMessage=null;
  const deadline=Date.now()+55*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,12000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_wan21_cache_timeout status='+String(lastStatus));
  const statusText=String(lastStatus??'').toUpperCase();
  if(statusText==='3'||statusText.includes('ERROR')) throw new Error('kaggle_wan21_cache_failed: '+String(failureMessage||'')+' log_tail='+String(out?.log||'').slice(-9000));
  const payload=extractKaggleJsonMarker(out?.log||'','ND_WAN21_CACHE_JSON=','kaggle_wan21_cache_payload_unparseable');
  const files=(out?.files||[]).map(f=>({file_name:f?.fileName||f?.file_name||null,url:f?.url||null,size:f?.size||null})).filter(x=>x.file_name);
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,provider_url:save?.url||null,provider_status:lastStatus,cache:payload,output_files:files};
  console.log(JSON.stringify({event:'ND_KAGGLE_WAN21_CACHE',...result}));
  return result;
}

async function kaggleWanGPGeneration(){
  const enabled=String(process.env.ND_KAGGLE_WANGP_GENERATE_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_wangp_generation_auth_failed');
  const username=String(intro.username);
  const slug='nd-wangp-first-last-qualification';
  const fullSlug=username+'/'+slug;
  const script=[
    "from pathlib import Path",
    "import json, os, platform, shutil, subprocess, sys, time",
    "ROOT=Path('/kaggle/working/Wan2GP')",
    "OUT=Path('/kaggle/working/wangp-output')",
    "COMMIT='2345ae148f82740f66e82c41292dbbdd592e713d'",
    "os.environ['HF_XET_HIGH_PERFORMANCE']='1'",
    "def run(cmd,timeout):",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)",
    "    if p.returncode!=0:",
    "        print('ND_WANGP_COMMAND_FAIL '+str(cmd)+'\\n'+p.stdout[-10000:])",
    "        raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "du=shutil.disk_usage('/kaggle/working')",
    "print('ND_WANGP_DISK_JSON='+json.dumps({'total_gb':round(du.total/1e9,2),'free_gb':round(du.free/1e9,2)}))",
    "if du.free < 28*10**9:",
    "    raise RuntimeError('insufficient /kaggle/working free disk for bounded Wan2.1 INT8 qualification: '+str(round(du.free/1e9,2))+' GB')",
    "if ROOT.exists():",
    "    run(['git','-C',str(ROOT),'fetch','--depth','1','origin',COMMIT],240)",
    "else:",
    "    run(['git','clone','--filter=blob:none','https://github.com/deepbeepmeep/Wan2GP.git',str(ROOT)],300)",
    "run(['git','-C',str(ROOT),'checkout',COMMIT],120)",
    "run([sys.executable,'-m','pip','install','-q','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],1500)",
    "from PIL import Image, ImageDraw",
    "W,H=832,480",
    "def frame(path,boat_x,lightning_x,phase):",
    "    im=Image.new('RGB',(W,H),(13,22,40)); d=ImageDraw.Draw(im)",
    "    d.rectangle([0,0,W,235],fill=(12,20,39)); d.rectangle([0,235,W,H],fill=(14,48,72))",
    "    for y in range(250,H,28):",
    "        off=(phase*13+y//7)%70",
    "        for x in range(-70,W+70,140): d.arc([x+off,y-12,x+off+110,y+25],180,350,fill=(95,145,165),width=3)",
    "    bx=boat_x; by=290",
    "    d.polygon([(bx-70,by),(bx+70,by),(bx+48,by+34),(bx-48,by+34)],fill=(72,42,29))",
    "    d.line([(bx,by),(bx,by-125)],fill=(210,195,165),width=5)",
    "    d.polygon([(bx+2,by-118),(bx+2,by-20),(bx+70,by-45)],fill=(205,205,185))",
    "    d.polygon([(bx-3,by-105),(bx-3,by-28),(bx-55,by-48)],fill=(170,180,170))",
    "    lx=lightning_x; d.line([(lx,35),(lx-25,100),(lx+3,100),(lx-35,175)],fill=(238,242,255),width=5)",
    "    for x in range(0,W,35): d.line([(x,0),(x-55,H)],fill=(80,110,135),width=1)",
    "    im.save(path)",
    "start=Path('/kaggle/working/start.png'); end=Path('/kaggle/working/end.png')",
    "frame(start,235,660,0); frame(end,595,210,1)",
    "sys.path.insert(0,str(ROOT)); os.chdir(ROOT)",
    "from shared.api import init",
    "OUT.mkdir(parents=True,exist_ok=True)",
    "session=init(root=ROOT,output_dir=OUT,cli_args=['--profile','4','--attention','sdpa','--fp16','--perc-reserved-mem-max','0.2'],console_output=True)",
    "schema=(session.get_model_schema('i2v') or {}).get('metadata') or {}",
    "settings=session.get_default_settings('i2v')",
    "saved=session.get_model_settings('i2v',include_selection=True)",
    "profile_entry=None",
    "for ent in saved.get('settings',[]):",
    "    if 'lightx2v' in ent.get('id','').lower() and '4 steps' in ent.get('id','').lower(): profile_entry=ent; break",
    "profile_id=None",
    "if profile_entry:",
    "    profile_id=profile_entry['id']; prof=session.get_model_settings('i2v',profile_id).get('content') or {}; settings.update(prof)",
    "fmin=int(schema.get('frames_minimum') or 5); fstep=int(schema.get('frames_steps') or 4)",
    "frames=fmin+7*fstep",
    "settings.update({'model_type':'i2v','prompt':'Cinematic fixed-camera night storm at sea. The wooden sailing ship travels smoothly from left to right while waves surge, rain lashes diagonally, sails billow in strong wind, and lightning shifts across the sky. Preserve the same ship and scene geometry, begin at the supplied start image and finish at the supplied end image.','negative_prompt':'text, watermark, duplicate ship, warped hull, extra mast, static frame','resolution':'832x480','video_length':frames,'force_fps':16,'seed':42,'image_start':str(start),'image_end':str(end),'image_prompt_type':'SE','batch_size':1})",
    "print('ND_WANGP_SETTINGS_JSON='+json.dumps({'model_type':settings.get('model_type'),'resolution':settings.get('resolution'),'video_length':settings.get('video_length'),'steps':settings.get('num_inference_steps'),'profile_id':profile_id,'image_prompt_type':settings.get('image_prompt_type'),'schema_frames_minimum':fmin,'schema_frames_steps':fstep},sort_keys=True))",
    "t0=time.time(); result=session.submit_task(settings).result(timeout=4200); elapsed=time.time()-t0",
    "if not result.success:",
    "    errs=[getattr(e,'message',str(e)) for e in (result.errors or [])]",
    "    raise RuntimeError('WanGP generation failed: '+' | '.join(errs))",
    "files=[Path(p) for p in (result.generated_files or [])]",
    "if not files: raise RuntimeError('WanGP returned no generated files')",
    "src=files[0]",
    "if not src.is_absolute(): src=OUT/src",
    "dst=Path('/kaggle/working/result.mp4'); shutil.copy2(src,dst)",
    "import cv2, numpy as np",
    "cap=cv2.VideoCapture(str(dst)); n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps=float(cap.get(cv2.CAP_PROP_FPS) or 0); vw=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); vh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))",
    "ok,first=cap.read(); last=None",
    "while True:",
    "    ok2,fr=cap.read()",
    "    if not ok2: break",
    "    last=fr",
    "cap.release()",
    "if first is None or last is None: raise RuntimeError('generated MP4 could not yield first/last frames')",
    "cv2.imwrite('/kaggle/working/generated_first.png',first); cv2.imwrite('/kaggle/working/generated_last.png',last)",
    "s=np.array(Image.open(start).convert('RGB')); e=np.array(Image.open(end).convert('RGB'))",
    "f=cv2.cvtColor(cv2.resize(first,(W,H)),cv2.COLOR_BGR2RGB); l=cv2.cvtColor(cv2.resize(last,(W,H)),cv2.COLOR_BGR2RGB)",
    "mae=lambda a,b: float(np.mean(np.abs(a.astype(np.float32)-b.astype(np.float32)))/255.0)",
    "m={'first_to_start':mae(f,s),'first_to_end':mae(f,e),'last_to_start':mae(l,s),'last_to_end':mae(l,e)}",
    "directional=bool(m['first_to_start'] < m['first_to_end'] and m['last_to_end'] < m['last_to_start'])",
    "receipt={'ok':True,'model_type':'i2v','profile_id':profile_id,'image_prompt_type':'SE','resolution':[vw,vh],'frame_count':n,'fps':fps,'duration_seconds':(n/fps if fps else None),'size_bytes':dst.stat().st_size,'elapsed_seconds':round(elapsed,2),'endpoint_mae':m,'directional_endpoint_pass':directional,'generated_source':str(src),'wangp_commit':COMMIT}",
    "Path('/kaggle/working/result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')",
    "print('ND_WANGP_GENERATION_JSON='+json.dumps(receipt,separators=(',',':'),sort_keys=True))"
  ].join('\n');

  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,
    newTitle:'ND WanGP First Last Qualification',
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
    enableInternet:true,
    modelDataSources:[],
    sessionTimeoutSeconds:5400,
    machineShape:'NvidiaTeslaT4'
  });
  if(save?.error) throw new Error('kaggle_wangp_generation_save_error: '+String(save.error).slice(0,500));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_wangp_generation_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null, failureMessage=null;
  const deadline=Date.now()+85*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,12000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_wangp_generation_timeout status='+String(lastStatus));
  const statusText=String(lastStatus??'').toUpperCase();
  if(statusText==='3'||statusText.includes('ERROR')){
    throw new Error('kaggle_wangp_generation_failed: '+String(failureMessage||'')+' log_tail='+String(out?.log||'').slice(-12000));
  }
  const payload=extractKaggleJsonMarker(out?.log||'','ND_WANGP_GENERATION_JSON=','kaggle_wangp_generation_payload_unparseable');
  const files=(out?.files||[]).map(f=>({file_name:f?.fileName||f?.file_name||null,url:f?.url||null,size:f?.size||null})).filter(x=>x.file_name);
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,provider_url:save?.url||null,provider_status:lastStatus,generation:payload,output_files:files};
  console.log(JSON.stringify({event:'ND_KAGGLE_WANGP_GENERATION',...result}));
  return result;
}


async function kaggleWanGPI2VQualification(){
  const enabled=String(process.env.ND_KAGGLE_WANGP_I2V_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_wangp_i2v_auth_failed');
  const username=String(intro.username);
  const slug='nd-wangp-i2v-qualification';
  const fullSlug=username+'/'+slug;
  const script=[
    "from pathlib import Path",
    "import hashlib, json, os, platform, shutil, subprocess, sys",
    "ROOT=Path('/kaggle/working/Wan2GP')",
    "OUT=Path('/kaggle/working/wangp-i2v-out')",
    "WORK=Path('/kaggle/working')",
    "COMMIT='2345ae148f82740f66e82c41292dbbdd592e713d'",
    "MODEL='i2v_2_2_Enhanced_Lightning_v2'",
    "def run(cmd,timeout):",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)",
    "    if p.returncode!=0:",
    "        print('ND_WANGP_COMMAND_FAIL '+str(cmd)+'\\n'+p.stdout[-8000:])",
    "        raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "if ROOT.exists():",
    "    run(['git','-C',str(ROOT),'fetch','--depth','1','origin',COMMIT],180)",
    "else:",
    "    run(['git','clone','--filter=blob:none','https://github.com/deepbeepmeep/Wan2GP.git',str(ROOT)],240)",
    "run(['git','-C',str(ROOT),'checkout',COMMIT],90)",
    "run([sys.executable,'-m','pip','install','-q','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],1200)",
    "sys.path.insert(0,str(ROOT))",
    "os.chdir(ROOT)",
    "from PIL import Image, ImageDraw",
    "import cv2, numpy as np",
    "from shared.api import init",
    "W,H=832,480",
    "def make_frame(path,ship_x,sun_x,warm=False):",
    "    sky=(202,170,132) if warm else (132,190,224)",
    "    sea=(37,94,124) if warm else (28,105,145)",
    "    im=Image.new('RGB',(W,H),sky)",
    "    d=ImageDraw.Draw(im)",
    "    d.rectangle((0,270,W,H),fill=sea)",
    "    d.ellipse((sun_x-34,62,sun_x+34,130),fill=(247,204,92))",
    "    d.polygon([(ship_x-70,345),(ship_x+78,345),(ship_x+45,382),(ship_x-52,382)],fill=(33,31,29))",
    "    d.line((ship_x,345,ship_x,205),fill=(28,25,22),width=7)",
    "    d.polygon([(ship_x+4,214),(ship_x+4,331),(ship_x+92,331)],fill=(236,229,206))",
    "    d.polygon([(ship_x-5,230),(ship_x-5,325),(ship_x-66,325)],fill=(220,214,194))",
    "    for y in (410,438,462):",
    "        d.arc((20,y-18,W-20,y+14),0,180,fill=(172,215,228),width=3)",
    "    im.save(path)",
    "start_path=WORK/'start.png'",
    "end_path=WORK/'end.png'",
    "make_frame(start_path,230,120,False)",
    "make_frame(end_path,610,705,True)",
    "OUT.mkdir(parents=True,exist_ok=True)",
    "session=init(root=ROOT,output_dir=OUT,cli_args=['--profile','4','--attention','sdpa','--fp16','--perc-reserved-mem-max','0.2'],console_output=True)",
    "schema=session.get_model_schema(MODEL)",
    "settings=session.get_default_settings(MODEL)",
    "settings.update({",
    "    'model_type':MODEL,",
    "    'prompt':'Cinematic continuous ocean shot. A small sailing ship moves smoothly from the left side of frame to the right while the sea and sails move naturally. Preserve the same ship, horizon and composition. Physically coherent waves, wind and camera perspective, no cuts.',",
    "    'negative_prompt':'flicker, duplicate ship, disappearing ship, sudden cut, warped hull, extra sails, text, watermark',",
    "    'image_start':str(start_path),",
    "    'image_end':str(end_path),",
    "    'image_prompt_type':'SE',",
    "    'resolution':'832x480',",
    "    'video_length':'2s',",
    "    'seed':42",
    "})",
    "print('ND_WANGP_I2V_SETTINGS_JSON='+json.dumps({'model_type':MODEL,'name':schema.get('name'),'resolution':settings.get('resolution'),'video_length':settings.get('video_length'),'steps':settings.get('num_inference_steps'),'image_prompt_type':settings.get('image_prompt_type')},sort_keys=True))",
    "job=session.submit_task(settings)",
    "result=job.result(timeout=3000)",
    "if not result.success:",
    "    errs=[getattr(e,'message',str(e)) for e in (result.errors or [])]",
    "    raise RuntimeError('WanGP generation failed: '+' | '.join(errs))",
    "files=[Path(p) for p in (result.generated_files or [])]",
    "video=None",
    "for p in files:",
    "    q=p if p.is_absolute() else OUT/p",
    "    if q.suffix.lower() in ('.mp4','.mov','.mkv','.webm') and q.exists():",
    "        video=q; break",
    "if video is None: raise RuntimeError('WanGP returned no video file: '+str(files))",
    "dst=WORK/'result.mp4'",
    "shutil.copy2(video,dst)",
    "cap=cv2.VideoCapture(str(dst))",
    "n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)",
    "fps=float(cap.get(cv2.CAP_PROP_FPS) or 0.0)",
    "ow=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0); oh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)",
    "ok,first=cap.read()",
    "if not ok: raise RuntimeError('cannot read first output frame')",
    "cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,n-1))",
    "ok,last=cap.read()",
    "cap.release()",
    "if not ok: raise RuntimeError('cannot read last output frame')",
    "cv2.imwrite(str(WORK/'output_first.png'),first)",
    "cv2.imwrite(str(WORK/'output_last.png'),last)",
    "a=cv2.imread(str(start_path)); b=cv2.imread(str(end_path))",
    "a=cv2.resize(a,(ow,oh)); b=cv2.resize(b,(ow,oh))",
    "def mae(x,y): return float(np.mean(np.abs(x.astype(np.float32)-y.astype(np.float32))))",
    "mfs=mae(first,a); mfe=mae(first,b); mle=mae(last,b); mls=mae(last,a); input_delta=mae(a,b)",
    "sha=hashlib.sha256(dst.read_bytes()).hexdigest()",
    "receipt={",
    " 'ok':True,'model_type':MODEL,'model_name':schema.get('name'),'wangp_commit':COMMIT,",
    " 'output_file':'result.mp4','size_bytes':dst.stat().st_size,'sha256':sha,",
    " 'width':ow,'height':oh,'frames':n,'fps':fps,'duration_seconds':(n/fps if fps else None),",
    " 'input_delta_mae':input_delta,'first_to_start_mae':mfs,'first_to_end_mae':mfe,",
    " 'last_to_end_mae':mle,'last_to_start_mae':mls,",
    " 'endpoint_order_pass':bool(mfs<mfe and mle<mls)",
    "}",
    "(WORK/'result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')",
    "print('ND_WANGP_I2V_RESULT_JSON='+json.dumps(receipt,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,
    newTitle:'ND WanGP I2V Qualification',
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
    enableInternet:true,
    modelDataSources:[],
    sessionTimeoutSeconds:3600,
    machineShape:'NvidiaTeslaT4'
  });
  if(save?.error) throw new Error('kaggle_wangp_i2v_save_error: '+String(save.error).slice(0,700));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_wangp_i2v_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null, failureMessage=null;
  const deadline=Date.now()+58*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{
      userName:username,kernelSlug:slug,versionLabel
    });
    lastStatus=st?.status;
    failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,12000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug:slug,versionLabel,pageSize:100
  });
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_wangp_i2v_timeout status='+String(lastStatus));
  const statusText=String(lastStatus??'').toUpperCase();
  if(statusText==='3'||statusText.includes('ERROR')){
    throw new Error('kaggle_wangp_i2v_failed: '+String(failureMessage||'')+' log_tail='+String(out?.log||'').slice(-10000));
  }
  const payload=extractKaggleJsonMarker(out?.log||'','ND_WANGP_I2V_RESULT_JSON=','kaggle_wangp_i2v_payload_unparseable');
  const fileList=Array.isArray(out?.files)?out.files.map(x=>({
    name:x?.fileName||x?.name||x?.path||null,
    size:x?.fileSize??x?.size??null
  })).filter(x=>x.name):[];
  const result={
    state:'PASS',
    username,
    ref:fullSlug+'/'+version,
    version,
    provider_url:save?.url||null,
    provider_status:lastStatus,
    output_files:fileList,
    qualification:payload
  };
  console.log(JSON.stringify({event:'ND_KAGGLE_WANGP_I2V',...result}));
  return result;
}


async function kaggleWanGPDiskFit(){
  const enabled=String(process.env.ND_KAGGLE_WANGP_DISK_FIT_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_wangp_disk_fit_auth_failed');
  const username=String(intro.username), slug='nd-wangp-disk-fit', fullSlug=username+'/'+slug;
  const script=[
    "import json, os, pathlib, shutil, subprocess, sys, urllib.request",
    "ROOT=pathlib.Path('/kaggle/working/Wan2GP')",
    "COMMIT='2345ae148f82740f66e82c41292dbbdd592e713d'",
    "MODEL_URL='https://huggingface.co/DeepBeepMeep/Wan2.2/resolve/main/wan22EnhancedLightning_v2I2VFP8LOW.safetensors'",
    "def du(path):",
    "    u=shutil.disk_usage(path); return {'total_gib':round(u.total/2**30,3),'used_gib':round(u.used/2**30,3),'free_gib':round(u.free/2**30,3)}",
    "def run(cmd,timeout):",
    "    env={**os.environ,'PIP_NO_CACHE_DIR':'1','HF_HUB_DISABLE_XET':'1'}",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,env=env)",
    "    if p.returncode!=0:",
    "        print('ND_CMD_FAIL '+str(cmd)+'\\\\n'+p.stdout[-8000:]); raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "out={'python':sys.version.split()[0],'before':du('/kaggle/working')}",
    "run(['git','clone','--filter=blob:none','https://github.com/deepbeepmeep/Wan2GP.git',str(ROOT)],240)",
    "run(['git','-C',str(ROOT),'checkout',COMMIT],90)",
    "out['after_clone']=du('/kaggle/working')",
    "run([sys.executable,'-m','pip','install','--no-cache-dir','-q','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],1200)",
    "for p in [pathlib.Path.home()/'.cache/pip',pathlib.Path.home()/'.cache/huggingface']:",
    "    try:",
    "        if p.exists(): shutil.rmtree(p,ignore_errors=True)",
    "    except: pass",
    "out['after_install_cleanup']=du('/kaggle/working')",
    "try:",
    "    req=urllib.request.Request(MODEL_URL,method='HEAD',headers={'User-Agent':'nd-kaggle-disk-fit/1.0'})",
    "    with urllib.request.urlopen(req,timeout=60) as resp: size=int(resp.headers.get('Content-Length') or 0)",
    "except Exception as e:",
    "    size=14300000000; out['head_error']=str(e)[:500]",
    "out['checkpoint_bytes']=size; out['checkpoint_gib']=round(size/2**30,3); out['reserve_gib']=2.0",
    "out['fits_with_2gib_reserve']=out['after_install_cleanup']['free_gib'] >= out['checkpoint_gib']+2.0",
    "print('ND_DISK_FIT_JSON='+json.dumps(out,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:'ND WanGP Disk Fit',text:script,language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],
    isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:true,modelDataSources:[],
    sessionTimeoutSeconds:1800
  });
  if(save?.error) throw new Error('kaggle_disk_fit_save_error: '+String(save.error).slice(0,700));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_disk_fit_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null,failureMessage=null;
  const deadline=Date.now()+25*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,8000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_disk_fit_timeout status='+String(lastStatus));
  const stx=String(lastStatus??'').toUpperCase();
  if(stx==='3'||stx.includes('ERROR')) throw new Error('kaggle_disk_fit_failed: '+String(failureMessage||'')+' tail='+String(out?.log||'').slice(-9000));
  const payload=extractKaggleJsonMarker(out?.log||'','ND_DISK_FIT_JSON=','kaggle_disk_fit_payload_unparseable');
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,provider_status:lastStatus,disk_fit:payload};
  console.log(JSON.stringify({event:'ND_KAGGLE_WANGP_DISK_FIT',...result}));
  return result;
}


async function kaggleSdCppFLFQualification(){
  const enabled=String(process.env.ND_KAGGLE_SDCPP_FLF_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_sdcpp_flf_auth_failed');
  const username=String(intro.username);
  const slug='nd-sd-cpp-flf-qualification';
  const fullSlug=username+'/'+slug;
  const script=[
    "from pathlib import Path",
    "import hashlib, json, os, platform, shutil, subprocess, sys",
    "WORK=Path('/kaggle/working')",
    "SRC=WORK/'stable-diffusion.cpp'",
    "MODELS=WORK/'models'",
    "SD_COMMIT='2f886889e6e8b78738d6b87f7191f6018557c551'",
    "def run(cmd,timeout,env=None):",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,env=env)",
    "    if p.returncode!=0:",
    "        print('ND_SDCPP_COMMAND_FAIL '+str(cmd)+'\\\\n'+p.stdout[-12000:])",
    "        raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "def disk():",
    "    u=shutil.disk_usage(WORK); return {'total_gib':round(u.total/2**30,3),'used_gib':round(u.used/2**30,3),'free_gib':round(u.free/2**30,3)}",
    "receipt={'python':platform.python_version(),'sd_commit':SD_COMMIT,'disk_before':disk()}",
    "print('ND_SDCPP_STAGE=build_start')",
    "run(['git','clone','--filter=blob:none','https://github.com/leejet/stable-diffusion.cpp.git',str(SRC)],300)",
    "run(['git','-C',str(SRC),'checkout',SD_COMMIT],120)",
    "run(['git','-C',str(SRC),'submodule','update','--init','--recursive','--depth','1'],600)",
    "receipt['nvcc']=run(['nvcc','--version'],60).splitlines()[-1] if shutil.which('nvcc') else None",
    "stub_candidates=[Path('/usr/local/cuda/lib64/stubs/libcuda.so'),Path('/usr/local/cuda/targets/x86_64-linux/lib/stubs/libcuda.so')]",
    "cuda_stub=next((p for p in stub_candidates if p.exists()),None)",
    "if cuda_stub is None: raise RuntimeError('CUDA driver stub libcuda.so not found')",
    "receipt['cuda_driver_stub']=str(cuda_stub)",
    "cm=SRC/'CMakeLists.txt'",
    "txt=cm.read_text(encoding='utf-8')",
    "anchor='# deps\\ninclude(cmake/ggml.cmake)'",
    "inject='''# Kaggle managed images provide the CUDA driver stub but FindCUDAToolkit may not export CUDA::cuda_driver.\\nif(SD_CUDA AND NOT TARGET CUDA::cuda_driver)\\n  add_library(CUDA::cuda_driver UNKNOWN IMPORTED GLOBAL)\\n  set_target_properties(CUDA::cuda_driver PROPERTIES IMPORTED_LOCATION \\\"'''+str(cuda_stub)+'''\\\")\\nendif()\\n\\n# deps\\ninclude(cmake/ggml.cmake)'''",
    "if anchor not in txt: raise RuntimeError('stable-diffusion.cpp CMake deps anchor missing')",
    "cm.write_text(txt.replace(anchor,inject,1),encoding='utf-8')",
    "if not receipt['nvcc']: raise RuntimeError('nvcc not available in Kaggle runtime')",
    "run(['cmake','-S',str(SRC),'-B',str(SRC/'build'),'-DSD_CUDA=ON','-DSD_WEBP=OFF','-DSD_WEBM=OFF','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CUDA_ARCHITECTURES=75'],600)",
    "run(['cmake','--build',str(SRC/'build'),'--config','Release','-j2'],1200)",
    "cli=SRC/'build/bin/sd-cli'",
    "if not cli.exists():",
    "    candidates=list((SRC/'build').rglob('sd-cli'))",
    "    if not candidates: raise RuntimeError('sd-cli binary not found after build')",
    "    cli=candidates[0]",
    "receipt['disk_after_build']=disk()",
    "MODELS.mkdir(parents=True,exist_ok=True)",
    "assets={",
    " 'dit':('wan2.1-flf2v-14b-720p-Q3_K_S.gguf','https://huggingface.co/city96/Wan2.1-FLF2V-14B-720P-gguf/resolve/main/wan2.1-flf2v-14b-720p-Q3_K_S.gguf?download=true'),",
    " 't5':('umt5-xxl-encoder-Q3_K_S.gguf','https://huggingface.co/city96/umt5-xxl-encoder-gguf/resolve/main/umt5-xxl-encoder-Q3_K_S.gguf?download=true'),",
    " 'clip':('clip_vision_h.safetensors','https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors?download=true'),",
    " 'vae':('wan_2.1_vae.safetensors','https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors?download=true')",
    "}",
    "paths={}",
    "for key,(name,url) in assets.items():",
    "    path=MODELS/name; paths[key]=path",
    "    print('ND_SDCPP_DOWNLOAD_START='+key)",
    "    run(['curl','-L','--fail','--silent','--show-error','--retry','5','--retry-delay','2','-o',str(path),url],1800)",
    "    print('ND_SDCPP_DOWNLOAD_DONE='+key+':'+str(path.stat().st_size))",
    "receipt['asset_sizes']={k:int(v.stat().st_size) for k,v in paths.items()}",
    "receipt['disk_after_downloads']=disk()",
    "from PIL import Image,ImageDraw",
    "W,H=832,480",
    "def make(path,ship_x,sun_x,warm=False):",
    "    sky=(199,160,121) if warm else (116,183,222)",
    "    sea=(42,87,117) if warm else (25,104,145)",
    "    im=Image.new('RGB',(W,H),sky); d=ImageDraw.Draw(im)",
    "    d.rectangle((0,270,W,H),fill=sea)",
    "    d.ellipse((sun_x-35,62,sun_x+35,132),fill=(248,206,88))",
    "    d.polygon([(ship_x-74,344),(ship_x+78,344),(ship_x+43,383),(ship_x-55,383)],fill=(34,31,29))",
    "    d.line((ship_x,344,ship_x,204),fill=(28,25,22),width=7)",
    "    d.polygon([(ship_x+4,215),(ship_x+4,330),(ship_x+94,330)],fill=(239,231,206))",
    "    d.polygon([(ship_x-5,231),(ship_x-5,325),(ship_x-67,325)],fill=(221,214,194))",
    "    for y in (408,438,465): d.arc((20,y-20,W-20,y+12),0,180,fill=(173,216,229),width=3)",
    "    im.save(path)",
    "start=WORK/'start.png'; end=WORK/'end.png'",
    "make(start,225,115,False); make(end,610,710,True)",
    "avi=WORK/'result.avi'; mp4=WORK/'result.mp4'",
    "prompt='Cinematic continuous ocean shot. The same small sailing ship travels smoothly from left to right. Natural moving waves and wind-filled sails, coherent perspective and lighting transition, no cuts, preserve hull and mast identity.'",
    "neg='flicker, duplicate ship, extra ship, disappearing ship, malformed hull, extra mast, text, watermark, sudden cut'",
    "cmd=[str(cli),'-M','vid_gen','--diffusion-model',str(paths['dit']),'--vae',str(paths['vae']),'--t5xxl',str(paths['t5']),'--clip_vision',str(paths['clip']),'-p',prompt,'-n',neg,'--cfg-scale','5.0','--sampling-method','euler','--steps','8','-W',str(W),'-H',str(H),'--diffusion-fa','--video-frames','17','--offload-to-cpu','--init-img',str(start),'--end-img',str(end),'--flow-shift','3.0','--seed','42','-o',str(avi)]",
    "print('ND_SDCPP_STAGE=generation_start')",
    "genlog=run(cmd,3000)",
    "receipt['generation_log_tail']=genlog[-2500:]",
    "if not avi.exists() or avi.stat().st_size<1024: raise RuntimeError('sd-cli returned no valid AVI')",
    "run(['ffmpeg','-y','-loglevel','error','-i',str(avi),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(mp4)],300)",
    "if not mp4.exists() or mp4.stat().st_size<1024: raise RuntimeError('MP4 conversion failed')",
    "import cv2, numpy as np",
    "cap=cv2.VideoCapture(str(mp4)); n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); fps=float(cap.get(cv2.CAP_PROP_FPS) or 0); ow=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0); oh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)",
    "ok,first=cap.read()",
    "if not ok: raise RuntimeError('cannot read first MP4 frame')",
    "cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,n-1)); ok,last=cap.read(); cap.release()",
    "if not ok: raise RuntimeError('cannot read last MP4 frame')",
    "cv2.imwrite(str(WORK/'output_first.png'),first); cv2.imwrite(str(WORK/'output_last.png'),last)",
    "a=cv2.resize(cv2.imread(str(start)),(ow,oh)); b=cv2.resize(cv2.imread(str(end)),(ow,oh))",
    "def mae(x,y): return float(np.mean(np.abs(x.astype(np.float32)-y.astype(np.float32))))",
    "mfs,mfe,mle,mls=mae(first,a),mae(first,b),mae(last,b),mae(last,a)",
    "receipt.update({'ok':True,'model':'Wan2.1-FLF2V-14B-720P-GGUF-Q3_K_S','width':ow,'height':oh,'frames':n,'fps':fps,'duration_seconds':(n/fps if fps else None),'size_bytes':mp4.stat().st_size,'sha256':hashlib.sha256(mp4.read_bytes()).hexdigest(),'first_to_start_mae':mfs,'first_to_end_mae':mfe,'last_to_end_mae':mle,'last_to_start_mae':mls,'endpoint_order_pass':bool(mfs<mfe and mle<mls),'disk_final':disk()})",
    "(WORK/'result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')",
    "print('ND_SDCPP_FLF_RESULT_JSON='+json.dumps(receipt,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  // Read existing ND kernel statuses before requesting another accelerator slot.
  let activeNd=[];
  try{
    const listing=await kaggleRpc('kernels.KernelsApiService','ListKernels',{user:username,pageSize:100});
    const kernels=Array.isArray(listing?.kernels)?listing.kernels:[];
    for(const k of kernels){
      const ks=String(k?.slug||k?.ref||'').split('/').pop();
      const ver=Number(k?.currentVersionNumber||k?.current_version_number||0);
      if(!ks?.startsWith('nd-')||!ver) continue;
      try{
        const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:ks,versionLabel:'v'+ver});
        const sv=String(st?.status??'');
        if(sv==='0'||sv==='1'||sv.toUpperCase().includes('QUEUED')||sv.toUpperCase().includes('RUNNING')){
          activeNd.push({slug:ks,version:ver,status:st?.status});
        }
      }catch{}
    }
  }catch(e){
    console.log(JSON.stringify({event:'ND_KAGGLE_SESSION_PREFLIGHT',state:'LIST_FAILED',error:String(e?.message||e).slice(0,1200)}));
  }
  if(activeNd.length){
    console.log(JSON.stringify({event:'ND_KAGGLE_SESSION_PREFLIGHT',state:'WAITING',active:activeNd}));
    const deadline=Date.now()+15*60*1000;
    while(Date.now()<deadline && activeNd.length){
      await new Promise(r=>setTimeout(r,15000));
      const next=[];
      for(const a of activeNd){
        try{
          const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:a.slug,versionLabel:'v'+a.version});
          const sv=String(st?.status??'');
          if(sv==='0'||sv==='1'||sv.toUpperCase().includes('QUEUED')||sv.toUpperCase().includes('RUNNING')) next.push({...a,status:st?.status});
        }catch{}
      }
      activeNd=next;
    }
  }
  if(activeNd.length) throw new Error('kaggle_sdcpp_flf_blocked_active_nd_sessions: '+JSON.stringify(activeNd));

  const baseSave={
    slug:fullSlug,newTitle:'ND sd.cpp FLF Qualification',text:script,language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],
    isPrivate:true,enableGpu:true,enableTpu:false,enableInternet:true,modelDataSources:[],
    sessionTimeoutSeconds:3600
  };
  let save=null,chosenShape=null,last403=null;
  for(const shape of ['NvidiaTeslaT4','NvidiaTeslaP100']){
    try{
      save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{...baseSave,machineShape:shape});
      chosenShape=shape;
      break;
    }catch(e){
      if(Number(e?.status)===403){
        last403=String(e?.message||e);
        console.log(JSON.stringify({event:'ND_KAGGLE_SDCPP_ADMISSION',state:'REJECTED',machine_shape:shape,error:last403.slice(0,1800)}));
        await new Promise(r=>setTimeout(r,20000));
        continue;
      }
      throw e;
    }
  }
  if(!save) throw new Error('kaggle_sdcpp_flf_all_gpu_shapes_rejected: '+String(last403||'unknown'));
  if(save?.error) throw new Error('kaggle_sdcpp_flf_save_error: '+JSON.stringify(save.error).slice(0,1200));
  console.log(JSON.stringify({event:'ND_KAGGLE_SDCPP_ADMISSION',state:'ACCEPTED',machine_shape:chosenShape}));
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version) throw new Error('kaggle_sdcpp_flf_missing_version');
  const versionLabel='v'+version;
  let lastStatus=null,failureMessage=null;
  const deadline=Date.now()+58*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,12000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:100});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_sdcpp_flf_timeout status='+String(lastStatus));
  const stx=String(lastStatus??'').toUpperCase();
  if(stx==='3'||stx.includes('ERROR')) throw new Error('kaggle_sdcpp_flf_failed: '+String(failureMessage||'')+' log_tail='+String(out?.log||'').slice(-12000));
  const payload=extractKaggleJsonMarker(out?.log||'','ND_SDCPP_FLF_RESULT_JSON=','kaggle_sdcpp_flf_payload_unparseable');
  const fileList=Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[];
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,machine_shape:chosenShape,provider_url:save?.url||null,provider_status:lastStatus,output_files:fileList,qualification:payload};
  console.log(JSON.stringify({event:'ND_KAGGLE_SDCPP_FLF',...result}));
  return result;
}


async function kaggleLtxMountProbe(){
  const enabled=String(process.env.ND_KAGGLE_LTX_MOUNT_PROBE_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_ltx_mount_probe_auth_failed');
  const username=String(intro.username);
  const slug='nd-ltx-model-mount-probe';
  const fullSlug=username+'/'+slug;
  const modelSource='marcelolmesilva/ltxv-13b-0.9.7-distilled-fp8.safetensors/pytorch/default/1';
  const script=[
    "from pathlib import Path",
    "import json, os, shutil",
    "root=Path('/kaggle/input')",
    "hits=[]",
    "for p in root.rglob('*'):",
    "    if p.is_file() and ('ltx' in p.name.lower() or p.suffix.lower()=='.safetensors'):",
    "        try:",
    "            st=p.stat(); readable=os.access(p,os.R_OK)",
    "            hits.append({'path':str(p),'size_bytes':int(st.st_size),'readable':bool(readable)})",
    "        except Exception as e:",
    "            hits.append({'path':str(p),'error':str(e)[:300]})",
    "    if len(hits)>=50: break",
    "u=shutil.disk_usage('/kaggle/working')",
    "out={'input_root_exists':root.exists(),'hits':hits,'working_total_bytes':int(u.total),'working_free_bytes':int(u.free)}",
    "print('ND_LTX_MOUNT_JSON='+json.dumps(out,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:'ND LTX Model Mount Probe',text:script,
    language:'python',kernelType:'script',
    datasetDataSources:[],kernelDataSources:[],competitionDataSources:[],categoryIds:[],
    modelDataSources:[modelSource],
    isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:false,
    sessionTimeoutSeconds:900
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version || save?.error || (save?.invalidModelSources||save?.invalid_model_sources||[]).length){
    throw new Error('kaggle_ltx_mount_save_failed: '+JSON.stringify({
      error:save?.error||null,
      version,
      invalid_model_sources:save?.invalidModelSources||save?.invalid_model_sources||[]
    }));
  }
  const versionLabel='v'+version;
  let lastStatus=null,failureMessage=null;
  const deadline=Date.now()+12*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,6000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_ltx_mount_timeout status='+String(lastStatus));
  const stx=String(lastStatus??'').toUpperCase();
  if(stx==='3'||stx.includes('ERROR')) throw new Error('kaggle_ltx_mount_failed: '+String(failureMessage||'')+' tail='+String(out?.log||'').slice(-8000));
  const payload=extractKaggleJsonMarker(out?.log||'','ND_LTX_MOUNT_JSON=','kaggle_ltx_mount_payload_unparseable');
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,provider_status:lastStatus,model_source:modelSource,mount:payload};
  console.log(JSON.stringify({event:'ND_KAGGLE_LTX_MOUNT_PROBE',...result}));
  return result;
}


async function kaggleLtxCacheProbe(){
  const enabled=String(process.env.ND_KAGGLE_LTX_CACHE_PROBE_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_ltx_cache_probe_auth_failed');
  const username=String(intro.username), slug='nd-ltx-cache-probe', fullSlug=username+'/'+slug;
  const datasetSource='damnyadav/ltxv13b-distilled-cache';
  const script=[
    "from pathlib import Path",
    "import json, os, shutil",
    "base=Path('/kaggle/input/datasets/damnyadav/ltxv13b-distilled-cache')",
    "def files_under(p,limit=40):",
    "    out=[]",
    "    if p.exists():",
    "        for x in p.rglob('*'):",
    "            if x.is_file():",
    "                try: out.append({'rel':str(x.relative_to(base)),'size':int(x.stat().st_size)})",
    "                except: pass",
    "                if len(out)>=limit: break",
    "    return out",
    "def find_root(base):",
    "    cands=[base]+[p for p in base.iterdir() if p.is_dir()] if base.exists() else []",
    "    for r in cands:",
    "        ok=((r/'transformer').is_dir() and any((r/'transformer').rglob('*.safetensors')) and (r/'text_encoder').is_dir() and any((r/'text_encoder').rglob('*.safetensors')) and (r/'vae').is_dir() and (r/'tokenizer').is_dir() and (r/'scheduler'/'scheduler_config.json').exists())",
    "        if ok: return r",
    "    return None",
    "root=find_root(base)",
    "u=shutil.disk_usage('/kaggle/working')",
    "out={'base_exists':base.exists(),'model_root':str(root) if root else None,'complete':bool(root),'sample_files':files_under(root or base,60),'working_free_bytes':int(u.free),'working_total_bytes':int(u.total)}",
    "print('ND_LTX_CACHE_JSON='+json.dumps(out,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:'ND LTX Cache Probe',text:script,language:'python',kernelType:'script',
    datasetDataSources:[datasetSource],kernelDataSources:[],competitionDataSources:[],categoryIds:[],
    modelDataSources:[],isPrivate:true,enableGpu:false,enableTpu:false,enableInternet:false,sessionTimeoutSeconds:900
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version || save?.error || (save?.invalidDatasetSources||save?.invalid_dataset_sources||[]).length){
    throw new Error('kaggle_ltx_cache_save_failed: '+JSON.stringify({error:save?.error||null,version,invalid_dataset_sources:save?.invalidDatasetSources||save?.invalid_dataset_sources||[]}));
  }
  const versionLabel='v'+version;
  let lastStatus=null,failureMessage=null;
  const deadline=Date.now()+12*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,6000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:50});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_ltx_cache_timeout status='+String(lastStatus));
  const stx=String(lastStatus??'').toUpperCase();
  if(stx==='3'||stx.includes('ERROR')) throw new Error('kaggle_ltx_cache_failed: '+String(failureMessage||'')+' tail='+String(out?.log||'').slice(-8000));
  const payload=extractKaggleJsonMarker(out?.log||'','ND_LTX_CACHE_JSON=','kaggle_ltx_cache_payload_unparseable');
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,provider_status:lastStatus,dataset_source:datasetSource,cache:payload};
  console.log(JSON.stringify({event:'ND_KAGGLE_LTX_CACHE_PROBE',...result}));
  return result;
}


async function kaggleLtxFirstLastQualification(){
  const enabled=String(process.env.ND_KAGGLE_LTX_F2L_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_ltx_f2l_auth_failed');
  const username=String(intro.username), slug='nd-ltx-first-last-qualification', fullSlug=username+'/'+slug;
  const datasetSource='damnyadav/ltxv13b-distilled-cache';
  const script=[
    "from pathlib import Path",
    "import gc, hashlib, inspect, json, os, platform, subprocess, sys, time",
    "os.environ['PYTORCH_CUDA_ALLOC_CONF']='expandable_segments:True'",
    "os.environ['TOKENIZERS_PARALLELISM']='false'",
    "MODEL=Path('/kaggle/input/datasets/damnyadav/ltxv13b-distilled-cache')",
    "WORK=Path('/kaggle/working')",
    "def run(cmd,timeout):",
    "    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,env={**os.environ,'PIP_NO_CACHE_DIR':'1'})",
    "    if p.returncode!=0:",
    "        print('ND_LTX_CMD_FAIL '+str(cmd)+'\\\\n'+p.stdout[-10000:]); raise RuntimeError('command failed: '+str(cmd))",
    "    return p.stdout",
    "run([sys.executable,'-m','pip','install','--no-cache-dir','-q','diffusers>=0.37.0','transformers>=4.48.0','accelerate>=1.2.0','bitsandbytes','sentencepiece','protobuf','imageio','imageio-ffmpeg','safetensors'],900)",
    "import numpy as np, torch, imageio.v2 as imageio",
    "from PIL import Image, ImageDraw",
    "from diffusers import LTXConditionPipeline, LTXVideoTransformer3DModel, AutoencoderKLLTXVideo, BitsAndBytesConfig as DiffusersBnBConfig",
    "from diffusers.schedulers import FlowMatchEulerDiscreteScheduler",
    "from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition",
    "from transformers import T5EncoderModel, T5TokenizerFast, BitsAndBytesConfig as TransformersBnBConfig",
    "assert torch.cuda.is_available() and torch.cuda.device_count()>=2, 'need T4x2'",
    "DT=torch.float16; G0=0; G1=1",
    "max_tr={G0:'14GiB',G1:'1GiB','cpu':'8GiB'}; max_t5={G0:'1GiB',G1:'14GiB','cpu':'8GiB'}",
    "nf4d=DiffusersBnBConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=DT)",
    "nf4t=TransformersBnBConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=DT)",
    "if not getattr(LTXVideoTransformer3DModel,'_no_split_modules',None): LTXVideoTransformer3DModel._no_split_modules=[]",
    "print('ND_LTX_STAGE=load_transformer')",
    "transformer=LTXVideoTransformer3DModel.from_pretrained(str(MODEL),subfolder='transformer',quantization_config=nf4d,torch_dtype=DT,device_map='auto',max_memory=max_tr,local_files_only=True)",
    "import torch.nn as nn",
    "class ChunkedFF(nn.Module):",
    "    def __init__(self,ff,chunk=512): super().__init__(); self.ff=ff; self.chunk=chunk",
    "    def forward(self,x,*a,**kw):",
    "        if x.shape[1]<=self.chunk: return self.ff(x,*a,**kw)",
    "        out=torch.empty_like(x)",
    "        for st in range(0,x.shape[1],self.chunk): out[:,st:min(st+self.chunk,x.shape[1])]=self.ff(x[:,st:min(st+self.chunk,x.shape[1])],*a,**kw)",
    "        return out",
    "for b in transformer.transformer_blocks:",
    "    if hasattr(b,'ff'): b.ff=ChunkedFF(b.ff,512)",
    "print('ND_LTX_STAGE=load_t5')",
    "text_encoder=T5EncoderModel.from_pretrained(str(MODEL),subfolder='text_encoder',quantization_config=nf4t,torch_dtype=DT,device_map='auto',max_memory=max_t5,local_files_only=True)",
    "tokenizer=T5TokenizerFast.from_pretrained(str(MODEL),subfolder='tokenizer',local_files_only=True)",
    "print('ND_LTX_STAGE=load_vae')",
    "vae=AutoencoderKLLTXVideo.from_pretrained(str(MODEL),subfolder='vae',torch_dtype=DT,local_files_only=True).to('cuda:0')",
    "scheduler=FlowMatchEulerDiscreteScheduler.from_pretrained(str(MODEL),subfolder='scheduler',local_files_only=True)",
    "pipe=LTXConditionPipeline(transformer=transformer,text_encoder=text_encoder,tokenizer=tokenizer,vae=vae,scheduler=scheduler)",
    "W,H,NF,FPS=864,480,33,30",
    "def make(path,ship_x,sun_x,warm=False):",
    "    sky=(202,170,132) if warm else (132,190,224); sea=(37,94,124) if warm else (28,105,145)",
    "    im=Image.new('RGB',(W,H),sky); d=ImageDraw.Draw(im); d.rectangle((0,270,W,H),fill=sea)",
    "    d.ellipse((sun_x-28,62,sun_x+28,118),fill=(247,204,92))",
    "    d.polygon([(ship_x-64,340),(ship_x+70,340),(ship_x+38,378),(ship_x-50,378)],fill=(33,31,29))",
    "    d.line((ship_x,340,ship_x,205),fill=(28,25,22),width=7)",
    "    d.polygon([(ship_x+4,214),(ship_x+4,330),(ship_x+86,330)],fill=(236,229,206))",
    "    d.polygon([(ship_x-5,228),(ship_x-5,324),(ship_x-62,324)],fill=(220,214,194))",
    "    for y in (410,440,466): d.arc((20,y-18,W-20,y+14),0,180,fill=(172,215,228),width=3)",
    "    im.save(path); return im",
    "sp=WORK/'start.png'; ep=WORK/'end.png'; start=make(sp,220,120,False); end=make(ep,640,735,True)",
    "conds=[LTXVideoCondition(image=start,frame_index=0),LTXVideoCondition(image=end,frame_index=NF-1)]",
    "prompt='A continuous cinematic ocean shot. The same small sailing ship travels smoothly from left to right as waves move naturally and sails respond to wind. The sky warms toward sunset. Preserve one ship, one horizon and coherent perspective; no cuts.'",
    "neg='flicker, duplicate ship, disappearing ship, sudden cut, warped hull, extra sails, text, watermark, jitter'",
    "kw=dict(prompt=prompt,negative_prompt=neg,width=W,height=H,num_frames=NF,guidance_scale=1.0,decode_timestep=0.05,decode_noise_scale=0.025,image_cond_noise_scale=0.025,generator=torch.Generator(device='cuda:0').manual_seed(42),output_type='latent',conditions=conds)",
    "params=set(inspect.signature(pipe.__call__).parameters.keys())",
    "if 'timesteps' in params: kw['timesteps']=[1000,993,987,981,975,909,725]",
    "else: kw['num_inference_steps']=7",
    "if 'tone_map_compression_ratio' in params: kw['tone_map_compression_ratio']=0.6",
    "print('ND_LTX_STAGE=generate')",
    "t0=time.time(); latents=pipe(**kw).frames; gen_s=time.time()-t0",
    "lm=pipe.vae.latents_mean.view(1,-1,1,1,1).to(latents.device,latents.dtype); ls=pipe.vae.latents_std.view(1,-1,1,1,1).to(latents.device,latents.dtype)",
    "latents=latents*ls+lm; pipe.vae.to('cuda:1'); latents=latents.to('cuda:1',pipe.vae.dtype)",
    "temb=torch.tensor([0.05],device='cuda:1',dtype=pipe.vae.dtype)",
    "print('ND_LTX_STAGE=decode')",
    "with torch.no_grad(): decoded=pipe.vae.decode(latents,temb,return_dict=False)[0]",
    "decoded=decoded.squeeze(0).permute(1,2,3,0); decoded=((decoded.float()+1.0)/2.0).clamp(0,1); arr=(decoded*255).to(torch.uint8).cpu().numpy()",
    "frames=[Image.fromarray(arr[i]) for i in range(arr.shape[0])]",
    "outp=WORK/'result.mp4'; imageio.mimsave(str(outp),[np.array(f) for f in frames],fps=FPS,codec='libx264',quality=7)",
    "frames[0].save(WORK/'output_first.png'); frames[-1].save(WORK/'output_last.png')",
    "def mae(a,b):",
    "    a=np.array(a.resize((W,H))).astype(np.float32); b=np.array(b.resize((W,H))).astype(np.float32); return float(np.mean(np.abs(a-b)))",
    "mfs=mae(frames[0],start); mfe=mae(frames[0],end); mle=mae(frames[-1],end); mls=mae(frames[-1],start)",
    "sha=hashlib.sha256(outp.read_bytes()).hexdigest()",
    "receipt={'ok':True,'pipeline':'LTXConditionPipeline','dataset_source':'damnyadav/ltxv13b-distilled-cache','width':W,'height':H,'frames':len(frames),'fps':FPS,'duration_seconds':len(frames)/FPS,'generation_seconds':round(gen_s,3),'size_bytes':outp.stat().st_size,'sha256':sha,'first_to_start_mae':mfs,'first_to_end_mae':mfe,'last_to_end_mae':mle,'last_to_start_mae':mls,'endpoint_order_pass':bool(mfs<mfe and mle<mls),'gpu_names':[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}",
    "(WORK/'result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')",
    "print('ND_LTX_F2L_JSON='+json.dumps(receipt,separators=(',',':'),sort_keys=True))"
  ].join('\n');
  const save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{
    slug:fullSlug,newTitle:'ND LTX First Last Qualification',text:script,language:'python',kernelType:'script',
    datasetDataSources:[datasetSource],kernelDataSources:[],competitionDataSources:[],categoryIds:[],modelDataSources:[],
    isPrivate:true,enableGpu:true,enableTpu:false,enableInternet:true,sessionTimeoutSeconds:3600,machineShape:'NvidiaTeslaT4'
  });
  const version=Number(save?.versionNumber||save?.version_number||0);
  if(!version || save?.error || (save?.invalidDatasetSources||save?.invalid_dataset_sources||[]).length){
    throw new Error('kaggle_ltx_f2l_save_failed: '+JSON.stringify({error:save?.error||null,version,invalid_dataset_sources:save?.invalidDatasetSources||save?.invalid_dataset_sources||[]}));
  }
  const versionLabel='v'+version;
  let lastStatus=null,failureMessage=null;
  const deadline=Date.now()+55*60*1000;
  while(Date.now()<deadline){
    const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug,versionLabel});
    lastStatus=st?.status; failureMessage=st?.failureMessage||st?.failure_message||null;
    if(kaggleStatusTerminal(lastStatus)) break;
    await new Promise(r=>setTimeout(r,10000));
  }
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:slug,versionLabel,pageSize:100});
  if(!kaggleStatusTerminal(lastStatus)) throw new Error('kaggle_ltx_f2l_timeout status='+String(lastStatus));
  const stx=String(lastStatus??'').toUpperCase();
  if(stx==='3'||stx.includes('ERROR')) throw new Error('kaggle_ltx_f2l_failed: '+String(failureMessage||'')+' log_tail='+String(out?.log||'').slice(-12000));
  const payload=extractKaggleJsonMarker(out?.log||'','ND_LTX_F2L_JSON=','kaggle_ltx_f2l_payload_unparseable');
  const files=Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||null,url:x?.url||null})).filter(x=>x.name):[];
  const result={state:'PASS',username,ref:fullSlug+'/'+version,version,provider_status:lastStatus,output_files:files,qualification:payload};
  console.log(JSON.stringify({event:'ND_KAGGLE_LTX_F2L',...result}));
  return result;
}


async function kaggleLtxCopyQualifiedOutputToDrive(){
  const enabled=String(process.env.ND_KAGGLE_LTX_DRIVE_COPY_ON_START||'false').trim().toLowerCase()==='true';
  if(!enabled) return {state:'SKIPPED'};
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN});
  if(!intro?.active||!intro?.username) throw new Error('kaggle_ltx_drive_copy_auth_failed');
  const username=String(intro.username);
  const kernelSlug='nd-ltx-first-last-qualification';
  const version=2;
  const versionLabel='v2';
  const parentId='1Qe6zqqZZzAohSt96_z4vkTcNAcGIThPh';
  const expectedSha='223008af6ff0035ecb61619765cb0efb7b0670a35ce75c3256db1e07617022a1';
  const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{
    userName:username,kernelSlug,versionLabel,pageSize:100
  });
  const files=Array.isArray(out?.files)?out.files:[];
  const findFile=name=>files.find(x=>(x?.fileName||x?.name||x?.path)===name);
  const mp4=findFile('result.mp4');
  const receipt=findFile('result.json');
  if(!mp4?.url) throw new Error('kaggle_ltx_drive_copy_result_mp4_missing');
  const videoRes=await fetch(mp4.url);
  if(!videoRes.ok) throw new Error('kaggle_ltx_drive_copy_download_http_'+videoRes.status);
  const video=Buffer.from(await videoRes.arrayBuffer());
  const sha=crypto.createHash('sha256').update(video).digest('hex');
  if(sha!==expectedSha) throw new Error('kaggle_ltx_drive_copy_sha_mismatch '+sha);
  if(video.length!==156579) throw new Error('kaggle_ltx_drive_copy_size_mismatch '+video.length);
  const driveResult=await authContext.run({user:true},async()=>{
    const created=await multipartCreate(
      'nd-ltx-first-last-qualification-v2.mp4',
      'video/mp4',
      parentId,
      video
    );
    const readback=await metadata(created.id);
    let receiptCreated=null;
    if(receipt?.url){
      const rr=await fetch(receipt.url);
      if(rr.ok){
        const rb=Buffer.from(await rr.arrayBuffer());
        receiptCreated=await multipartCreate(
          'nd-ltx-first-last-qualification-v2.json',
          'application/json',
          parentId,
          rb
        );
      }
    }
    return {created,readback,receipt_created:receiptCreated};
  });
  if(String(driveResult?.readback?.size||'')!==String(video.length)) throw new Error('drive_copy_readback_size_mismatch');
  if(driveResult?.readback?.mimeType!=='video/mp4') throw new Error('drive_copy_readback_mime_mismatch');
  const result={
    state:'PASS',
    kaggle_ref:username+'/'+kernelSlug+'/'+version,
    sha256:sha,
    size_bytes:video.length,
    drive:{
      id:driveResult.created.id,
      name:driveResult.readback.name,
      mime_type:driveResult.readback.mimeType,
      size:Number(driveResult.readback.size||0),
      parent_id:(driveResult.readback.parents||[])[0]||null,
      url:driveResult.readback.webViewLink||null,
      receipt_id:driveResult.receipt_created?.id||null
    }
  };
  console.log(JSON.stringify({event:'ND_KAGGLE_LTX_DRIVE_COPY',...result}));
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


async function remoteKaggleOutputToDrive(args={}){
  const rawUrl=String(args.url||'').trim();
  const name=String(args.name||'').trim();
  const mimeType=String(args.mime_type||'application/octet-stream').trim();
  const parentId=String(args.parent_id||'').trim();
  if(!rawUrl||!name||!parentId) throw new Error('url, name and parent_id required');
  let remote;
  try{remote=new URL(rawUrl);}catch{throw new Error('invalid remote url');}
  if(remote.protocol!=='https:' || remote.hostname!=='www.kaggleusercontent.com') throw new Error('remote host not allowed');
  if(!['video/mp4','application/json'].includes(mimeType)) throw new Error('remote mime type not allowed');
  return authContext.run({user:true},async()=>{
    await requireMcpParent(parentId);
    const escapedName=name.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
    const escapedParent=parentId.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
    const q=new URLSearchParams({
      q:"name = '"+escapedName+"' and '"+escapedParent+"' in parents and trashed = false",
      pageSize:'10',
      spaces:'drive',
      fields:'files(id,name,mimeType,size,parents,webViewLink,modifiedTime)'
    });
    const existing=await gjson('https://www.googleapis.com/drive/v3/files?'+q.toString());
    const found=(existing.files||[])[0]||null;
    if(found){
      const rb=await metadata(found.id);
      return {reused:true,created:false,file:rb};
    }
    const res=await fetch(remote);
    if(!res.ok) throw new Error('remote download HTTP '+res.status);
    const declared=Number(res.headers.get('content-length')||0);
    if(declared>150*1024*1024) throw new Error('remote file exceeds 150 MB');
    const buf=Buffer.from(await res.arrayBuffer());
    if(buf.length>150*1024*1024) throw new Error('remote file exceeds 150 MB');
    const created=await multipartCreate(name,mimeType,parentId,buf);
    const rb=await metadata(created.id);
    return {reused:false,created:true,file:rb};
  });
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
  if (req.method === 'POST' && req.url === '/internal/kaggle-ltx/import-output') {
    if (!safeEqual(req.headers['x-nd-bridge-key'], BRIDGE_KEY)) return json(res,401,{ok:false,error:'unauthorized'});
    const chunks=[]; for await(const ch of req) chunks.push(ch);
    let body={};
    try{body=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}
    catch{return json(res,400,{ok:false,error:'invalid_json'});}
    try{
      const result=await remoteKaggleOutputToDrive(body);
      return json(res,200,{ok:true,result});
    }catch(e){
      return json(res,502,{ok:false,error:String(e?.message||e).slice(0,1200)});
    }
  }
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
  {
    const readVersion=Number(process.env.ND_KAGGLE_GPU_PROBE_READ_VERSION||0);
    if(KAGGLE_API_TOKEN && readVersion>0) setTimeout(()=>kaggleGpuProbeReadback(readVersion).catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_GPU_PROBE_READBACK',state:'FAIL',version:readVersion,error:String(e?.message||e).slice(0,900)}))),7000);
  }
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_WANGP_BOOTSTRAP_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleWanGPBootstrap().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_WANGP_BOOTSTRAP',state:'FAIL',error:String(e?.message||e).slice(0,7800)}))),10000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_WANGP_I2V_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleWanGPI2VQualification().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_WANGP_I2V',state:'FAIL',error:String(e?.message||e).slice(0,12000)}))),12000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_WANGP_DISK_FIT_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleWanGPDiskFit().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_WANGP_DISK_FIT',state:'FAIL',error:String(e?.message||e).slice(0,12000)}))),14000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_LTX_MOUNT_PROBE_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleLtxMountProbe().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_LTX_MOUNT_PROBE',state:'FAIL',error:String(e?.message||e).slice(0,12000)}))),16000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_LTX_CACHE_PROBE_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleLtxCacheProbe().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_LTX_CACHE_PROBE',state:'FAIL',error:String(e?.message||e).slice(0,12000)}))),18000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_LTX_F2L_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleLtxFirstLastQualification().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_LTX_F2L',state:'FAIL',error:String(e?.message||e).slice(0,16000)}))),20000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_LTX_DRIVE_COPY_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleLtxCopyQualifiedOutputToDrive().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_LTX_DRIVE_COPY',state:'FAIL',error:String(e?.message||e).slice(0,12000)}))),22000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_SDCPP_FLF_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleSdCppFLFQualification().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_SDCPP_FLF',state:'FAIL',error:String(e?.message||e).slice(0,14000)}))),16000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_WANGP_GENERATE_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleWanGPGeneration().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_WANGP_GENERATION',state:'FAIL',error:String(e?.message||e).slice(0,14000)}))),12000);
  if(KAGGLE_API_TOKEN && String(process.env.ND_KAGGLE_WAN21_CACHE_ON_START||'false').trim().toLowerCase()==='true') setTimeout(()=>kaggleWan21Cache().catch(e=>console.error(JSON.stringify({event:'ND_KAGGLE_WAN21_CACHE',state:'FAIL',error:String(e?.message||e).slice(0,12000)}))),14000);
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
// ND_KAGGLE_LTX_F2L_TRIGGER_20260926