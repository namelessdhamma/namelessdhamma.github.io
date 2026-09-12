import { Buffer } from "node:buffer";

// ND Safe Tool Broker V13 qualification wrapper.
// Reuses proven V11 front unchanged. Adds only a bounded startup qualification
// for sandbox_research_save followed by exact sandbox_read content verification.
const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js";
let src=await (await fetch(BASE)).text();
const marker='await import("data:text/javascript;base64,"+Buffer.from(outer).toString("base64"));';
if(!src.includes(marker)) throw new Error("V13 V11 import marker missing");

const probe=String.raw`
setTimeout(async()=>{
  const port=String(process.env.PORT||"3000"),auth=process.env.QSTASH_TOKEN||"",base="http://127.0.0.1:"+port;
  async function invoke(tool,args){
    const r=await fetch(base+"/invoke",{method:"POST",headers:{Authorization:"Bearer "+auth,"Content-Type":"application/json","Accept":"application/json","User-Agent":"nd-v13-research-qualifier/1.0"},body:JSON.stringify({tool,query:"",args})});
    const t=await r.text();if(!r.ok)throw new Error("invoke "+tool+" HTTP "+r.status+": "+t.slice(0,500));
    const j=JSON.parse(t);if(j.error)throw new Error("invoke "+tool+": "+String(j.error).slice(0,500));return j.result;
  }
  try{
    if(!auth)throw new Error("QSTASH_TOKEN unavailable");
    const content="Automated ND Father Workspace Research qualification probe. Non-authoritative test artifact; safe to deduplicate.";
    const save=await invoke("sandbox_research_save",{idempotency_key:"startup-v13-research-qualification",content,title:"ND Research qualification probe",actor:"vk_ai_assistant",sender_vk_id:"SELFTEST",gateway_version:"v13-research-qualification",provider:"selftest",actual_model:"none",source_refs:["startup:selftest"]});
    if(!(save&&save.ok&&save.read_back_verified&&save.artifact_id))throw new Error("research save did not verify");
    const read=await invoke("sandbox_read",{artifact_id:save.artifact_id});
    if(!(read&&read.ok&&String(read.content||"")===content))throw new Error("research read-back mismatch");
    console.log("ND_RESEARCH_SANDBOX_SELF_PROBE",JSON.stringify({ok:true,artifact_id:save.artifact_id,status:save.status,version:save.version,deduplicated:!!save.deduplicated,read_back_exact:true,authority:save.authority||null}));
  }catch(e){console.error("ND_RESEARCH_SANDBOX_SELF_PROBE",JSON.stringify({ok:false,error:String(e).slice(0,700)}));}
},12000);
`;
src=src.replace(marker,marker+"\n"+probe);
console.log("ND_SAFE_TOOL_BROKER_V13_RESEARCH_QUALIFICATION_START");
await import("data:text/javascript;base64,"+Buffer.from(src).toString("base64"));
