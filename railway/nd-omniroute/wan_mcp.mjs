import { Client, handle_file } from '@gradio/client';

const DEFAULT_SPACE = process.env.ND_WAN_DEFAULT_SPACE || 'Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom';
const HF_TOKEN = String(process.env.HF_TOKEN || '').trim();
const DEFAULT_LTX_SPACE = String(process.env.ND_LTX_PRIMARY_SPACE || 'DeepRat/LTX-Video-ZeroGPU-Optimized').trim();
const DEFAULT_LTX_RESERVES = String(process.env.ND_LTX_RESERVE_SPACES || 'Lightricks/ltx-video-distilled')
  .split(',').map(x => x.trim()).filter(Boolean);
const LTX_I2V_PRIMARY_SPACE = String(process.env.ND_LTX_I2V_PRIMARY_SPACE || 'DeepRat/LTX-Video-ZeroGPU-Optimized').trim();
const LTX_KEYFRAME_PRIMARY_SPACE = String(process.env.ND_LTX_KEYFRAME_PRIMARY_SPACE || '').trim();
const LTX_KEYFRAME_RESERVES = String(process.env.ND_LTX_KEYFRAME_RESERVE_SPACES || 'techfreakworm/LTX2.3-Studio,linoyts/ltx-2-first-last-frame')
  .split(',').map(x => x.trim()).filter(Boolean);

const GITHUB_PAT = String(process.env.ND_GITHUB_PAT || '').trim();
const LTX_HFJOBS_ENABLED = /^(1|true|yes)$/i.test(String(process.env.ND_LTX_HFJOBS_PAID_ENABLED || 'false').trim());
const LTX_HFJOBS_REPO = 'namelessdhamma/ND-app';
const LTX_HFJOBS_MAX_COST_USD = 0.405;

const STORYBOARD_REPO = 'namelessdhamma/namelessdhamma.github.io';
const STORYBOARD_EVENT = 'nd_storyboard_render';

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

async function ltxGenerateKeyframes(args={}){
  const spaceId=String(args.space_id||LTX_KEYFRAME_PRIMARY_SPACE).trim();
  if(!spaceId){
    throw new Error('No live-qualified LTX keyframe primary is configured. Use ltx_get_capabilities + ltx_call_space_raw on a readable candidate until a real first/last MP4 qualification passes.');
  }
  throw new Error('No live-qualified semantic keyframe adapter is currently adopted for '+spaceId+'. Use ltx_get_capabilities + ltx_call_space_raw after schema readback.');
}

export async function ltxKeyframeSelftest(){
  const start='https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/diffusers/cat.png';
  const end='https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png';
  const started=Date.now();
  try{
    const result=await ltxGenerateKeyframes({
      start_image_url:start,
      end_image_url:end,
      prompt:'Smooth continuous transition between two keyframes, stable camera, coherent motion.',
      duration_seconds:2,
      width:512,
      height:512,
      seed:42,
      randomize_seed:false,
      enhance_prompt:false
    });
    return {ok:!!result.video_ref,elapsed_ms:Date.now()-started,space_id:LTX_KEYFRAME_PRIMARY_SPACE,video_ref:result.video_ref||null,result};
  }catch(e){
    return {ok:false,elapsed_ms:Date.now()-started,space_id:LTX_KEYFRAME_PRIMARY_SPACE,error:errorText(e)};
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
    description:'Fail-closed semantic first/last-frame entrypoint. It becomes executable only after a real keyframe Space passes live qualification; until then use ltx_get_capabilities + ltx_call_space_raw.',
    inputSchema:{
      type:'object',
      properties:{
        start_image_url:{type:'string'},
        end_image_url:{type:'string'},
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
    rife_state:'NOT_YET_QUALIFIED',
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
        else if(name==='ltx_generate_quota_independent') result=await ltxQuotaIndependentSubmit(args);
        else if(name==='ltx_quota_independent_status') result=await ltxQuotaIndependentStatus(args);
        else if(name==='ltx_generate_keyframes') result=await ltxGenerateKeyframes(args);
        else if(name==='ltx_list_routes') result={
          primary:DEFAULT_LTX_SPACE,
          i2v:{primary:LTX_I2V_PRIMARY_SPACE,reserves:DEFAULT_LTX_RESERVES},
          keyframe:{primary:LTX_KEYFRAME_PRIMARY_SPACE||null,reserves:LTX_KEYFRAME_RESERVES,state:LTX_KEYFRAME_PRIMARY_SPACE?'VERIFY_AT_USE':'NO_LIVE_QUALIFIED_PRIMARY'},
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
  const base={ok:true,mode:'full',primary_space:DEFAULT_LTX_SPACE,i2v_primary_space:LTX_I2V_PRIMARY_SPACE,keyframe_primary_space:LTX_KEYFRAME_PRIMARY_SPACE,reserve_spaces:DEFAULT_LTX_RESERVES,keyframe_reserve_spaces:LTX_KEYFRAME_RESERVES,selected_space:selected,hf_token_configured:!!HF_TOKEN,quota_independent:{enabled:LTX_HFJOBS_ENABLED,route:'HF Jobs / L4 / LTX 2B distilled FP8',daily_generation_quota:'NONE',estimated_max_cost_usd:LTX_HFJOBS_MAX_COST_USD},tools:TOOLS.filter(x=>x.name.startsWith('ltx_')).map(x=>x.name)};
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
