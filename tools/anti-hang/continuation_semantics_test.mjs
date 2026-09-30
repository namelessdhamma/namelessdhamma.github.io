import assert from 'node:assert/strict';

function resume(s){
  if(s.outcome_state==='OUTCOME_UNKNOWN') return {action:'RECONCILE',effect_id:s.effect_id,can_submit:false};
  if(s.effect_id||s.provider_job_id) return {action:'RESUME_OR_STATUS',effect_id:s.effect_id,provider_job_id:s.provider_job_id,can_submit:false};
  return {action:'RECOVER_CURRENT',can_submit:false};
}
function stop(s, remoteCancelled=false){
  return {...s,local_state:'INTERRUPTED',remote_cancelled:remoteCancelled,can_open_new_operation:false,next_action:s.effect_id?'RECONCILE_SAME_EFFECT':'RECOVER_CURRENT'};
}
function late(s,resultGeneration,currentGeneration,resultRef){
  return resultGeneration===currentGeneration
    ? {...s,result_ref:resultRef,control_authority:true}
    : {...s,late_result_ref:resultRef,control_authority:false,late_result_disposition:'EVIDENCE_ONLY'};
}
function overlapping(s,incomingEffectId){
  return s.effect_id && s.effect_id===incomingEffectId
    ? {action:'RESUME_OR_STATUS',effect_id:s.effect_id,provider_job_id:s.provider_job_id,can_submit:false}
    : {action:'RECONCILE_BEFORE_SUBMIT',effect_id:incomingEffectId,can_submit:false};
}
function wait(s,hasUsefulWork){
  return hasUsefulWork
    ? {action:'CONTINUE_USEFUL_WORK',effect_id:s.effect_id,provider_job_id:s.provider_job_id}
    : {action:'WAIT_EXTERNAL',effect_id:s.effect_id,provider_job_id:s.provider_job_id,resume_trigger:'PROVIDER_STATUS_CHANGE_OR_NEXT_WAKE'};
}
function compact(s){
  const keys=['objective_ref','owner_ref','phase','accepted_result_refs','effect_id','provider_job_id','operation_profile','outcome_state','observed_at','next_action','resume_trigger','generation'];
  return Object.fromEntries(keys.filter(k=>s[k]!==undefined).map(k=>[k,s[k]]));
}

const base={objective_ref:'NAM-397',owner_ref:'Supervisor',phase:'external',accepted_result_refs:['R1','R2'],effect_id:'E1',provider_job_id:'J1',operation_profile:'DURABLE_ASYNC',outcome_state:'RUNNING',observed_at:'2026-09-30T00:00:00Z',next_action:'STATUS_J1',generation:'G1'};

let x=stop(base);
assert.equal(x.remote_cancelled,false);
assert.equal(x.can_open_new_operation,false);
assert.equal(x.next_action,'RECONCILE_SAME_EFFECT');
console.log('T3_1_DELIVERED_STOP=PASS');

x=resume(base);
assert.equal(x.action,'RESUME_OR_STATUS');
assert.equal(x.can_submit,false);
assert.equal(x.provider_job_id,'J1');
console.log('T3_2_CLIENT_BREAK=PASS');

x=late(base,'G1','G2','R3');
assert.equal(x.control_authority,false);
assert.equal(x.late_result_disposition,'EVIDENCE_ONLY');
console.log('T3_3_LATE_RESULT=PASS');

x=resume({...base,outcome_state:'OUTCOME_UNKNOWN'});
assert.equal(x.action,'RECONCILE');
assert.equal(x.can_submit,false);
console.log('T3_4_LOST_RECEIPT=PASS');

x=overlapping(base,'E1');
assert.equal(x.action,'RESUME_OR_STATUS');
assert.equal(x.can_submit,false);
assert.equal(x.provider_job_id,'J1');
console.log('T3_5_OVERLAPPING_WAKE=PASS');

x=compact(base);
assert.deepEqual(x.accepted_result_refs,['R1','R2']);
assert.equal(x.effect_id,'E1');
assert.equal(x.provider_job_id,'J1');
console.log('T3_6_CONTEXT_BREAK=PASS');

assert.equal(wait(base,true).action,'CONTINUE_USEFUL_WORK');
console.log('T3_7_USEFUL_WORK=PASS');

x=wait(base,false);
assert.equal(x.action,'WAIT_EXTERNAL');
assert.equal(x.resume_trigger,'PROVIDER_STATUS_CHANGE_OR_NEXT_WAKE');
console.log('T3_8_WAIT_EXTERNAL=PASS');

console.log('ND_CONTINUATION_SEMANTICS=PASS');
