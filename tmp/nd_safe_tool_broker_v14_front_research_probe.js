import { Buffer } from "node:buffer";
const SRC="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js";
let s=await (await fetch(SRC)).text();
const marker='await import("data:text/javascript;base64,"+Buffer.from(outer).toString("base64"));';
if(!s.includes(marker))throw new Error("v14 import marker missing");
const researchPatch=String.raw`
const researchProbeCode="setTimeout(async()=>{\\n  try{\\n    const args={idempotency_key:'startup:research-save-v14',content:'ND Father Workspace research-save qualification probe. Non-authoritative test artifact; safe to retain.',title:'Research Save Qualification Probe',actor:'vk_ai_assistant',sender_vk_id:'SELFTEST',gateway_version:'broker-v14-research-probe',provider:'selftest',actual_model:'none',source_refs:['startup-selftest']};\\n    const r=await invokeTool('sandbox_research_save','',args);\\n    const rr=await invokeTool('sandbox_read','',{artifact_id:r.artifact_id});\\n    const ok=!!(r&&r.ok&&r.read_back_verified&&rr&&rr.ok&&rr.artifact_id===r.artifact_id&&rr.content===args.content&&rr.authority==='NON_AUTHORITATIVE_SANDBOX');\\n    console.log('ND_FATHER_RESEARCH_SANDBOX_SELF_PROBE',JSON.stringify({ok,artifact_id:r&&r.artifact_id,status:r&&r.status,version:r&&r.version,read_back_verified:!!(r&&r.read_back_verified),authority:rr&&rr.authority}));\\n  }catch(e){console.error('ND_FATHER_RESEARCH_SANDBOX_SELF_PROBE',JSON.stringify({ok:false,error:String(e).slice(0,500)}));}\\n},9000);";
patched += '\\n' + researchProbeCode + '\\n';
`;
const add='const researchPatch='+JSON.stringify(researchPatch)+';\nouter=outer.replace(finalizer,researchPatch+"\\n"+finalizer);\n';
s=s.replace(marker,add+marker);
await import("data:text/javascript;base64,"+Buffer.from(s).toString("base64"));
