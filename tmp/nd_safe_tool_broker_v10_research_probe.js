const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d519ae887c5d7a972b9dc676eef58c964cd6c6b0/tmp/nd_safe_tool_broker_v9_father_comment.js";
let outer=await (await fetch(BASE)).text();
const finalizer="const encoded=Buffer.from(patched).toString('base64');";
if(!outer.includes(finalizer))throw new Error("v10 research-probe finalizer marker missing");
const inject=String.raw`
const researchProbeCode="setTimeout(async()=>{\\n  try{\\n    const args={idempotency_key:'startup:research-save-v10',content:'ND Father Workspace research-save qualification probe. Non-authoritative test artifact; safe to retain.',title:'Research Save Qualification Probe',actor:'vk_ai_assistant',sender_vk_id:'SELFTEST',gateway_version:'broker-v10-research-probe',provider:'selftest',actual_model:'none',source_refs:['startup-selftest']};\\n    const r=await invokeTool('sandbox_research_save','',args);\\n    const rr=await invokeTool('sandbox_read','',{artifact_id:r.artifact_id});\\n    const ok=!!(r&&r.ok&&r.read_back_verified&&rr&&rr.ok&&rr.artifact_id===r.artifact_id&&rr.content===args.content&&rr.authority==='NON_AUTHORITATIVE_SANDBOX');\\n    console.log('ND_FATHER_RESEARCH_SANDBOX_SELF_PROBE',JSON.stringify({ok,artifact_id:r&&r.artifact_id,status:r&&r.status,version:r&&r.version,read_back_verified:!!(r&&r.read_back_verified),authority:rr&&rr.authority}));\\n  }catch(e){console.error('ND_FATHER_RESEARCH_SANDBOX_SELF_PROBE',JSON.stringify({ok:false,error:String(e).slice(0,500)}));}\\n},9000);";
patched=patched.replace(serveMarker,serveMarker+'\\n'+researchProbeCode);
`;
outer=outer.replace(finalizer,inject+"\n"+finalizer);
await import("data:text/javascript;base64,"+Buffer.from(outer).toString("base64"));
