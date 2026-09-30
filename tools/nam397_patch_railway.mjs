import fs from 'node:fs';

const path='railway/nd-omniroute/wan_mcp.mjs';
let s=fs.readFileSync(path,'utf8');

function rb(src,aMark,bMark,repl){
  const a=src.indexOf(aMark); if(a<0) throw new Error('missing '+aMark);
  const b=src.indexOf(bMark,a+aMark.length); if(b<0) throw new Error('missing '+bMark);
  return src.slice(0,a)+repl+'\n\n'+src.slice(b);
}
function once(oldText,newText,label){
  const n=s.split(oldText).length-1;
  if(n!==1) throw new Error(label+' expected once, got '+n);
  s=s.replace(oldText,newText);
}

once("import crypto from 'node:crypto';","import crypto from 'node:crypto';\nimport {ltxControlTimeout,withLtxControlDeadline,ltxFetch,ltxReadBoundedBytes,ltxReadBoundedText,LTX_CONTROL_TEXT_MAX_BYTES,LTX_CONTROL_INPUT_MAX_BYTES} from './ltx_control.mjs';",'control import');

s=rb(s,'async function kaggleRpc(','async function kaggleKernelOutputUrl',`async function kaggleRpc(service,method,body={},ctx=null){
  if(!KAGGLE_API_TOKEN) throw new Error('KAGGLE_API_TOKEN is not configured');
  const res=await ltxFetch('https://api.kaggle.com/v1/'+service+'/'+method,{
    method:'POST',
    headers:{authorization:'Bearer '+KAGGLE_API_TOKEN,accept:'application/json','content-type':'application/json','user-agent':'nd-ltx-kaggle/1.1'},
    body:JSON.stringify(body)
  },ctx);
  const txt=await ltxReadBoundedText(res,ctx,LTX_CONTROL_TEXT_MAX_BYTES,'Kaggle RPC response');
  let data={}; try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,1200)};}
  if(!res.ok){
    const raw=data?.message??data?.error??data??txt; let detail;
    try{detail=typeof raw==='string'?raw:JSON.stringify(raw);}catch{detail=String(raw);}
    const e=new Error('Kaggle HTTP '+res.status+': '+String(detail).slice(0,1800));
    e.status=res.status; e.code='PROVIDER_HTTP_ERROR'; throw e;
  }
  return data;
}`);

s=rb(s,'async function kaggleKernelOutputUrl(','function kaggleDurationSeconds',`async function kaggleKernelOutputUrl(ownerSlug,kernelSlug,filePath,versionNumber=0,ctx=null){
  if(!KAGGLE_API_TOKEN) throw new Error('KAGGLE_API_TOKEN is not configured');
  const res=await ltxFetch('https://api.kaggle.com/v1/kernels.KernelsApiService/DownloadKernelOutput',{
    method:'POST',redirect:'manual',
    headers:{authorization:'Bearer '+KAGGLE_API_TOKEN,accept:'application/json','content-type':'application/json','user-agent':'nd-ltx-kaggle/1.1'},
    body:JSON.stringify({ownerSlug,kernelSlug,filePath,versionNumber})
  },ctx);
  if(res.status>=300&&res.status<400){const loc=res.headers.get('location'); if(loc) return loc;}
  const txt=await ltxReadBoundedText(res,ctx,LTX_CONTROL_TEXT_MAX_BYTES,'Kaggle output response');
  let data={}; try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt};}
  if(!res.ok){const e=new Error('Kaggle DownloadKernelOutput HTTP '+res.status+': '+String(data?.message||data?.error||txt).slice(0,1200));e.status=res.status;e.code='PROVIDER_HTTP_ERROR';throw e;}
  const url=data?.url||data?.redirectUrl||data?.redirect_url||data?.downloadUrl||data?.download_url||null;
  if(url) return String(url);
  const raw=String(txt||'').trim(); if(/^https?:\\/\\//i.test(raw)) return raw;
  throw new Error('Kaggle DownloadKernelOutput returned no URL for '+filePath);
}`);

s=rb(s,'async function kaggleLtxIdentity(','function kaggleLtxRequestRef',`async function kaggleLtxIdentity(ctx=null){
  const intro=await kaggleRpc('security.OAuthService','IntrospectToken',{token:KAGGLE_API_TOKEN},ctx);
  if(!intro?.active||!intro?.username) throw new Error('Kaggle token inactive');
  const username=String(intro.username);
  if(KAGGLE_USERNAME_SLUG&&username!==KAGGLE_USERNAME_SLUG) throw new Error('Kaggle username mismatch');
  return {username};
}
async function kaggleLtxPreflight(ctx=null,knownUsername=null){
  const username=knownUsername||((await kaggleLtxIdentity(ctx)).username);
  const quota=await kaggleRpc('kernels.KernelsApiService','GetAcceleratorQuotaStatistics',{},ctx);
  const g=quota?.gpuQuota||quota?.gpu_quota||{};
  const used=kaggleDurationSeconds(g?.timeUsed??g?.time_used),reserved=kaggleDurationSeconds(g?.timeReserved??g?.time_reserved),total=kaggleDurationSeconds(g?.totalTimeAllowed??g?.total_time_allowed);
  const remaining=Math.max(0,total-used);
  if(total<=0) throw new Error('FREE_ONLY_BLOCKED: Kaggle GPU quota unavailable');
  if(remaining<15*60) throw new Error('FREE_ONLY_BLOCKED: less than 15 minutes Kaggle GPU quota remains');
  return {username,gpu:{used_hours:Number((used/3600).toFixed(3)),reserved_hours:Number((reserved/3600).toFixed(3)),total_hours:Number((total/3600).toFixed(3)),remaining_hours:Number((remaining/3600).toFixed(3)),refresh_at:quota?.quotaRefreshTime||quota?.quota_refresh_time||null}};
}`);

s=rb(s,'async function resolveKaggleLtx2bKernel(','function ltx2bInputFingerprint',`async function resolveKaggleLtx2bKernel(username,ref,ctx=null){
  let lastError=null;
  for(const slug of [ref.kernel_slug,ref.direct_kernel_slug]){
    try{
      const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug:slug},ctx);
      return {slug,st};
    }catch(e){lastError=e;if(ctx?.isDeadline()) throw e;}
  }
  throw lastError||new Error('Kaggle LTX2B kernel resolution failed');
}`);

s=rb(s,'async function ltx2bExistingRequest(','function newKaggleLtxKernelRef',`async function ltx2bExistingRequest(username,kernelSlug,ctx=null){
  const listed=await kaggleRpc('kernels.KernelsApiService','ListKernels',{user:username,search:kernelSlug,pageSize:50},ctx);
  const kernels=Array.isArray(listed?.kernels)?listed.kernels:[],owner=username.toLowerCase(),target=kernelSlug.toLowerCase();
  const exact=kernels.filter(k=>{const slug=String(k?.slug||'').replace(/^.*\\//,'').toLowerCase(),ref=String(k?.ref||'').toLowerCase(),author=String(k?.author||'').toLowerCase();return ref===owner+'/'+target||(slug===target&&(!author||author===owner||author==='savva savchenko'));});
  if(exact.length===0)return null;
  if(exact.length>1)throw new Error('Kaggle idempotency conflict: multiple exact kernels for '+kernelSlug);
  const version=Number(exact[0]?.currentVersionNumber??exact[0]?.current_version_number??0);
  if(!version)throw new Error('Kaggle idempotency conflict: existing kernel has no current version');
  const st=await kaggleRpc('kernels.KernelsApiService','GetKernelSessionStatus',{userName:username,kernelSlug,versionLabel:'v'+version},ctx);
  return {version,state:kaggleState(st?.status),provider_status:st?.status??null};
}
function ltx2bEffectTokenFromId(effectId){
  const m=String(effectId||'').trim().match(/^ltx2b:([a-f0-9]{64})$/i);
  if(!m)throw new Error('valid ltx2b effect_id required');
  return 'r'+m[1].slice(0,12)+'-'+m[1].slice(12,16);
}`);

s=rb(s,'async function prepareLtxKernelInput(','async function ltxKaggleWan2gpSubmit',`async function prepareLtxKernelInput(value,label,ctx=null){
  const ref=String(value||'').trim(),m=ref.match(/^drive:([A-Za-z0-9_-]{10,200})$/i);
  if(!m)return {url:resolveLtxInputRef(ref),base64:null,content_type:null,size_bytes:null};
  if(!LTX_INPUT_TOKEN)throw new Error('ND_LTX_INPUT_TOKEN is not configured');
  const publicUrl=LTX_PUBLIC_BASE+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  const local='http://127.0.0.1:'+OUTER_PORT+'/ltx-input/'+LTX_INPUT_TOKEN+'/'+encodeURIComponent(m[1]);
  const res=await ltxFetch(local,{},ctx);
  if(!res.ok)throw new Error(label+' Drive input read failed HTTP '+res.status);
  const ct=String(res.headers.get('content-type')||'');
  if(!ct.startsWith('image/'))throw new Error(label+' Drive input is not an image');
  const declared=Number(res.headers.get('content-length')||0);
  if(declared>LTX_CONTROL_INPUT_MAX_BYTES)throw new Error(label+' Drive input size invalid');
  const bytes=await ltxReadBoundedBytes(res,ctx,LTX_CONTROL_INPUT_MAX_BYTES,label+' Drive input');
  if(!bytes.length)throw new Error(label+' Drive input body size invalid');
  if(declared>0&&declared!==bytes.length)throw new Error(label+' Drive input content-length mismatch');
  return {url:publicUrl,base64:bytes.toString('base64'),content_type:ct,size_bytes:bytes.length};
}`);

s=rb(s,'async function ltxKaggle2bSubmit(','async function ltxKaggle2bStatus',`async function ltxKaggle2bSubmit(args={},opts={}){
  return withLtxControlDeadline('ltx.primary.submit',ltxControlTimeout('submit'),async ctx=>{
    const [startInput,endInput]=await Promise.all([prepareLtxKernelInput(args.start_image_url,'start',ctx),prepareLtxKernelInput(args.end_image_url,'end',ctx)]);
    const {username}=await kaggleLtxIdentity(ctx),direct=opts.direct===true;
    const seed=args.randomize_seed===true?Math.floor(Math.random()*2147483647):Number(args.seed??42),prompt=String(args.prompt||'').trim(),negativePrompt=String(args.negative_prompt||'').trim()||undefined,durationSeconds=Number(args.duration_seconds??2),width=Number(args.width??512),height=Number(args.height??288);
    const effect=ltx2bEffectRef({startInput,endInput,prompt,negativePrompt,durationSeconds,width,height,seed,direct,idempotencyKey:args.idempotency_key});
    const prior=await ltx2bExistingRequest(username,effect.kernel_slug,ctx);
    if(prior)return {ok:true,state:prior.state,reused_existing:true,request_id:'k2b-'+effect.token+'-v'+prior.version,effect_id:effect.effect_id,effect_token:effect.token,provider_ref:username+'/'+effect.kernel_slug+'/'+prior.version,provider_status:prior.provider_status,route:direct?'kaggle_ltx2b_direct_f2l':'kaggle_ltx2b_wan2gp_f2l',worker_mode:direct?'DIRECT_LTX':'WAN2GP_WRAPPER',cost_policy:'FREE_ONLY',gpu_quota:null,seed,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK'};
    const preflight=await kaggleLtxPreflight(ctx,username);
    const workerUrl=direct?'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx2b_direct_worker.py':'https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/railway/nd-omniroute/kaggle_ltx2b_wan2gp_worker.py';
    const build=useInline=>{const request={start_image_url:useInline?undefined:(startInput.url||undefined),end_image_url:useInline?undefined:(endInput.url||undefined),start_image_base64:useInline?(startInput.base64||undefined):undefined,end_image_base64:useInline?(endInput.base64||undefined):undefined,prompt,negative_prompt:negativePrompt,duration_seconds:durationSeconds,width,height,seed},reqB64=Buffer.from(JSON.stringify(request),'utf8').toString('base64');return ['import base64,sys,urllib.request','from pathlib import Path',"request_path=Path('/kaggle/working/nd-ltx2b-request.json')","request_path.write_bytes(base64.b64decode('"+reqB64+"'))","worker=Path('/kaggle/working/kaggle_ltx2b_wan2gp_worker.py')","req=urllib.request.Request('"+workerUrl+"',headers={'User-Agent':'nd-kaggle-ltx2b/1.0'})","worker.write_bytes(urllib.request.urlopen(req,timeout=120).read())","sys.argv=['kaggle_ltx2b_wan2gp_worker.py',str(request_path)]","exec(compile(worker.read_text(encoding='utf-8'),'kaggle_ltx2b_wan2gp_worker.py','exec'),{'__name__':'__main__'})"].join('\\n');};
    const inline=!!(startInput.base64||endInput.base64);let inputTransport=inline?'inline_base64':'url',script=build(inline);
    if(Buffer.byteLength(script,'utf8')>=900000&&inline){inputTransport='url_fallback';script=build(false);}
    if(Buffer.byteLength(script,'utf8')>=900000)throw new Error('Kaggle LTX2B kernel source preflight exceeds 900 KB');
    const cacheSources=[preflight.username+'/nd-ltx-2b-distilled-cache',preflight.username+'/nd-ltx2b-load-probe-fixed'];
    let save;
    try{save=await kaggleRpc('kernels.KernelsApiService','SaveKernel',{slug:preflight.username+'/'+effect.kernel_slug,newTitle:'ND LTX2B '+effect.token,text:script,language:'python',kernelType:'script',datasetDataSources:[],kernelDataSources:cacheSources,competitionDataSources:[],categoryIds:[],modelDataSources:[],isPrivate:true,enableGpu:true,enableTpu:false,enableInternet:true,kernelExecutionType:'SaveAndRunAll',machineShape:'NvidiaTeslaT4',sessionTimeoutSeconds:3600},ctx);}
    catch(e){
      const msg=String(e?.message||e);
      if(/429|RESOURCE_EXHAUSTED|maximum.*GPU|batch GPU session|capacity|quota/i.test(msg))return {ok:false,state:'CAPACITY_BLOCKED',effect_id:effect.effect_id,effect_token:effect.token,route:direct?'kaggle_ltx2b_direct_f2l':'kaggle_ltx2b_wan2gp_f2l',cost_policy:'FREE_ONLY',retry_after_seconds:60,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK_AND_RETRY_LATER',error:msg.slice(0,1200)};
      if(e?.code==='CONTROL_DEADLINE'||ctx.isDeadline())return {ok:false,state:'SUBMIT_AMBIGUOUS',outcome_state:'OUTCOME_UNKNOWN',effect_id:effect.effect_id,effect_token:effect.token,kernel_slug:effect.kernel_slug,route:direct?'kaggle_ltx2b_direct_f2l':'kaggle_ltx2b_wan2gp_f2l',cost_policy:'FREE_ONLY',retry_after_seconds:30,nonblocking:true,caller_action:'RECONCILE_SAME_EFFECT_LATER_DO_NOT_RESUBMIT',error:msg.slice(0,1200)};
      const st=Number(e?.status||0);
      if(!st||st===408||st===409||st>=500){try{if(ctx.remainingMs()>750){const found=await ltx2bExistingRequest(username,effect.kernel_slug,ctx);if(found)return {ok:true,state:found.state,reused_existing:true,request_id:'k2b-'+effect.token+'-v'+found.version,effect_id:effect.effect_id,effect_token:effect.token,provider_ref:username+'/'+effect.kernel_slug+'/'+found.version,provider_status:found.provider_status,route:direct?'kaggle_ltx2b_direct_f2l':'kaggle_ltx2b_wan2gp_f2l',worker_mode:direct?'DIRECT_LTX':'WAN2GP_WRAPPER',cost_policy:'FREE_ONLY',gpu_quota:preflight.gpu,seed,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK'};}}catch{}return {ok:false,state:'SUBMIT_AMBIGUOUS',outcome_state:'OUTCOME_UNKNOWN',effect_id:effect.effect_id,effect_token:effect.token,kernel_slug:effect.kernel_slug,route:direct?'kaggle_ltx2b_direct_f2l':'kaggle_ltx2b_wan2gp_f2l',cost_policy:'FREE_ONLY',retry_after_seconds:30,nonblocking:true,caller_action:'RECONCILE_SAME_EFFECT_LATER_DO_NOT_RESUBMIT',error:msg.slice(0,1200)};}
      throw e;
    }
    const invalid=save?.invalidKernelSources||save?.invalid_kernel_sources||[],version=Number(save?.versionNumber||save?.version_number||0);
    if(save?.error||invalid.length)throw new Error('Kaggle LTX2B submit failed '+JSON.stringify({error:save?.error||null,invalid_kernel_sources:invalid}));
    if(!version)throw new Error('Kaggle LTX2B submit returned no version');
    return {ok:true,state:'SUBMITTED',reused_existing:false,request_id:'k2b-'+effect.token+'-v'+version,effect_id:effect.effect_id,effect_token:effect.token,provider_ref:preflight.username+'/'+effect.kernel_slug+'/'+version,route:direct?'kaggle_ltx2b_direct_f2l':'kaggle_ltx2b_wan2gp_f2l',worker_mode:direct?'DIRECT_LTX':'WAN2GP_WRAPPER',cache_source:cacheSources[0],cache_sources:cacheSources,input_transport:inputTransport,input_sizes:{start:startInput.size_bytes||null,end:endInput.size_bytes||null},machine_shape_requested:'NvidiaTeslaT4',cost_policy:'FREE_ONLY',gpu_quota:preflight.gpu,seed,nonblocking:true,caller_action:'CONTINUE_OTHER_USEFUL_WORK'};
  });
}
async function ltxKaggle2bReconcile(args={}){
  return withLtxControlDeadline('ltx.primary.reconcile',ltxControlTimeout('reconcile'),async ctx=>{
    const token=String(args.effect_token||'').trim()||ltx2bEffectTokenFromId(args.effect_id);
    if(!/^r[a-f0-9]{12}-[a-f0-9]{4}$/i.test(token))throw new Error('valid effect_token required');
    const {username}=await kaggleLtxIdentity(ctx),kernelSlug='nd-ltx2b-'+token,found=await ltx2bExistingRequest(username,kernelSlug,ctx);
    if(!found)return {ok:false,state:'OUTCOME_UNKNOWN',outcome_state:'OUTCOME_UNKNOWN',effect_id:String(args.effect_id||'')||null,effect_token:token,kernel_slug:kernelSlug,safe_to_resubmit:false,retry_after_seconds:30,nonblocking:true,caller_action:'RECHECK_SAME_EFFECT_LATER_DO_NOT_RESUBMIT'};
    return {ok:true,state:found.state,reused_existing:true,request_id:'k2b-'+token+'-v'+found.version,effect_id:String(args.effect_id||'')||null,effect_token:token,provider_ref:username+'/'+kernelSlug+'/'+found.version,provider_status:found.provider_status,nonblocking:true,caller_action:'CONTINUE_SAME_EFFECT'};
  });
}`);

s=rb(s,'async function ltxKaggle2bStatus(','async function ltxKaggle2bResult',`async function ltxKaggle2bStatus(args={}){
  return withLtxControlDeadline('ltx.primary.status',ltxControlTimeout('status'),async ctx=>{
    const ref=kaggleLtx2bRequestRef(args.request_id),{username}=await kaggleLtxIdentity(ctx),resolved=await resolveKaggleLtx2bKernel(username,ref,ctx),state=kaggleState(resolved.st?.status);
    let diagnostics=null;
    if(['FAILED','CANCELLED'].includes(state)){try{const out=await kaggleRpc('kernels.KernelsApiService','ListKernelSessionOutput',{userName:username,kernelSlug:resolved.slug,pageSize:100},ctx);diagnostics={files:Array.isArray(out?.files)?out.files.map(x=>({name:x?.fileName||x?.name||x?.path||null,size:x?.fileSize??x?.size??null})).filter(x=>x.name):[],log_tail:String(out?.log||'').slice(-12000)};}catch(e){diagnostics={error:errorText(e)};}}
    return {ok:true,request_id:ref.request_id,state,provider_status:resolved.st?.status??null,failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,provider_ref:username+'/'+resolved.slug+'/'+ref.version,diagnostics,nonblocking:true,control_observed_at:new Date().toISOString(),next_check_after_seconds:state==='QUEUED'?30:(state==='RUNNING'?45:null)};
  });
}`);

s=rb(s,'async function ltxKaggle2bResult(','async function ltxKaggleStatus',`async function ltxKaggle2bResult(args={}){
  return withLtxControlDeadline('ltx.primary.result',ltxControlTimeout('result'),async ctx=>{
    const ref=kaggleLtx2bRequestRef(args.request_id),{username}=await kaggleLtxIdentity(ctx),resolved=await resolveKaggleLtx2bKernel(username,ref,ctx),state=kaggleState(resolved.st?.status);
    if(state!=='COMPLETED')return {ok:false,request_id:ref.request_id,state,provider_status:resolved.st?.status??null,failure_message:resolved.st?.failureMessage||resolved.st?.failure_message||null,nonblocking:true};
    const mp4Url=await kaggleKernelOutputUrl(username,resolved.slug,'result.mp4',ref.version,ctx);
    let receiptUrl=null,receipt_state='READY';try{if(ctx.remainingMs()>500)receiptUrl=await kaggleKernelOutputUrl(username,resolved.slug,'result.json',ref.version,ctx);else receipt_state='DEFERRED_CONTROL_BUDGET';}catch(e){receipt_state=e?.code==='CONTROL_DEADLINE'||ctx.isDeadline()?'DEFERRED_CONTROL_BUDGET':'UNAVAILABLE';}
    return {ok:true,request_id:ref.request_id,state:'READY',route:'kaggle_ltx2b_direct_f2l',provider_ref:username+'/'+resolved.slug+'/'+ref.version,receipt:null,provider_video_url:mp4Url,provider_receipt_url:receiptUrl,receipt_state,stable_video_url:LTX_RESULT_TOKEN?LTX_PUBLIC_BASE+'/ltx-result/'+encodeURIComponent(LTX_RESULT_TOKEN)+'/'+encodeURIComponent(ref.request_id)+'.mp4':null,stable_receipt_url:LTX_RESULT_TOKEN?LTX_PUBLIC_BASE+'/ltx-result/'+encodeURIComponent(LTX_RESULT_TOKEN)+'/'+encodeURIComponent(ref.request_id)+'.json':null,video_ref:mp4Url,drive_video:null,drive_receipt:null,drive_import_error:null,persistence_state:args.persist_to_drive===false?'NOT_REQUESTED':'DEFERRED_SEPARATE_OPERATION',persistence_note:'Generation success is independent from persistence; interactive result read returns provider references only.',result_mode:'PROVIDER_REFERENCE',nonblocking:true};
  });
}`);

once("  {\n    name:'ltx_keyframe_status',\n    description:'Read provider status for a Kaggle LTX first/last-frame generation request.',","  {\n    name:'ltx_keyframe_reconcile',\n    description:'Reconcile an ambiguous Kaggle LTX submit by stable effect identity without resubmitting it.',\n    inputSchema:{type:'object',properties:{effect_id:{type:'string'},effect_token:{type:'string'}},anyOf:[{required:['effect_id']},{required:['effect_token']}],additionalProperties:false}\n  },\n  {\n    name:'ltx_keyframe_status',\n    description:'Read provider status for a Kaggle LTX first/last-frame generation request under a bounded control deadline.',",'broad reconcile tool');

once("  {\n    name:'ltx_keyframe_status',\n    description:'One bounded read of Kaggle job state. Never wait or poll in a loop. If QUEUED/RUNNING, return control immediately and continue other useful work until a later status check is useful.',","  {\n    name:'ltx_keyframe_reconcile',\n    description:'Reconcile an ambiguous submit by stable effect identity. Never creates a new provider job.',\n    inputSchema:{type:'object',properties:{effect_id:{type:'string'},effect_token:{type:'string'}},anyOf:[{required:['effect_id']},{required:['effect_token']}],additionalProperties:false}\n  },\n  {\n    name:'ltx_keyframe_status',\n    description:'One bounded read of Kaggle job state. Never wait or poll in a loop. If QUEUED/RUNNING, return control immediately and continue other useful work until a later status check is useful.',",'prod reconcile tool');

once("serverInfo:{name:'ND Kaggle LTX MCP',version:'1.1.0'}","serverInfo:{name:'ND Kaggle LTX MCP',version:'1.2.0'}",'server version');
once("        if(name==='ltx_generate_keyframes') result=await ltxKaggle2bSubmit(args,{direct:true});\n        else if(name==='ltx_keyframe_status') result=await ltxKaggle2bStatus(args);","        if(name==='ltx_generate_keyframes') result=await ltxKaggle2bSubmit(args,{direct:true});\n        else if(name==='ltx_keyframe_reconcile') result=await ltxKaggle2bReconcile(args);\n        else if(name==='ltx_keyframe_status') result=await ltxKaggle2bStatus(args);",'dedicated dispatch');
once("        else if(name==='ltx_generate_keyframes') result=await ltxGenerateKeyframes(args);\n        else if(name==='ltx_keyframe_status') result=/^k2b-/i.test(String(args.request_id||''))?await ltxKaggle2bStatus(args):await ltxKaggleStatus(args);\n        else if(name==='ltx_keyframe_result') result=/^k2b-/i.test(String(args.request_id||''))?await ltxKaggle2bResult(args):await ltxKaggleResult(args);","        else if(name==='ltx_generate_keyframes') result=await ltxGenerateKeyframes(args);\n        else if(name==='ltx_keyframe_reconcile') result=await ltxKaggle2bReconcile(args);\n        else if(name==='ltx_keyframe_status') result=/^k2b-/i.test(String(args.request_id||''))?await ltxKaggle2bStatus(args):await ltxKaggleStatus(args);\n        else if(name==='ltx_keyframe_result') result=/^k2b-/i.test(String(args.request_id||''))?await ltxKaggle2bResult({...args,persist_to_drive:false}):await ltxKaggleResult(args);",'broad dispatch');

s=rb(s,'export async function ltxResultBytes(','export async function wanHealth',`export async function ltxResultBytes(requestId){
  return withLtxControlDeadline('ltx.result.download',ltxControlTimeout('download'),async ctx=>{
    const id=String(requestId||'').trim();if(!id)throw new Error('ltx result request_id required');
    const result=/^k2b-/i.test(id)?await ltxKaggle2bResult({request_id:id,persist_to_drive:false}):await ltxKaggleResult({request_id:id});
    if(result?.state!=='READY')return {state:result?.state||'UNKNOWN',mp4:null,receipt:result?.receipt||null};
    const remote=String(result?.provider_video_url||result?.video_ref||'').trim();if(!remote)throw new Error('ltx result provider url missing');
    const res=await ltxFetch(remote,{headers:{'user-agent':'nd-external-intelligence/1.1'}},ctx);if(!res.ok)throw new Error('ltx result provider download HTTP '+res.status);
    const mp4=await ltxReadBoundedBytes(res,ctx,150*1024*1024,'ltx result');if(!mp4.length)throw new Error('ltx result provider returned empty body');
    return {state:'READY',mp4,receipt:result?.receipt||null};
  });
}`);

once("const base={ok:true,mode:'production_nonblocking',production_tools:LTX_PRODUCTION_TOOLS.map(x=>x.name),nonblocking_contract:'SUBMIT_RETURNS_IMMEDIATELY / NO_FOREGROUND_POLLING / CONTINUE_OTHER_USEFUL_WORK',","const base={ok:true,mode:'production_nonblocking',runtime_profile:'DURABLE_ASYNC',control_contract:{submit_timeout_ms:ltxControlTimeout('submit'),status_timeout_ms:ltxControlTimeout('status'),result_timeout_ms:ltxControlTimeout('result'),reconcile_timeout_ms:ltxControlTimeout('reconcile'),result_mode:'PROVIDER_REFERENCE',ambiguous_submit:'RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT'},production_tools:LTX_PRODUCTION_TOOLS.map(x=>x.name),nonblocking_contract:'SUBMIT_RETURNS_IMMEDIATELY / NO_FOREGROUND_POLLING / CONTINUE_OTHER_USEFUL_WORK',",'health contract');

for(const req of ["from './ltx_control.mjs'","async function ltxKaggle2bReconcile","name:'ltx_keyframe_reconcile'","runtime_profile:'DURABLE_ASYNC'","result_mode:'PROVIDER_REFERENCE'"]) if(!s.includes(req))throw new Error('missing '+req);
fs.writeFileSync(path,s);
console.log('NAM397_RAILWAY_PATCH=PASS');
