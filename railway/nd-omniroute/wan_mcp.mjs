import { Client, handle_file } from '@gradio/client';

const DEFAULT_SPACE = process.env.ND_WAN_DEFAULT_SPACE || 'Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom';
const HF_TOKEN = String(process.env.HF_TOKEN || '').trim();
const DEFAULT_LTX_SPACE = String(process.env.ND_LTX_PRIMARY_SPACE || 'DeepRat/LTX-Video-ZeroGPU-Optimized').trim();
const DEFAULT_LTX_RESERVES = String(process.env.ND_LTX_RESERVE_SPACES || 'Lightricks/ltx-video-distilled')
  .split(',').map(x => x.trim()).filter(Boolean);
const LTX_I2V_PRIMARY_SPACE = String(process.env.ND_LTX_I2V_PRIMARY_SPACE || 'DeepRat/LTX-Video-ZeroGPU-Optimized').trim();
const LTX_KEYFRAME_PRIMARY_SPACE = String(process.env.ND_LTX_KEYFRAME_PRIMARY_SPACE || 'Imosu/LTX-2.3-turboX').trim();
const LTX_KEYFRAME_RESERVES = String(process.env.ND_LTX_KEYFRAME_RESERVE_SPACES || 'techfreakworm/LTX2.3-Studio,linoyts/ltx-2-first-last-frame')
  .split(',').map(x => x.trim()).filter(Boolean);

function configuredLtxSpaces(){
  return [...new Set([DEFAULT_LTX_SPACE, LTX_I2V_PRIMARY_SPACE, LTX_KEYFRAME_PRIMARY_SPACE, ...DEFAULT_LTX_RESERVES, ...LTX_KEYFRAME_RESERVES].filter(Boolean))];
}

function json(res,status,obj){
  const raw=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{'content-type':'application/json','content-length':raw.length,'cache-control':'no-store'});
  res.end(raw);
}
function errorText(e){return String(e?.stack||e?.message||e).slice(0,4000);}

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
  if(spaceId !== 'Imosu/LTX-2.3-turboX'){
    throw new Error('No semantic keyframe adapter is qualified for this Space yet; use ltx_call_space_raw after capability readback.');
  }
  const start=String(args.start_image_url||'').trim();
  const end=String(args.end_image_url||'').trim();
  if(!start || !end) throw new Error('start_image_url and end_image_url required');
  const duration=Math.max(1,Math.min(6,Number(args.duration_seconds??2)));
  const width=Number(args.width??512);
  const height=Number(args.height??512);
  const app=await Client.connect(spaceId,connectOptions());
  const payload={
    first_frame:handle_file(start),
    end_frame:handle_file(end),
    prompt:String(args.prompt||'Smooth continuous cinematic motion from the first keyframe to the last keyframe, preserving subject identity and scene coherence.'),
    duration,
    generation_mode:'Interpolate',
    enhance_prompt:Boolean(args.enhance_prompt??false),
    seed:Number(args.seed??42),
    randomize_seed:Boolean(args.randomize_seed??false),
    height,
    width,
    audio_path:null
  };
  const result=await app.predict('/generate_video',payload);
  const normalized={space_id:spaceId,api_name:'/generate_video',...normalizeResult(result)};
  return {...normalized,video_ref:findVideoRef(normalized.data),semantic_mode:'first_last_keyframe_interpolation'};
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
    name:'ltx_generate_keyframes',
    description:'Generate a free LTX first-to-last-keyframe interpolation video through the qualified LTX 2.3 ZeroGPU adapter. Intended for storyboard segment animation.',
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

function toolResult(value){
  return {content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value,isError:false};
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
        if(name==='ltx_generate_keyframes') result=await ltxGenerateKeyframes(args);
        else if(name==='ltx_list_routes') result={
          primary:DEFAULT_LTX_SPACE,
          i2v:{primary:LTX_I2V_PRIMARY_SPACE,reserves:DEFAULT_LTX_RESERVES},
          keyframe:{primary:LTX_KEYFRAME_PRIMARY_SPACE,reserves:LTX_KEYFRAME_RESERVES},
          all:configuredLtxSpaces(),
          state:'CONFIGURED / VERIFY_AT_USE'
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
  const base={ok:true,mode:'full',primary_space:DEFAULT_LTX_SPACE,i2v_primary_space:LTX_I2V_PRIMARY_SPACE,keyframe_primary_space:LTX_KEYFRAME_PRIMARY_SPACE,reserve_spaces:DEFAULT_LTX_RESERVES,keyframe_reserve_spaces:LTX_KEYFRAME_RESERVES,selected_space:selected,hf_token_configured:!!HF_TOKEN,tools:TOOLS.filter(x=>x.name.startsWith('ltx_')).map(x=>x.name)};
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
