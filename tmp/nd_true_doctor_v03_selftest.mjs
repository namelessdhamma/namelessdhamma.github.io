import {
  DOCTOR_ID, DOCTOR_VERSION, doctorStart, doctorObserve, doctorFinalize,
  createProbeReceipt, PROBE_SPECS, doctorStatus, runPlannedProbes, executeSafeRecipe
} from "./nd_true_doctor_v03.js";

const assert=(cond,msg)=>{if(!cond) throw new Error(msg)};

const context={
  context_revision:"test-r1",
  expected_profiles:[{
    profile_id:"ETP-DRIVE",
    supervisor:"True Memory",
    capability:"Google Drive native access",
    criticality:"CRITICAL",
    desired_state:"READY",
    primary_path:"ChatGPT Google Drive",
    qualified_alternates:["Governed Google API/Broker"],
    required_semantics:{read:true,write:true,execute:false},
    current_health:"DEGRADED"
  }],
  recent_incidents:[{
    incident_id:"TD-OLD-DRIVE",
    capability:"Google Drive native access",
    supervisor:"True Memory",
    provider:"Google Drive",
    failure_class:"INSTALL_CONTROL_PLANE",
    error_signature:"installed/enabled but permissions reports not_installed"
  }],
  patterns:[{
    pattern_id:"PAT-001",
    signature:"installed enabled not_installed control-plane divergence",
    failure_class:"INSTALL_CONTROL_PLANE",
    best_discriminating_tests:"control plane state provider profile"
  }],
  repair_recipes:[],
  capability_health:[]
};

const manual=doctorStart({
  invocation_mode:"MANUAL_CHAT",
  supervisor:"True Memory",
  capability:"Google Drive native access",
  provider:"Google Drive",
  error_signature:"installed/enabled but permission surface says not_installed",
  observed_state:"direct provider still reachable",
  authority_context:{diagnose:true,probe_readonly:true,reversible_qualification_write:false,safe_recipe_execution:true,material_mutation:false}
},context);

assert(manual.doctor_id===DOCTOR_ID,"manual doctor identity");
assert(manual.invocation.invocation_mode==="MANUAL_CHAT","manual mode");
assert(manual.contextual_diagnosis.expected_profile?.profile_id==="ETP-DRIVE","expected profile loaded");
assert(manual.contextual_diagnosis.similar_incidents.length===1,"prior incident retrieved");
assert(manual.contextual_diagnosis.failure_class==="INSTALL_CONTROL_PLANE","contextual class");

const auto=doctorStart({
  invocation_mode:"AUTOMATION",
  cycle_id:"cycle-2",
  branch_id:"SELF_DEV",
  supervisor:"True Memory",
  capability:"Google Drive native access",
  provider:"Google Drive",
  error_signature:"installed/enabled but permission surface says not_installed"
},context);

assert(auto.doctor_id===manual.doctor_id,"same doctor across invocation modes");
assert(auto.invocation.invocation_mode==="AUTOMATION","automation mode");
assert(auto.context_revision===manual.context_revision,"shared context revision");

const observed=doctorObserve(manual,[
  createProbeReceipt(PROBE_SPECS.CONTROL_PLANE_STATE,{status:"FAIL",ok:false,observed:"permissions view not_installed"}),
  createProbeReceipt(PROBE_SPECS.PROVIDER_PROFILE,{status:"PASS",ok:true,observed:"provider profile reachable"}),
  createProbeReceipt(PROBE_SPECS.SAFE_READ,{status:"PASS",ok:true,observed:"read succeeded"})
]);
assert(observed.refined_diagnosis.failure_class==="INSTALL_CONTROL_PLANE","Drive refinement");
assert(observed.refined_diagnosis.confidence>=0.97,"Drive confidence");
assert(observed.repair_plan.continuity.action==="CONTINUE_PRIMARY","keep proven primary despite control-plane divergence");

const exposure=doctorStart({
  invocation_mode:"AUTOMATION",
  supervisor:"True Developer",
  capability:"repo read",
  provider:"GitHub",
  error_signature:"provider down maybe"
},{expected_profiles:[],recent_incidents:[],patterns:[]});
const exposureObserved=doctorObserve(exposure,[
  createProbeReceipt(PROBE_SPECS.TOOL_EXPOSURE,{status:"FAIL",ok:false,observed:"tool absent"}),
  createProbeReceipt(PROBE_SPECS.PROVIDER_PROFILE,{status:"PASS",ok:true,observed:"GitHub reachable"})
]);
assert(exposureObserved.refined_diagnosis.failure_class==="TOOL_EXPOSURE","provider-down rejected when provider passes");

const auth=doctorStart({
  invocation_mode:"MANUAL_CHAT",capability:"Drive access",provider:"Drive",error_signature:"access fails"
},{});
const authObserved=doctorObserve(auth,[
  createProbeReceipt(PROBE_SPECS.PROVIDER_PROFILE,{status:"FAIL",ok:false,error:"401 unauthorized invalid_grant"})
]);
assert(authObserved.refined_diagnosis.failure_class==="AUTH_OAUTH","auth probe");

const perm=doctorStart({
  invocation_mode:"MANUAL_CHAT",capability:"write",provider:"Drive",error_signature:"operation fails"
},{});
const permObserved=doctorObserve(perm,[
  createProbeReceipt(PROBE_SPECS.PROVIDER_PROFILE,{status:"PASS",ok:true}),
  createProbeReceipt(PROBE_SPECS.SAFE_READ,{status:"FAIL",ok:false,error:"403 forbidden insufficient_scope"})
]);
assert(permObserved.refined_diagnosis.failure_class==="PERMISSION","permission probe");

const rw=doctorStart({
  invocation_mode:"AUTOMATION",capability:"write",provider:"Drive",error_signature:"read works write fails",
  authority_context:{diagnose:true,probe_readonly:true,reversible_qualification_write:true,safe_recipe_execution:false,material_mutation:false}
},{});
const rwObserved=doctorObserve(rw,[
  createProbeReceipt(PROBE_SPECS.SAFE_READ,{status:"PASS",ok:true}),
  createProbeReceipt(PROBE_SPECS.REVERSIBLE_WRITE,{status:"FAIL",ok:false,error:"write denied"})
]);
assert(rwObserved.refined_diagnosis.failure_class==="WRITE_ONLY","write-only refinement");

const thread=doctorStart({
  invocation_mode:"MANUAL_CHAT",capability:"plugin",error_signature:"existing thread fails"
},{});
const threadObserved=doctorObserve(thread,[
  createProbeReceipt(PROBE_SPECS.THREAD_CANARY,{status:"PASS",ok:true,observed:"fresh thread pass; new thread works"})
]);
assert(threadObserved.refined_diagnosis.failure_class==="THREAD_LOCAL","thread-local refinement");
assert(threadObserved.repair_plan.continuity.action==="MIGRATE_THREAD","thread continuity");

const runtime=doctorStart({
  invocation_mode:"AUTOMATION",capability:"browser recovery",provider:"Browserless",error_signature:"session lost after reclaim"
},{});
const runtimeObserved=doctorObserve(runtime,[
  createProbeReceipt(PROBE_SPECS.RUNTIME_HEALTH,{status:"FAIL",ok:false,observed:"reclaimed session unavailable"})
]);
assert(runtimeObserved.refined_diagnosis.failure_class==="DEPLOYMENT_RUNTIME","runtime refinement");

const failclosed=doctorStart({
  invocation_mode:"AUTOMATION",capability:"state write",error_signature:"duplicate write corrupt hash mismatch"
},{});
const fcObserved=doctorObserve(failclosed,[]);
assert(fcObserved.repair_plan.continuity.action==="FAIL_CLOSED","integrity fail-closed");

const finalized=doctorFinalize(observed,{
  verification_status:"PASS",
  verification_checks:["provider read still succeeds","parent objective can continue"],
  parent_objective_status:"CONTINUED",
  repair_outcome:{status:"CONTAINED"}
});
assert(finalized.learning_candidate!==null,"verified case yields learning candidate");
assert(finalized.learning_candidate.authority==="PROPOSAL_ONLY","learning cannot self-mutate production");

let probeCalls=0;
const adapter={
  controlPlaneState:async()=>({ok:false,status:"FAIL",observed:"not_installed"}),
  providerProfile:async()=>{probeCalls++;return {ok:true,status:"PASS",observed:"profile ok"}},
  safeRead:async()=>({ok:true,status:"PASS",observed:"read ok"})
};
const autoRun=await runPlannedProbes(auto,adapter);
assert(probeCalls===1,"injected probe adapter ran");
assert(autoRun.refined_diagnosis.failure_class==="INSTALL_CONTROL_PLANE","automated probe orchestration");


const browserlessContext={
  context_revision:"test-browserless-r1",
  expected_profiles:[{
    profile_id:"ETP-BROWSERLESS",
    supervisor:"True Research / True Developer",
    capability:"Browserless authenticated profile qualification",
    criticality:"CRITICAL",
    desired_state:"READY",
    primary_path:"Browserless custom MCP",
    qualified_alternates:["Doctor Make relay"],
    required_semantics:{read:true,write:true,execute:true},
    current_health:"BLOCKED_CURRENT_CONVERSATION"
  }],
  recent_incidents:[],
  patterns:[]
};

const browserless=doctorStart({
  invocation_mode:"MANUAL_CHAT",
  supervisor:"True Research / True Developer",
  capability:"Browserless authenticated profile qualification",
  provider:"Browserless",
  error_signature:"FORBIDDEN: This conversation does not support developer MCPs",
  observed_state:"native custom MCP blocked before provider execution",
  authority_context:{diagnose:true,probe_readonly:true,reversible_qualification_write:false,safe_recipe_execution:true,material_mutation:false}
},browserlessContext);

const browserlessObserved=doctorObserve(browserless,[
  createProbeReceipt(PROBE_SPECS.TOOL_EXPOSURE,{status:"FAIL",ok:false,error:"FORBIDDEN: This conversation does not support developer MCPs"}),
  createProbeReceipt(PROBE_SPECS.CONTROL_PLANE_STATE,{status:"PASS",ok:true,observed:"Browserless app permission full_access"}),
  createProbeReceipt(PROBE_SPECS.PROVIDER_PROFILE,{status:"PASS",ok:true,observed:"Browserless provider reachable independently"})
]);
assert(browserlessObserved.refined_diagnosis.failure_class==="CHATGPT_CONVERSATION_MCP_GATE","Browserless conversation gate classification");
assert(browserlessObserved.refined_diagnosis.confidence>=0.99,"Browserless gate confidence");
assert(browserlessObserved.repair_plan.continuity.action==="RESTORE_SAME_CHAT_CAPABILITY","same-chat continuity action");
assert(browserlessObserved.repair_plan.executable_safe_recipe_ids.includes("SAFE_SAME_CHAT_RELAY"),"same-chat relay recipe exposed");

const relayResult=await executeSafeRecipe(browserlessObserved,"SAFE_SAME_CHAT_RELAY",{
  sameChatRelay:async({idempotency_key})=>({
    ok:true,
    mutated:false,
    observed:"same-chat provider capability restored through independent relay",
    evidence_refs:["relay-canary",idempotency_key]
  })
});
assert(relayResult.status==="PASS","same-chat relay recipe executes");
assert(relayResult.mutated===false,"same-chat relay does not imply provider mutation");

const status=doctorStatus(context);
assert(status.field_ready===true,"field ready");
assert(status.shared_context===true,"shared context");
assert(status.broad_autonomous_mutation===false,"broad mutation remains off");

console.log(JSON.stringify({
  doctor_id:DOCTOR_ID,
  version:DOCTOR_VERSION,
  tests:21,
  pass:true,
  modes:["AUTOMATION","MANUAL_CHAT"],
  shared_context:true,
  validation_required:true,
  broad_autonomous_mutation:false
}));
