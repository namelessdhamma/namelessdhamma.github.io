import fs from 'node:fs';

const src=fs.readFileSync(new URL('../wan_mcp.mjs',import.meta.url),'utf8');

function mustHave(s,label){
  if(!src.includes(s)) throw new Error('missing '+label+': '+s);
}

mustHave("const WAN_RUNTIME_PROFILE='OPAQUE_BLOCKING';",'opaque profile');
mustHave("abort_supported:false",'honest abort boundary');
mustHave("provider_reconcile_supported:false",'honest reconcile boundary');
mustHave("interruption_outcome:'OUTCOME_UNKNOWN'",'interruption state');
mustHave("resubmit_policy:'NO_BLIND_RESUBMIT'",'no blind resubmit');
mustHave("boundary_checkpoint:'REQUIRED_BEFORE_CONSEQUENTIAL_OPAQUE_CALL'",'boundary checkpoint');
mustHave("local_stop_remote_cancel:'NOT_EQUIVALENT'",'stop semantics');
mustHave("const WAN_TOOLS=TOOLS.filter(x=>x.name.startsWith('wan_'));",'wan-only surface');
mustHave("description:'OPAQUE_BLOCKING Wan I2V call.",'wan generate declaration');
mustHave("description:'OPAQUE_BLOCKING raw Gradio call.",'raw call declaration');
mustHave("runtime_profile:WAN_RUNTIME_PROFILE",'health profile');
mustHave("tools:WAN_TOOLS.map(x=>x.name)",'health surface');

const start=src.indexOf('export function createWanMcpHandler()');
const end=src.indexOf('export async function ltxResultBytes',start);
if(start<0||end<0) throw new Error('cannot isolate Wan handler');
const handler=src.slice(start,end);
for(const legacy of [
  "name==='ltx_generate_quota_independent'",
  "name==='ltx_generate_keyframes'",
  "name==='ltx_keyframe_status'",
  "name==='ltx_keyframe_result'",
  "name==='ltx_call_space_raw'"
]){
  if(handler.includes(legacy)) throw new Error('legacy LTX bypass remains callable on generic Wan MCP: '+legacy);
}
for(const active of ["name==='wan_get_capabilities'","name==='wan_generate_video'","name==='wan_call_space_raw'"]){
  if(!handler.includes(active)) throw new Error('Wan tool missing from handler: '+active);
}

console.log('WAN_OPAQUE_BOUNDARY=PASS');
console.log('WAN_LEGACY_LTX_BYPASS_CLOSED=PASS');
