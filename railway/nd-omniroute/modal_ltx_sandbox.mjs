import { ModalClient } from 'modal';

const LTX_COMMIT='4b2d053057623ddd4d0a1d3e9cd28890e9ef487f';
const MODAL_APP='nd-ltx2b-sandbox';
const BASE_IMAGE='pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime';
const REQUEST_PREFIX='modal-sandbox:';
const WORKER="\nimport base64, glob, json, os, pathlib, subprocess, sys, urllib.request\n\nraw=os.environ['ND_LTX_REQUEST_B64']\nreq=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)).decode())\nroot=pathlib.Path('/tmp/nd-ltx')\nsrc=pathlib.Path('/opt/LTX-Video')\nout=root/'outputs'\nmedia=root/'media'\nout.mkdir(parents=True,exist_ok=True)\nmedia.mkdir(parents=True,exist_ok=True)\n\ndef download(url,path):\n    r=urllib.request.Request(url,headers={'User-Agent':'ND-Modal-LTX/1.0'})\n    with urllib.request.urlopen(r,timeout=120) as srcf, open(path,'wb') as dst:\n        total=0\n        while True:\n            chunk=srcf.read(1024*1024)\n            if not chunk:\n                break\n            total+=len(chunk)\n            if total>20*1024*1024:\n                raise RuntimeError('input image exceeds 20 MiB')\n            dst.write(chunk)\n\nstart=media/'start.png'\nend=media/'end.png'\ndownload(req['start_image_url'],start)\ndownload(req['end_image_url'],end)\n\ncmd=[\n    sys.executable,'inference.py',\n    '--prompt',req['prompt'],\n    '--negative_prompt',req['negative_prompt'],\n    '--pipeline_config','configs/ltxv-2b-0.9.8-distilled-fp8.yaml',\n    '--height',str(req['height']),\n    '--width',str(req['width']),\n    '--num_frames',str(req['num_frames']),\n    '--seed',str(req['seed']),\n    '--frame_rate',str(req['frame_rate']),\n    '--output_path',str(out),\n    '--offload_to_cpu','true',\n    '--conditioning_media_paths',str(start),str(end),\n    '--conditioning_start_frames','0',str(req['num_frames']-1),\n    '--conditioning_strengths',str(req['start_strength']),str(req['end_strength']),\n]\nenv=os.environ.copy()\nenv.setdefault('PYTORCH_CUDA_ALLOC_CONF','expandable_segments:True')\nsubprocess.check_call(cmd,cwd=src,env=env)\nfiles=sorted(glob.glob(str(out/'**'/'*.mp4'),recursive=True),key=os.path.getmtime)\nif not files:\n    raise RuntimeError('no mp4 output found')\nvideo=pathlib.Path(files[-1])\ndata=video.read_bytes()\nif not data:\n    raise RuntimeError('empty mp4 output')\nif len(data)>150*1024*1024:\n    raise RuntimeError('mp4 output exceeds 150 MiB')\n(root/'result.mp4').write_bytes(data)\nreceipt={\n    'ok':True,\n    'model':'ltxv-2b-0.9.8-distilled-fp8',\n    'ltx_commit':'4b2d053057623ddd4d0a1d3e9cd28890e9ef487f',\n    'width':req['width'],'height':req['height'],'num_frames':req['num_frames'],\n    'frame_rate':req['frame_rate'],'seed':req['seed'],'bytes':len(data),\n    'endpoint_frame':req['num_frames']-1\n}\n(root/'result.json').write_text(json.dumps(receipt,sort_keys=True),encoding='utf-8')\nprint('ND_MODAL_LTX_DONE='+json.dumps(receipt,sort_keys=True))\n";

function cleanError(e){
  return String(e?.stack||e?.message||e).replace(/https:\/\/[^\s'"]+\/ltx-input\/[^\s'"]+/gi,'[REDACTED_INPUT_URL]').slice(0,6000);
}

function safeRequest(args={}){
  const width=Math.max(256,Math.min(1280,Number(args.width??512)));
  const height=Math.max(256,Math.min(1280,Number(args.height??288)));
  const fps=Math.max(1,Math.min(60,Number(args.frame_rate??24)));
  const duration=Math.max(1,Math.min(6,Number(args.duration_seconds??2)));
  const requested=Math.max(9,Math.round(duration*fps));
  const frames=Math.min(121,1+8*Math.max(1,Math.round((requested-1)/8)));
  return {
    start_image_url:String(args.start_image_url||'').trim(),
    end_image_url:String(args.end_image_url||'').trim(),
    prompt:String(args.prompt||'').trim()||'Smooth cinematic transition between keyframes with natural motion and consistent lighting.',
    negative_prompt:String(args.negative_prompt||'worst quality, inconsistent motion, blurry, jittery, distorted, sudden cut, duplicate subject, text, watermark'),
    width,height,frame_rate:fps,duration_seconds:duration,num_frames:frames,
    seed:Number(args.seed??42),
    start_strength:Number(args.start_strength??1.0),
    end_strength:Number(args.end_strength??0.9)
  };
}

function sandboxIdFromRequest(requestId){
  const raw=String(requestId||'').trim();
  if(!raw.startsWith(REQUEST_PREFIX)) return null;
  const id=raw.slice(REQUEST_PREFIX.length);
  return /^[A-Za-z0-9_-]{6,200}$/.test(id)?id:null;
}

export function modalLtxSandboxConfigured(){
  return !!(String(process.env.MODAL_TOKEN_ID||'').trim() && String(process.env.MODAL_TOKEN_SECRET||'').trim());
}

export async function modalLtxSandboxProbe(){
  if(!modalLtxSandboxConfigured()) return {ok:false,state:'CREDENTIALS_MISSING',provider:'Modal',route:'modal_ltx2b_direct_sandbox'};
  try{
    const modal=new ModalClient();
    await modal.apps.fromName(MODAL_APP,{createIfMissing:true});
    modal.close();
    return {ok:true,state:'AUTHENTICATED',provider:'Modal',route:'modal_ltx2b_direct_sandbox',sdk:'modal-js'};
  }catch(e){
    return {ok:false,state:'AUTH_OR_PROVIDER_ERROR',provider:'Modal',route:'modal_ltx2b_direct_sandbox',error:cleanError(e)};
  }
}

export async function modalLtxSandboxSubmit(args={}){
  if(!modalLtxSandboxConfigured()) throw new Error('Modal credentials are not configured');
  const req=safeRequest(args);
  if(!/^https?:\/\//i.test(req.start_image_url)||!/^https?:\/\//i.test(req.end_image_url)) throw new Error('resolved http(s) start/end image URLs required');

  const modal=new ModalClient();
  try{
    const app=await modal.apps.fromName(MODAL_APP,{createIfMissing:true});
    const image=modal.images.fromRegistry(BASE_IMAGE);
    const encoded=Buffer.from(JSON.stringify(req),'utf8').toString('base64url');
    const workerB64=Buffer.from(WORKER,'utf8').toString('base64');
    const setup=[
      'set -euo pipefail',
      'apt-get update -qq',
      'DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git ffmpeg',
      'rm -rf /var/lib/apt/lists/*',
      'git clone https://github.com/Lightricks/LTX-Video.git /opt/LTX-Video',
      'cd /opt/LTX-Video',
      'git checkout '+LTX_COMMIT,
      "pip install --no-cache-dir -e '.[inference]'",
      'echo "$ND_LTX_WORKER_B64" | base64 -d > /tmp/nd-ltx-worker.py',
      'python /tmp/nd-ltx-worker.py'
    ].join('; ');
    const sb=await modal.sandboxes.create(app,image,{
      gpu:String(process.env.ND_LTX_MODAL_GPU||'T4'),
      timeoutMs:20*60*1000,
      memoryMiB:24576,
      command:['bash','-lc',setup],
      env:{ND_LTX_REQUEST_B64:encoded,ND_LTX_WORKER_B64:workerB64,HF_HOME:'/tmp/hf-cache',TRANSFORMERS_CACHE:'/tmp/hf-cache'}
    });
    const result={
      ok:true,state:'SUBMITTED',provider:'Modal',route:'modal_ltx2b_direct_sandbox',
      request_id:REQUEST_PREFIX+sb.sandboxId,sandbox_id:sb.sandboxId,
      gpu:String(process.env.ND_LTX_MODAL_GPU||'T4'),model:'ltxv-2b-0.9.8-distilled-fp8',cost_policy:'FREE_CREDIT_ONLY',
      width:req.width,height:req.height,num_frames:req.num_frames,frame_rate:req.frame_rate,seed:req.seed
    };
    sb.detach();
    return result;
  }finally{
    modal.close();
  }
}

export async function modalLtxSandboxStatus(args={}){
  const sandboxId=String(args.sandbox_id||sandboxIdFromRequest(args.request_id)||'').trim();
  if(!sandboxId) throw new Error('valid Modal sandbox request_id required');
  const modal=new ModalClient();
  try{
    const sb=await modal.sandboxes.fromId(sandboxId);
    const code=await sb.poll();
    if(code===null) return {ok:true,state:'RUNNING',provider:'Modal',route:'modal_ltx2b_direct_sandbox',request_id:REQUEST_PREFIX+sandboxId,sandbox_id:sandboxId};
    if(code!==0){
      const [stdout,stderr]=await Promise.all([sb.stdout.readText().catch(()=>''),sb.stderr.readText().catch(()=>'')]);
      return {ok:false,state:'FAILED',provider:'Modal',route:'modal_ltx2b_direct_sandbox',request_id:REQUEST_PREFIX+sandboxId,sandbox_id:sandboxId,exit_code:code,stdout_tail:String(stdout).slice(-2500),stderr_tail:cleanError(String(stderr).slice(-3500))};
    }
    const receiptText=await sb.filesystem.readText('/tmp/nd-ltx/result.json').catch(()=>'');
    let receipt=null; try{receipt=receiptText?JSON.parse(receiptText):null;}catch{}
    return {ok:true,state:'COMPLETED',provider:'Modal',route:'modal_ltx2b_direct_sandbox',request_id:REQUEST_PREFIX+sandboxId,sandbox_id:sandboxId,exit_code:code,receipt};
  }finally{
    modal.close();
  }
}

export async function modalLtxSandboxResultBytes(args={}){
  const sandboxId=String(args.sandbox_id||sandboxIdFromRequest(args.request_id)||'').trim();
  if(!sandboxId) throw new Error('valid Modal sandbox request_id required');
  const modal=new ModalClient();
  try{
    const sb=await modal.sandboxes.fromId(sandboxId);
    const code=await sb.poll();
    if(code===null) return {ok:false,state:'RUNNING',request_id:REQUEST_PREFIX+sandboxId,sandbox_id:sandboxId};
    if(code!==0){
      const [stdout,stderr]=await Promise.all([sb.stdout.readText().catch(()=>''),sb.stderr.readText().catch(()=>'')]);
      return {ok:false,state:'FAILED',request_id:REQUEST_PREFIX+sandboxId,sandbox_id:sandboxId,exit_code:code,stdout_tail:String(stdout).slice(-2500),stderr_tail:cleanError(String(stderr).slice(-3500))};
    }
    const [video,receiptText]=await Promise.all([
      sb.filesystem.readBytes('/tmp/nd-ltx/result.mp4'),
      sb.filesystem.readText('/tmp/nd-ltx/result.json')
    ]);
    let receipt=null; try{receipt=JSON.parse(receiptText);}catch{}
    return {ok:true,state:'READY',request_id:REQUEST_PREFIX+sandboxId,sandbox_id:sandboxId,video:Buffer.from(video),receipt};
  }finally{
    modal.close();
  }
}

export async function modalLtxFunctionBootstrapRaw(){
  if(!modalLtxSandboxConfigured()) throw new Error('Modal credentials are not configured');
  const modal=new ModalClient();
  try{
    const app=await modal.apps.fromName('nd-modal-bootstrap',{createIfMissing:true});
    const image=modal.images.fromRegistry('python:3.11-slim');
    const secret=await modal.secrets.fromObject({
      MODAL_TOKEN_ID:String(process.env.MODAL_TOKEN_ID||''),
      MODAL_TOKEN_SECRET:String(process.env.MODAL_TOKEN_SECRET||'')
    });
    const script=[
      'set -euo pipefail',
      "python -m pip install -q --disable-pip-version-check 'modal>=1.5.1'",
      "python - <<'PY'",
      'from urllib.request import urlopen',
      "u='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/modal/nd_ltx2b_app.py'",
      "open('/tmp/nd_ltx2b_app.py','wb').write(urlopen(u,timeout=60).read())",
      'PY',
      "modal deploy /tmp/nd_ltx2b_app.py --name nd-ltx2b-first-last > /tmp/deploy.log 2>&1",
      "modal workspace proxy-tokens create --json > /tmp/proxy.json",
      "python - <<'PY'",
      'import json,re',
      "deploy=open('/tmp/deploy.log','r',encoding='utf-8',errors='replace').read()",
      "urls=re.findall(r'https://[A-Za-z0-9.-]+\\.modal\\.run',deploy)",
      "generate=next((u for u in urls if 'generate' in u),None)",
      "health=next((u for u in urls if 'health' in u),None)",
      "if not generate or not health: raise RuntimeError('Modal endpoint URLs not found')",
      "p=json.load(open('/tmp/proxy.json'))",
      "print('ND_MODAL_BOOTSTRAP='+json.dumps({'generate_url':generate,'health_url':health,'proxy_key':p['Modal-Key'],'proxy_secret':p['Modal-Secret']},separators=(',',':')))",
      'PY'
    ].join('\n');
    const sb=await modal.sandboxes.create(app,image,{
      command:['sh','-lc',script],
      secrets:[secret],
      timeoutMs:20*60*1000,
      memoryMiB:2048
    });
    const code=await sb.wait();
    const [stdout,stderr]=await Promise.all([sb.stdout.readText(),sb.stderr.readText()]);
    if(code!==0) throw new Error('Modal bootstrap failed: '+String(stderr||stdout).slice(-5000));
    const marker='ND_MODAL_BOOTSTRAP=';
    const line=String(stdout||'').split(/\r?\n/).find(x=>x.startsWith(marker));
    if(!line) throw new Error('Modal bootstrap receipt missing');
    const cfg=JSON.parse(line.slice(marker.length));
    if(!cfg.generate_url||!cfg.health_url||!cfg.proxy_key||!cfg.proxy_secret) throw new Error('Modal bootstrap receipt incomplete');
    return cfg;
  }finally{
    modal.close();
  }
}

export function isModalSandboxRequestId(value){
  return !!sandboxIdFromRequest(value);
}
