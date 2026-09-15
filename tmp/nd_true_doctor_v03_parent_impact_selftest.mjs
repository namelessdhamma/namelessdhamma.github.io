import assert from 'node:assert/strict';
import {classifyParentImpact} from './nd_true_doctor_v03_parent_impact.js';

const benign403=classifyParentImpact({
  required_semantics:{read:true,write:false,execute:false},
  route_checks:{docs_api_enable:'FAIL'},
  parent_checks:{read:'PASS'}
});
assert.equal(benign403.state,'ROUTE_LOCAL_DEGRADED');
assert.equal(benign403.action,'CONTINUE_PARENT_OBJECTIVE');

const hardFailure=classifyParentImpact({
  required_semantics:{read:true,write:false,execute:false},
  route_checks:{provider_profile:'FAIL'},
  parent_checks:{read:'FAIL'},
  qualified_alternate_checks:[]
});
assert.equal(hardFailure.state,'PARENT_CAPABILITY_FAILED');
assert.equal(hardFailure.action,'ESCALATE_PARENT_IMPACT');

const contained=classifyParentImpact({
  required_semantics:{read:true,write:false,execute:false},
  route_checks:{primary:'FAIL'},
  parent_checks:{read:'FAIL'},
  qualified_alternate_checks:[{read:'PASS'}]
});
assert.equal(contained.state,'PARENT_CAPABILITY_DEGRADED');
assert.equal(contained.action,'USE_QUALIFIED_FAILOVER');

const unknown=classifyParentImpact({
  required_semantics:{read:true,write:true,execute:false},
  route_checks:{admin:'FAIL'},
  parent_checks:{read:'PASS'}
});
assert.equal(unknown.state,'UNKNOWN');
assert.equal(unknown.evidence_complete,false);

console.log(JSON.stringify({ok:true,cases:4}));
