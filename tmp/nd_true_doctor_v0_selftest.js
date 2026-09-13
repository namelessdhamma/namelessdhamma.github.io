// ND True Doctor v0.1 regression fixtures
// Mirrors the first field cases plus representative synthetic boundaries.
// Expected execution: import ./nd_true_doctor_v0.js and assert exact primary class.

import { doctorDiagnose, repairRoute } from "./nd_true_doctor_v0.js";

const fixtures = [
  ["Drive control-plane divergence","INSTALL_CONTROL_PLANE",{
    error_signature:"catalog dependency installed/enabled but permissions side reports not_installed",
    provider:"Google Drive",observed_state:"direct provider profile succeeds"
  }],
  ["Linear schema/runtime divergence","SCHEMA_RUNTIME",{
    error_signature:"tool not found; schema exposed but runtime missing",provider:"Linear"
  }],
  ["Browser reclaim","DEPLOYMENT_RUNTIME",{
    error_signature:"after hard timeout browser reclaim prior session returned about:blank"
  }],
  ["OAuth","AUTH_OAUTH",{error_signature:"401 unauthorized invalid_grant OAuth"}],
  ["Quota","RATE_LIMIT_QUOTA",{error_signature:"429 too many requests rate limit"}],
  ["Thread-local","THREAD_LOCAL",{error_signature:"existing thread fails but new thread works"}],
  ["Write-only","WRITE_ONLY",{error_signature:"read works but write fails"}],
  ["Unknown","UNKNOWN",{error_signature:"unexpected purple failure zxq"}],
];

let passed = 0;
for (const [name, expected, input] of fixtures) {
  const actual = doctorDiagnose(input).diagnosis.failure_class;
  if (actual !== expected) throw new Error(`${name}: expected ${expected}, got ${actual}`);
  passed++;
}

for (const failureClass of ["THREAD_LOCAL","INSTALL_CONTROL_PLANE","DEPLOYMENT_RUNTIME","DATA_INTEGRITY"]) {
  const route = repairRoute({}, {failure_class:failureClass, confidence:0.9});
  if (!Array.isArray(route.actions) || !route.actions.length) throw new Error(`${failureClass}: missing repair actions`);
  if (!Array.isArray(route.verification) || !route.verification.length) throw new Error(`${failureClass}: missing verification`);
  if (route.mutation_allowed !== false) throw new Error(`${failureClass}: v0.1 must remain non-mutating`);
}

console.log(JSON.stringify({doctor:"0.1.0",passed,total:fixtures.length,repair_route_samples:4,mutations:false}));
