import {health,submit,reconcile,status,result} from "../lib/ltx-core.js";

const PATH_TOKEN=String(process.env.ND_LTX_MCP_PATH_TOKEN||"").trim();
const TOOLS=[
  {name:"ltx_shot",description:"NORMALIZED FREE_ONLY ND video shot interface. Start with start_image_url + end_image_url; defaults to the QUALIFIED_DIRECT_1024 production profile (1024x576, ~2 s, seed 42). Continue with request_id only; returns QUEUED/RUNNING or READY with video_ref. Transport/provider internals are hidden.",inputSchema:{type:"object",properties:{request_id:{type:"string"},start_image_url:{type:"string"},end_image_url:{type:"string"},prompt:{type:"string"},negative_prompt:{type:"string"},duration_seconds:{type:"number",minimum:1,maximum:6,default:2},seed:{type:"integer",default:42},idempotency_key:{type:"string"}},oneOf:[{required:["request_id"],not:{anyOf:[{required:["start_image_url"]},{required:["end_image_url"]}]}},{required:["start_image_url","end_image_url"],not:{required:["request_id"]}}],additionalProperties:false}},
  {name:"ltx_generate_keyframes",description:"NONBLOCKING FREE_ONLY Kaggle LTX 2B first/last-frame submit. Successful submit ends the call; never wait or poll in a loop.",inputSchema:{type:"object",properties:{start_image_url:{type:"string"},end_image_url:{type:"string"},prompt:{type:"string"},negative_prompt:{type:"string"},duration_seconds:{type:"number",minimum:1,maximum:6,default:2},width:{type:"integer",default:512},height:{type:"integer",default:288},seed:{type:"integer",default:42},idempotency_key:{type:"string"}},required:["start_image_url","end_image_url"],additionalProperties:false}},
  {name:"ltx_keyframe_reconcile",description:"Reconcile an ambiguous submit by stable effect identity. Never resubmits the effect.",inputSchema:{type:"object",properties:{effect_id:{type:"string"},effect_token:{type:"string"}},anyOf:[{required:["effect_id"]},{required:["effect_token"]}],additionalProperties:false}},
  {name:"ltx_keyframe_status",description:"One bounded Kaggle job state read under an end-to-end control deadline. Never wait or poll in a loop.",inputSchema:{type:"object",properties:{request_id:{type:"string"}},required:["request_id"],additionalProperties:false}},
  {name:"ltx_keyframe_result",description:"One bounded Kaggle result-reference read under an end-to-end control deadline. Returns fresh provider URLs when READY.",inputSchema:{type:"object",properties:{request_id:{type:"string"}},required:["request_id"],additionalProperties:false}}
];

function clean(e){
  let x=String(e?.message||e||"error");
  for(const v of [PATH_TOKEN,process.env.KAGGLE_API_TOKEN,process.env.ND_LTX_INPUT_TOKEN]) if(v) x=x.split(v).join("[REDACTED]");
  return x.slice(0,1800);
}

function simpleEnvelope(out={}){
  const state=String(out?.state||"UNKNOWN");
  const normalized={
    ok:out?.ok!==false,
    capability:"nd-kaggle-ltx",
    profile:"QUALIFIED_DIRECT_1024",
    state,
    cost_policy:"FREE_ONLY",
    nonblocking:true
  };
  for(const key of ["request_id","effect_id","outcome_state","next_check_after_seconds","failure_message","error"]){
    if(out?.[key]!==undefined&&out?.[key]!==null) normalized[key]=out[key];
  }
  if(out?.video_ref) normalized.video_ref=out.video_ref;
  else if(out?.provider_video_url) normalized.video_ref=out.provider_video_url;
  if(["SUBMITTED","QUEUED","RUNNING","PROVIDER_VISIBILITY_PENDING"].includes(state)) normalized.caller_action="CONTINUE_SAME_SHOT_LATER";
  else if(state==="READY") normalized.caller_action="REVIEW_VIDEO";
  else if(state==="SUBMIT_AMBIGUOUS"||state==="OUTCOME_UNKNOWN"||out?.outcome_state==="OUTCOME_UNKNOWN") normalized.caller_action="RECONCILE_SAME_EFFECT";
  else if(state==="CAPACITY_BLOCKED") normalized.caller_action="RETRY_SAME_CAPABILITY_LATER";
  return normalized;
}

async function simpleShot(args={}){
  const requestId=String(args.request_id||"").trim();
  if(requestId){
    const st=await status({request_id:requestId});
    if(st?.state==="COMPLETED") return simpleEnvelope(await result({request_id:requestId}));
    return simpleEnvelope(st);
  }
  return simpleEnvelope(await submit({
    start_image_url:args.start_image_url,
    end_image_url:args.end_image_url,
    prompt:args.prompt,
    negative_prompt:args.negative_prompt,
    duration_seconds:args.duration_seconds??2,
    width:1024,
    height:576,
    quality_mode:"direct",
    seed:args.seed??42,
    idempotency_key:args.idempotency_key
  }));
}


export default async function handler(req,res){
  const supplied=String(req.query?.token||"").trim();
  if(!PATH_TOKEN||supplied!==PATH_TOKEN) return res.status(404).json({ok:false,error:"not_found"});
  if(req.method==="GET") return res.status(200).json({...health(),service:"nd-kaggle-ltx-reserve",provider:"vercel",tools:TOOLS.map(x=>x.name)});
  if(req.method!=="POST"){res.setHeader("Allow","GET, POST");return res.status(405).end()}
  let msg=req.body||{};
  if(typeof msg==="string"){try{msg=JSON.parse(msg||"{}")}catch{return res.status(400).json({jsonrpc:"2.0",id:null,error:{code:-32700,message:"Parse error"}})}}
  const id=msg.id??null, method=String(msg.method||"");
  if(method==="notifications/initialized") return res.status(204).end();
  if(method==="initialize") return res.status(200).json({jsonrpc:"2.0",id,result:{protocolVersion:String(msg.params?.protocolVersion||"2025-06-18"),capabilities:{tools:{}},serverInfo:{name:"ND Kaggle LTX Vercel Reserve",version:"1.2.0"},instructions:"FREE_ONLY normalized ND Kaggle LTX surface. Prefer ltx_shot for normal use; advanced operations are recovery/diagnostic only. Submit returns control; ambiguous submit must reconcile the same effect before any resubmit."}});
  if(method==="ping") return res.status(200).json({jsonrpc:"2.0",id,result:{}});
  if(method==="tools/list") return res.status(200).json({jsonrpc:"2.0",id,result:{tools:TOOLS}});
  if(method==="tools/call"){
    try{
      const name=String(msg.params?.name||""), a=msg.params?.arguments||{};
      let out;
      if(name==="ltx_shot") out=await simpleShot(a);\n      else if(name==="ltx_generate_keyframes") out=await submit(a);
      else if(name==="ltx_keyframe_reconcile") out=await reconcile(a);
      else if(name==="ltx_keyframe_status") out=await status(a);
      else if(name==="ltx_keyframe_result") out=await result(a);
      else return res.status(200).json({jsonrpc:"2.0",id,error:{code:-32601,message:"Unknown tool"}});
      return res.status(200).json({jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:false}});
    }catch(e){
      const out={ok:false,state:e?.code==="CONTROL_DEADLINE"?"CONTROL_DEADLINE":"ERROR",outcome_state:e?.outcome_state||null,error_code:e?.code||null,timeout_ms:e?.timeout_ms||null,error:clean(e),nonblocking:true};
      return res.status(200).json({jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:true}});
    }
  }
  return res.status(200).json({jsonrpc:"2.0",id,error:{code:-32601,message:"Method not found"}});
}
