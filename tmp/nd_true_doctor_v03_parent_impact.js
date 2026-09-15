// ND True Doctor v0.3 — bounded parent-impact observability extension.
// D&Q only. Distinguishes a failing/degraded route from failure of the parent capability.

export const ROUTE_HEALTH_STATES = Object.freeze([
  "ROUTE_HEALTHY",
  "ROUTE_LOCAL_DEGRADED",
  "PARENT_CAPABILITY_DEGRADED",
  "PARENT_CAPABILITY_FAILED",
  "UNKNOWN"
]);

const norm = v => String(v ?? "").toUpperCase();
const pass = v => norm(v) === "PASS" || v === true;
const fail = v => norm(v) === "FAIL" || v === false;

export function classifyParentImpact(input={}) {
  const required = input.required_semantics || {read:true, write:false, execute:false};
  const parent = input.parent_checks || {};
  const route = input.route_checks || {};
  const alternates = input.qualified_alternate_checks || [];

  const requiredChecks=[];
  if (required.read) requiredChecks.push(parent.read);
  if (required.write) requiredChecks.push(parent.write);
  if (required.execute) requiredChecks.push(parent.execute);

  const knownRequired = requiredChecks.filter(v => v !== undefined && v !== null);
  const parentAllPass = knownRequired.length === requiredChecks.length && requiredChecks.length > 0 && knownRequired.every(pass);
  const parentAnyFail = knownRequired.some(fail);
  const routeAnyFail = Object.values(route).some(fail);
  const alternateSatisfies = alternates.some(a => {
    const checks=[];
    if (required.read) checks.push(a.read);
    if (required.write) checks.push(a.write);
    if (required.execute) checks.push(a.execute);
    return checks.length > 0 && checks.every(pass);
  });

  if (parentAllPass && routeAnyFail) return {
    state:"ROUTE_LOCAL_DEGRADED",
    parent_objective_impact:"NONE_OBSERVED",
    action:"CONTINUE_PARENT_OBJECTIVE",
    rationale:"a local route/admin check failed while all required parent semantics passed",
    evidence_complete:true
  };

  if (parentAllPass) return {
    state:"ROUTE_HEALTHY",
    parent_objective_impact:"NONE_OBSERVED",
    action:"CONTINUE_PARENT_OBJECTIVE",
    rationale:"all required parent semantics passed",
    evidence_complete:true
  };

  if (parentAnyFail && alternateSatisfies) return {
    state:"PARENT_CAPABILITY_DEGRADED",
    parent_objective_impact:"PRIMARY_PATH_IMPACT_CONTAINED",
    action:"USE_QUALIFIED_FAILOVER",
    rationale:"required primary semantic failed but a qualified alternate satisfies the same required semantics",
    evidence_complete:true
  };

  if (parentAnyFail && !alternateSatisfies) return {
    state:"PARENT_CAPABILITY_FAILED",
    parent_objective_impact:"REQUIRED_SEMANTIC_UNAVAILABLE",
    action:"ESCALATE_PARENT_IMPACT",
    rationale:"a required parent semantic failed and no qualified alternate is proven to satisfy it",
    evidence_complete:true
  };

  return {
    state:"UNKNOWN",
    parent_objective_impact:"UNKNOWN",
    action:"PROBE_REQUIRED_SEMANTICS",
    rationale:"insufficient direct evidence for one or more required parent semantics",
    evidence_complete:false
  };
}

export function createRouteHealthReceipt(input={}) {
  const classification=classifyParentImpact(input);
  return {
    receipt_version:"route-health-parent-impact/0.1",
    capability:input.capability || "unknown",
    route:input.route || "unknown",
    required_semantics:input.required_semantics || null,
    route_checks:input.route_checks || {},
    parent_checks:input.parent_checks || {},
    qualified_alternate_checks:input.qualified_alternate_checks || [],
    ...classification,
    observed_at:input.observed_at || new Date().toISOString(),
    evidence_refs:input.evidence_refs || []
  };
}
