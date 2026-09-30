import crypto from 'node:crypto';

const GITHUB_PAT=String(process.env.ND_GITHUB_PAT||'').trim();
const STORYBOARD_REPO=String(process.env.ND_STORYBOARD_REPO||'namelessdhamma/namelessdhamma.github.io').trim();
const STORYBOARD_WORKFLOW=String(process.env.ND_STORYBOARD_WORKFLOW||'nd-storyboard-render.yml').trim();
const STORYBOARD_BRANCH=String(process.env.ND_STORYBOARD_CONTROL_BRANCH||'main').trim();
const STORYBOARD_MCP_TOKEN=String(process.env.ND_STORYBOARD_MCP_PATH_TOKEN||'').trim();
const STORYBOARD_PUBLIC_BASE=String(process.env.ND_STORYBOARD_PUBLIC_BASE||'https://nd-external-intelligence-production.up.railway.app').replace(/\/$/,'');
const CONTROL_MAX_BYTES=Number(process.env.ND_STORYBOARD_CONTROL_MAX_BYTES||4*1024*1024);
const RESULT_MAX_BYTES=Number(process.env.ND_STORYBOARD_RESULT_MAX_BYTES||150*1024*1024);

const timeout=(name,fallback)=>{
  const n=Number(process.env[name]||fallback);
  return Number.isFinite(n)&&n>0?n:fallback;
};
const SUBMIT_TIMEOUT=timeout('ND_STORYBOARD_SUBMIT_TIMEOUT_MS',20000);
const STATUS_TIMEOUT=timeout('ND_STORYBOARD_STATUS_TIMEOUT_MS',15000);
const RESULT_TIMEOUT=timeout('ND_STORYBOARD_RESULT_TIMEOUT_MS',15000);
const RECONCILE_TIMEOUT=timeout('ND_STORYBOARD_RECONCILE_TIMEOUT_MS',15000);
const DOWNLOAD_TIMEOUT=timeout('ND_STORYBOARD_DOWNLOAD_TIMEOUT_MS',60000);

function errText(e){return String(e?.message||e||'error').slice(0,1800);}
function json(res,status,obj){const raw=Buffer.from(JSON.stringify(obj));res.writeHead(status,{'content-type':'application/json','content-length':raw.length,'cache-control':'no-store'});return res.end(raw);}
function toolResult(value){return {content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value,isError:false};}
function sha256(s){return crypto.createHash('sha256').update(s).digest('hex');}

function controlError(label,ms,cause){
  const e=new Error(label+' control deadline '+ms+'ms');
  e.code='CONTROL_DEADLINE';e.timeout_ms=ms;e.cause=cause;return e;
}
async function withDeadline(label,ms,fn){
  const controller=new AbortController();
  let fired=false;
  const timer=setTimeout(()=>{fired=true;controller.abort(new Error(label+' deadline'));},ms);
  const started=Date.now();
  const ctx={signal:controller.signal,remainingMs:()=>Math.max(0,ms-(Date.now()-started)),isDeadline:()=>fired||controller.signal.aborted};
  try{return await fn(ctx);}
  catch(e){if(ctx.isDeadline()||e?.name==='AbortError')throw controlError(label,ms,e);throw e;}
  finally{clearTimeout(timer);}
}
async function readBoundedBytes(response,ctx,maxBytes,label){
  const declared=Number(response.headers.get('content-length')||0);
  if(declared>maxBytes)throw new Error(label+' exceeds byte limit');
  if(!response.body?.getReader){
    const b=Buffer.from(await response.arrayBuffer());
    if(b.length>maxBytes)throw new Error(label+' exceeds byte limit');
    return b;
  }
  const reader=response.body.getReader();const chunks=[];let total=0;
  while(true){
    if(ctx.signal.aborted)throw controlError(label,0,ctx.signal.reason);
    const p=await reader.read();
    if(p.done)break;
    const b=Buffer.from(p.value);total+=b.length;
    if(total>maxBytes){try{await reader.cancel('byte_limit')}catch{};throw new Error(label+' exceeds byte limit');}
    chunks.push(b);
  }
  return Buffer.concat(chunks,total);
}
class GithubHttpError extends Error{
  constructor(status,data){super('GitHub API '+status+': '+JSON.stringify(data).slice(0,1200));this.status=status;this.data=data;}
}
async function githubJson(path,{method='GET',body,ctx,allow404=false}={}){
  if(!GITHUB_PAT)throw new Error('ND_GITHUB_PAT is not configured');
  const res=await fetch('https://api.github.com'+path,{
    method,
    headers:{
      accept:'application/vnd.github+json',
      authorization:'Bearer '+GITHUB_PAT,
      'x-github-api-version':'2022-11-28',
      ...(body?{'content-type':'application/json'}:{})
    },
    body:body?JSON.stringify(body):undefined,
    signal:ctx?.signal
  });
  if(allow404&&res.status===404)return null;
  const raw=await readBoundedBytes(res,ctx,CONTROL_MAX_BYTES,'storyboard github response');
  const txt=raw.toString('utf8');let data={};
  try{data=txt?JSON.parse(txt):{};}catch{data={raw:txt.slice(0,4000)};}
  if(!res.ok)throw new GithubHttpError(res.status,data);
  return data;
}

export function normalizeStoryboardManifest(args={}){
  const frames=Array.isArray(args.frames)?args.frames:[];
  if(frames.length<2||frames.length>40)throw new Error('frames must contain 2..40 items');
  return {
    width:Number(args.width??640),
    height:Number(args.height??360),
    fps:Number(args.fps??24),
    default_duration:Number(args.default_duration??1.4),
    transition_duration:Number(args.transition_duration??0.30),
    frames:frames.map((f,i)=>{
      const url=String(f?.url||'').trim();
      if(!/^https?:\/\//i.test(url))throw new Error('frame '+i+' requires http(s) url');
      return {url,duration:Number(f?.duration??args.default_duration??1.4),motion:String(f?.motion||'slow_push_in'),transition:String(f?.transition||'fade')};
    })
  };
}
export function storyboardEffect(args={}){
  const manifest=normalizeStoryboardManifest(args);
  const idem=String(args.idempotency_key||'').trim();
  const material=JSON.stringify({version:1,manifest,idempotency_key:idem||null});
  const digest=sha256(material);
  return {
    manifest,
    effect_id:'storyboard:'+digest,
    effect_token:digest,
    request_id:'sb-r'+digest.slice(0,20),
    request_path:'.nd-control/storyboard/requests/'+digest+'.json',
    idempotency_key:idem||null
  };
}
function parseEffectId(effectId){
  const m=String(effectId||'').trim().match(/^storyboard:([a-f0-9]{64})$/i);
  if(!m)throw new Error('valid storyboard effect_id required');
  const digest=m[1].toLowerCase();
  return {effect_id:'storyboard:'+digest,effect_token:digest,request_id:'sb-r'+digest.slice(0,20),request_path:'.nd-control/storyboard/requests/'+digest+'.json'};
}
async function readRequest(effect,ctx){
  const encoded=effect.request_path.split('/').map(encodeURIComponent).join('/');
  const x=await githubJson('/repos/'+STORYBOARD_REPO+'/contents/'+encoded+'?ref='+encodeURIComponent(STORYBOARD_BRANCH),{ctx,allow404:true});
  if(!x)return null;
  let record=null;
  try{record=JSON.parse(Buffer.from(String(x.content||'').replace(/\s+/g,''),'base64').toString('utf8'));}catch{}
  return {blob_sha:x.sha||null,html_url:x.html_url||null,record};
}
async function statusWithContext(requestId,ctx){
  const id=String(requestId||'').trim();
  if(!/^sb-[a-z0-9-]+$/i.test(id))throw new Error('valid request_id required');
  const runs=await githubJson('/repos/'+STORYBOARD_REPO+'/actions/workflows/'+encodeURIComponent(STORYBOARD_WORKFLOW)+'/runs?per_page=100',{ctx});
  const list=Array.isArray(runs?.workflow_runs)?runs.workflow_runs:[];
  const title='ND Storyboard '+id;
  const run=list.find(r=>String(r?.display_title||'')===title)||list.find(r=>String(r?.display_title||'').includes(id));
  if(!run)return {ok:true,state:'SUBMITTED_NOT_YET_VISIBLE',request_id:id,runtime_profile:'DURABLE_ASYNC',nonblocking:true};
  let artifact=null;
  if(run.status==='completed'){
    const arts=await githubJson('/repos/'+STORYBOARD_REPO+'/actions/runs/'+run.id+'/artifacts',{ctx});
    const arr=Array.isArray(arts?.artifacts)?arts.artifacts:[];
    artifact=arr.find(a=>a?.name==='nd-storyboard-'+id)||arr[0]||null;
  }
  return {
    ok:run.conclusion!=='failure',request_id:id,
    state:run.status==='completed'?(run.conclusion==='success'?'COMPLETED':'FAILED'):String(run.status||'UNKNOWN').toUpperCase(),
    conclusion:run.conclusion||null,run_id:run.id,run_url:run.html_url,
    artifact:artifact?{id:artifact.id,name:artifact.name,size_in_bytes:artifact.size_in_bytes,expired:artifact.expired,archive_download_api_url:artifact.archive_download_url}:null,
    runtime_profile:'DURABLE_ASYNC',nonblocking:true
  };
}
export async function storyboardRenderStatus(args={}){
  return withDeadline('storyboard.status',STATUS_TIMEOUT,ctx=>statusWithContext(args.request_id,ctx));
}
export async function storyboardRenderReconcile(args={}){
  const effect=args.effect_id?parseEffectId(args.effect_id):parseEffectId('storyboard:'+String(args.effect_token||''));
  return withDeadline('storyboard.reconcile',RECONCILE_TIMEOUT,async ctx=>{
    const req=await readRequest(effect,ctx);
    if(!req)return {ok:false,state:'OUTCOME_UNKNOWN',outcome_state:'OUTCOME_UNKNOWN',...effect,safe_to_resubmit:false,nonblocking:true};
    const st=await statusWithContext(effect.request_id,ctx);
    return {ok:true,...effect,reconciled:true,request_record_ref:req.html_url||effect.request_path,...st,safe_to_resubmit:false,nonblocking:true};
  });
}
export async function storyboardRenderSubmit(args={}){
  const effect=storyboardEffect(args);
  let mutationStarted=false;
  try{
    return await withDeadline('storyboard.submit',SUBMIT_TIMEOUT,async ctx=>{
      const existing=await readRequest(effect,ctx);
      if(existing){
        const st=await statusWithContext(effect.request_id,ctx);
        return {ok:true,...effect,reused_existing:true,request_record_ref:existing.html_url||effect.request_path,...st,safe_to_resubmit:false,nonblocking:true};
      }
      const record={schema:'nd-storyboard-request-v2',version:1,request_id:effect.request_id,effect_id:effect.effect_id,effect_token:effect.effect_token,idempotency_key:effect.idempotency_key,manifest:effect.manifest};
      const encoded=effect.request_path.split('/').map(encodeURIComponent).join('/');
      let created;
      try{
        mutationStarted=true;
        created=await githubJson('/repos/'+STORYBOARD_REPO+'/contents/'+encoded,{
          method:'PUT',ctx,
          body:{message:effect.request_id,content:Buffer.from(JSON.stringify(record,null,2)+'\n').toString('base64'),branch:STORYBOARD_BRANCH}
        });
      }catch(e){
        if(e?.status===422){
          const now=await readRequest(effect,ctx);
          if(now){
            const st=await statusWithContext(effect.request_id,ctx);
            return {ok:true,...effect,reused_existing:true,request_record_ref:now.html_url||effect.request_path,...st,safe_to_resubmit:false,nonblocking:true};
          }
        }
        if(e?.name==='AbortError'||e instanceof TypeError){
          return {ok:false,state:'SUBMIT_AMBIGUOUS',outcome_state:'OUTCOME_UNKNOWN',...effect,safe_to_resubmit:false,reconcile_required:true,nonblocking:true,error:errText(e)};
        }
        throw e;
      }
      return {
        ok:true,state:'SUBMITTED',...effect,
        request_record_ref:created?.content?.html_url||effect.request_path,
        control_commit_sha:created?.commit?.sha||null,
        route:'public_github_actions_ffmpeg_storyboard_v2',cost_policy:'FREE_ONLY',
        runtime_profile:'DURABLE_ASYNC',safe_to_resubmit:false,nonblocking:true
      };
    });
  }catch(e){
    if(e?.code==='CONTROL_DEADLINE'){
      return mutationStarted
        ? {ok:false,state:'SUBMIT_AMBIGUOUS',outcome_state:'OUTCOME_UNKNOWN',...effect,safe_to_resubmit:false,reconcile_required:true,runtime_profile:'DURABLE_ASYNC',nonblocking:true,error:errText(e)}
        : {ok:false,state:'CONTROL_DEADLINE',outcome_state:'NO_MUTATION_CONFIRMED',...effect,safe_to_resubmit:false,runtime_profile:'DURABLE_ASYNC',nonblocking:true,error:errText(e)};
    }
    throw e;
  }
}
export async function storyboardRenderResult(args={}){
  const requestId=String(args.request_id||'').trim();
  return withDeadline('storyboard.result',RESULT_TIMEOUT,async ctx=>{
    const st=await statusWithContext(requestId,ctx);
    if(st.state!=='COMPLETED'||!st.artifact?.id)return {ok:false,request_id:requestId,state:st.state,status:st,result_mode:'PROVIDER_REFERENCE',nonblocking:true};
    if(st.artifact.expired)return {ok:false,request_id:requestId,state:'RESULT_EXPIRED',status:st,result_mode:'PROVIDER_REFERENCE',nonblocking:true};
    const base=STORYBOARD_PUBLIC_BASE+'/storyboard-result/'+encodeURIComponent(STORYBOARD_MCP_TOKEN)+'/'+encodeURIComponent(requestId);
    return {
      ok:true,request_id:requestId,state:'READY',mp4_url:base+'.mp4',receipt_url:base+'.json',
      artifact:st.artifact,run_id:st.run_id,run_url:st.run_url,
      result_mode:'PROVIDER_REFERENCE',runtime_profile:'DURABLE_ASYNC',nonblocking:true
    };
  });
}
export async function storyboardResultBytes(requestId){
  const id=String(requestId||'').trim();
  return withDeadline('storyboard.download',DOWNLOAD_TIMEOUT,async ctx=>{
    const st=await statusWithContext(id,ctx);
    if(st.state!=='COMPLETED'||!st.artifact?.id)return {status:st,mp4:null,receipt:null};
    if(st.artifact.expired)throw new Error('storyboard artifact expired');
    if(Number(st.artifact.size_in_bytes||0)>RESULT_MAX_BYTES+4*1024*1024)throw new Error('storyboard artifact exceeds result proxy limit');
    const res=await fetch('https://api.github.com/repos/'+STORYBOARD_REPO+'/actions/artifacts/'+st.artifact.id+'/zip',{
      headers:{accept:'application/vnd.github+json',authorization:'Bearer '+GITHUB_PAT,'x-github-api-version':'2022-11-28'},
      redirect:'follow',signal:ctx.signal
    });
    if(!res.ok)throw new Error('GitHub artifact download '+res.status);
    const zipBytes=await readBoundedBytes(res,ctx,RESULT_MAX_BYTES+4*1024*1024,'storyboard artifact');
    const {default:AdmZip}=await import('adm-zip');
    const zip=new AdmZip(zipBytes);
    const mp4Entry=zip.getEntry('storyboard-output.mp4');
    const receiptEntry=zip.getEntry('storyboard-receipt.json');
    if(!mp4Entry)throw new Error('storyboard-output.mp4 missing from artifact');
    const mp4Size=Number(mp4Entry?.header?.size||0);
    if(mp4Size>RESULT_MAX_BYTES)throw new Error('storyboard MP4 exceeds result proxy limit');
    const receiptSize=Number(receiptEntry?.header?.size||0);
    if(receiptSize>2*1024*1024)throw new Error('storyboard receipt exceeds result proxy limit');
    const mp4=mp4Entry.getData();
    let receipt=null;
    if(receiptEntry){try{receipt=JSON.parse(receiptEntry.getData().toString('utf8'));}catch{}}
    return {status:st,mp4,receipt};
  });
}

const TOOLS=[
  {name:'storyboard_render_submit',description:'DURABLE_ASYNC storyboard submit. Creates one deterministic provider-side request record per logical effect and returns control immediately.',inputSchema:{type:'object',properties:{frames:{type:'array',minItems:2,maxItems:40,items:{type:'object',properties:{url:{type:'string'},duration:{type:'number',minimum:0.2,maximum:20},motion:{type:'string'},transition:{type:'string'}},required:['url'],additionalProperties:false}},width:{type:'integer',default:640},height:{type:'integer',default:360},fps:{type:'integer',default:24},default_duration:{type:'number',default:1.4},transition_duration:{type:'number',default:0.3},idempotency_key:{type:'string',description:'Optional explicit logical-effect key. Omit to deduplicate exact normalized requests.'}},required:['frames'],additionalProperties:false}},
  {name:'storyboard_render_reconcile',description:'Reconcile an ambiguous storyboard submit by stable effect identity. Never creates a new render.',inputSchema:{type:'object',properties:{effect_id:{type:'string'},effect_token:{type:'string'}},anyOf:[{required:['effect_id']},{required:['effect_token']}],additionalProperties:false}},
  {name:'storyboard_render_status',description:'One bounded status read. Never polls in a loop.',inputSchema:{type:'object',properties:{request_id:{type:'string'}},required:['request_id'],additionalProperties:false}},
  {name:'storyboard_render_result',description:'One bounded provider-reference result read. Does not download the artifact in the foreground.',inputSchema:{type:'object',properties:{request_id:{type:'string'}},required:['request_id'],additionalProperties:false}}
];
export function createStoryboardMcpHandler(){
  return async function handle(req,res){
    if(req.method==='GET'){res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});res.write(': nd-storyboard-renderer-mcp durable-async-v2\n\n');return res.end();}
    if(req.method!=='POST')return json(res,405,{ok:false,error:'method_not_allowed'});
    const chunks=[];for await(const ch of req)chunks.push(ch);
    let msg={};try{msg=JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}catch{return json(res,400,{jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}});}
    const id=msg.id??null,method=String(msg.method||'');
    try{
      if(method==='initialize')return json(res,200,{jsonrpc:'2.0',id,result:{protocolVersion:String(msg?.params?.protocolVersion||'2025-06-18'),capabilities:{tools:{}},serverInfo:{name:'ND Storyboard Renderer MCP',version:'2.0.0'}}});
      if(method==='ping')return json(res,200,{jsonrpc:'2.0',id,result:{}});
      if(method.startsWith('notifications/')){res.writeHead(202,{'cache-control':'no-store'});return res.end();}
      if(method==='tools/list')return json(res,200,{jsonrpc:'2.0',id,result:{tools:TOOLS}});
      if(method==='tools/call'){
        const name=String(msg?.params?.name||''),args=(msg?.params?.arguments&&typeof msg.params.arguments==='object')?msg.params.arguments:{};
        let result;
        if(name==='storyboard_render_submit')result=await storyboardRenderSubmit(args);
        else if(name==='storyboard_render_reconcile')result=await storyboardRenderReconcile(args);
        else if(name==='storyboard_render_status')result=await storyboardRenderStatus(args);
        else if(name==='storyboard_render_result')result=await storyboardRenderResult(args);
        else return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Unknown tool'}});
        return json(res,200,{jsonrpc:'2.0',id,result:toolResult(result)});
      }
      return json(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }catch(e){return json(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:errText(e)}],isError:true}});}
  };
}
export async function storyboardHealth(){
  return {
    ok:true,route:'public_github_actions_ffmpeg_storyboard_v2',repository:STORYBOARD_REPO,workflow:STORYBOARD_WORKFLOW,
    cost_policy:'FREE_ONLY',runtime_profile:'DURABLE_ASYNC',nonblocking:true,
    control_contract:{submit_timeout_ms:SUBMIT_TIMEOUT,status_timeout_ms:STATUS_TIMEOUT,result_timeout_ms:RESULT_TIMEOUT,reconcile_timeout_ms:RECONCILE_TIMEOUT,download_timeout_ms:DOWNLOAD_TIMEOUT,ambiguous_submit:'RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT',result_mode:'PROVIDER_REFERENCE'},
    tools:TOOLS.map(x=>x.name)
  };
}
