import {health,submit,status,result} from "../lib/ltx-core.js";

const PATH_TOKEN=String(process.env.ND_LTX_MCP_PATH_TOKEN||process.env.ND_TELEGRAM_MCP_PATH_TOKEN||"").trim();
const TOOLS=[
  {name:"ltx_generate_keyframes",description:"NONBLOCKING FREE_ONLY Kaggle LTX 2B first/last-frame submit. Successful submit ends the call; never wait or poll in a loop.",inputSchema:{type:"object",properties:{start_image_url:{type:"string"},end_image_url:{type:"string"},prompt:{type:"string"},negative_prompt:{type:"string"},duration_seconds:{type:"number",minimum:1,maximum:6,default:2},width:{type:"integer",default:512},height:{type:"integer",default:288},seed:{type:"integer",default:42},idempotency_key:{type:"string"}},required:["start_image_url","end_image_url"],additionalProperties:false}},
  {name:"ltx_keyframe_status",description:"One bounded Kaggle job state read. Never wait or poll in a loop.",inputSchema:{type:"object",properties:{request_id:{type:"string"}},required:["request_id"],additionalProperties:false}},
  {name:"ltx_keyframe_result",description:"One bounded Kaggle result read. Returns fresh provider URLs when READY.",inputSchema:{type:"object",properties:{request_id:{type:"string"}},required:["request_id"],additionalProperties:false}}
];

function clean(e){
  let x=String(e?.message||e||"error");
  for(const v of [PATH_TOKEN,process.env.KAGGLE_API_TOKEN,process.env.ND_LTX_INPUT_TOKEN]) if(v) x=x.split(v).join("[REDACTED]");
  return x.slice(0,1800);
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
  if(method==="initialize") return res.status(200).json({jsonrpc:"2.0",id,result:{protocolVersion:String(msg.params?.protocolVersion||"2025-06-18"),capabilities:{tools:{}},serverInfo:{name:"ND Kaggle LTX Vercel Reserve",version:"1.0.0"},instructions:"FREE_ONLY nonblocking Kaggle LTX reserve. Submit returns immediately; continue other useful work."}});
  if(method==="ping") return res.status(200).json({jsonrpc:"2.0",id,result:{}});
  if(method==="tools/list") return res.status(200).json({jsonrpc:"2.0",id,result:{tools:TOOLS}});
  if(method==="tools/call"){
    try{
      const name=String(msg.params?.name||""), a=msg.params?.arguments||{};
      let out;
      if(name==="ltx_generate_keyframes") out=await submit(a);
      else if(name==="ltx_keyframe_status") out=await status(a);
      else if(name==="ltx_keyframe_result") out=await result(a);
      else return res.status(200).json({jsonrpc:"2.0",id,error:{code:-32601,message:"Unknown tool"}});
      return res.status(200).json({jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:false}});
    }catch(e){
      const out={ok:false,error:clean(e),nonblocking:true};
      return res.status(200).json({jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:true}});
    }
  }
  return res.status(200).json({jsonrpc:"2.0",id,error:{code:-32601,message:"Method not found"}});
}
