// ND True Doctor v0.3 — contextual diagnosis + safe probe orchestration.
// One logical Doctor across AUTOMATION and MANUAL_CHAT invocation modes.
// Qualification artifact: broad autonomous mutation is intentionally NOT enabled.

export const DOCTOR_ID = "ND_TRUE_DOCTOR";
export const DOCTOR_VERSION = "0.4.0-rc1";
export const CONTRACT_VERSION = "doctor-contract/0.4-rc1";

export const INVOCATION_MODES = Object.freeze(["AUTOMATION", "MANUAL_CHAT"]);
export const HEALTH_STATES = Object.freeze(["READY", "DEGRADED", "BLOCKED", "UNKNOWN"]);
export const CONTINUITY_ACTIONS = Object.freeze([
  "CONTINUE_PRIMARY",
  "CONTINUE_DEGRADED",
  "MIGRATE_THREAD",
  "SWITCH_SURFACE",
  "USE_QUALIFIED_FAILOVER",
  "RESTORE_SAME_CHAT_CAPABILITY",
  "HUMAN_GATE",
  "FAIL_CLOSED"
]);

export const FAILURE_CLASSES = Object.freeze([
  "TOOL_EXPOSURE",
  "CHATGPT_CONVERSATION_MCP_GATE",
  "SCHEMA_RUNTIME",
  "INSTALL_CONTROL_PLANE",
  "PERMISSION",
  "AUTH_OAUTH",
  "PROVIDER_BACKEND",
  "CHATGPT_PLATFORM",
  "SURFACE",
  "MODEL",
  "THREAD_LOCAL",
  "WRITE_ONLY",
  "RATE_LIMIT_QUOTA",
  "TOOL_COLLISION_REGISTRY_PRESSURE",
  "NETWORK_PATH",
  "STATE_MEMORY_POINTER",
  "DEPLOYMENT_RUNTIME",
  "DATA_INTEGRITY",
  "AUTHORITY_GOVERNANCE",
  "UNKNOWN"
]);

export const PROBE_SPECS = Object.freeze({
  TOOL_EXPOSURE: {
    probe_id: "tool_exposure",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "LOW",
    failure_domain: "CHATGPT_TOOL_REGISTRY",
    adapter_method: "toolExposure"
  },
  CONTROL_PLANE_STATE: {
    probe_id: "control_plane_state",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "LOW",
    failure_domain: "CHATGPT_PLUGIN_CONTROL_PLANE",
    adapter_method: "controlPlaneState"
  },
  PROVIDER_PROFILE: {
    probe_id: "provider_profile",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "LOW",
    failure_domain: "PROVIDER_AUTH_BACKEND",
    adapter_method: "providerProfile"
  },
  SAFE_READ: {
    probe_id: "safe_read",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "LOW",
    failure_domain: "PROVIDER_DATA_PATH",
    adapter_method: "safeRead"
  },
  REVERSIBLE_WRITE: {
    probe_id: "reversible_write",
    mutation_class: "REVERSIBLE_QUALIFICATION",
    risk: "MEDIUM",
    cost: "MEDIUM",
    failure_domain: "PROVIDER_WRITE_PATH",
    adapter_method: "reversibleWriteReadBack"
  },
  THREAD_CANARY: {
    probe_id: "thread_canary",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "MEDIUM",
    failure_domain: "CHATGPT_THREAD_RUNTIME",
    adapter_method: "threadCanary"
  },
  SURFACE_CANARY: {
    probe_id: "surface_canary",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "MEDIUM",
    failure_domain: "CHATGPT_SURFACE",
    adapter_method: "surfaceCanary"
  },
  RUNTIME_HEALTH: {
    probe_id: "runtime_health",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "LOW",
    failure_domain: "OWNED_RUNTIME",
    adapter_method: "runtimeHealth"
  },
  POINTER_VERIFY: {
    probe_id: "pointer_verify",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "LOW",
    failure_domain: "TRUE_MEMORY_STATE",
    adapter_method: "verifyPointer"
  },
  BROWSER_SESSION: {
    probe_id: "browser_session",
    mutation_class: "NONE",
    risk: "LOW",
    cost: "MEDIUM",
    failure_domain: "BROWSER_RUNTIME",
    adapter_method: "browserSessionHealth"
  }
});

const now = () => new Date().toISOString();
const norm = v => String(v ?? "").toLowerCase();
const has = (s, ...xs) => xs.some(x => s.includes(x));
const unique = xs => [...new Set(xs.filter(Boolean))];
const clamp = (n,min=0,max=1) => Math.max(min,Math.min(max,n));

function tokenSet(v) {
  return new Set(norm(v).split(/[^a-zа-яё0-9_]+/i).filter(x => x.length > 2));
}
function jaccard(a,b) {
  const A=tokenSet(a), B=tokenSet(b);
  if (!A.size || !B.size) return 0;
  let inter=0; for (const x of A) if (B.has(x)) inter++;
  return inter / (A.size + B.size - inter);
}
function evidenceBlob(i={}) {
  return [
    i.error_signature, i.observed_state, i.expected_state, i.provider,
    i.surface, i.notes, i.runtime_error, i.capability
  ].filter(Boolean).join(" | ");
}
function id(prefix="DOC") {
  return prefix + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2,8);
}

export function createInvocationEnvelope(input={}) {
  const mode = INVOCATION_MODES.includes(input.invocation_mode) ? input.invocation_mode : "MANUAL_CHAT";
  return {
    doctor_id: DOCTOR_ID,
    doctor_version: DOCTOR_VERSION,
    invocation_id: input.invocation_id || id("INV"),
    invocation_mode: mode,
    started_at: input.started_at || now(),
    trigger: input.trigger || "TECHNICAL_FAILURE",
    cycle_id: input.cycle_id || null,
    branch_id: input.branch_id || null,
    assignment_id: input.assignment_id || null,
    chat_or_thread: input.chat_or_thread || null,
    surface: input.surface || null,
    model: input.model || null,
    parent_objective: input.parent_objective || null,
    supervisor: input.supervisor || "unknown",
    capability: input.capability || "unknown",
    resource_scope: input.resource_scope || null,
    authority_context: input.authority_context || {
      diagnose: true,
      probe_readonly: true,
      reversible_qualification_write: false,
      safe_recipe_execution: false,
      material_mutation: false
    }
  };
}

export function createExpectedToolProfile(input={}) {
  return {
    profile_id: input.profile_id || id("ETP"),
    supervisor: input.supervisor || "unknown",
    capability: input.capability || "unknown",
    criticality: input.criticality || "MEDIUM",
    desired_state: input.desired_state || "READY",
    primary_path: input.primary_path || null,
    qualified_alternates: input.qualified_alternates || [],
    required_semantics: {
      read: input.required_semantics?.read ?? true,
      write: input.required_semantics?.write ?? false,
      execute: input.required_semantics?.execute ?? false
    },
    authority_ceiling: input.authority_ceiling || "LOCAL_BOUNDED",
    health_checks: input.health_checks || [],
    failure_domains: input.failure_domains || [],
    last_known_good: input.last_known_good || null,
    current_health: input.current_health || "UNKNOWN",
    version: input.version || "1"
  };
}

export function createContextSnapshot(input={}) {
  return {
    doctor_id: DOCTOR_ID,
    doctor_version: DOCTOR_VERSION,
    context_revision: input.context_revision || null,
    fetched_at: input.fetched_at || now(),
    expected_profiles: input.expected_profiles || [],
    recent_incidents: input.recent_incidents || [],
    patterns: input.patterns || [],
    repair_recipes: input.repair_recipes || [],
    capability_health: input.capability_health || [],
    unresolved_incidents: input.unresolved_incidents || [],
    learning_candidates: input.learning_candidates || [],
    authoritative_refs: input.authoritative_refs || []
  };
}

export function createIncidentEnvelope(input={}, invocation=null) {
  return {
    incident_id: input.incident_id || id("INC"),
    correlation_id: input.correlation_id || invocation?.invocation_id || id("COR"),
    detected_at: input.detected_at || now(),
    detected_by: input.detected_by || "true-doctor",
    doctor_id: DOCTOR_ID,
    invocation_mode: invocation?.invocation_mode || input.invocation_mode || "MANUAL_CHAT",
    system: input.system || "unknown",
    supervisor: input.supervisor || invocation?.supervisor || "unknown",
    capability: input.capability || invocation?.capability || "unknown",
    expected_state: input.expected_state || "",
    observed_state: input.observed_state || "",
    error_signature: input.error_signature || "",
    severity: input.severity || "MEDIUM",
    surface: input.surface || invocation?.surface || "",
    model: input.model || invocation?.model || "",
    thread_or_run: input.thread_or_run || invocation?.chat_or_thread || "",
    client_version: input.client_version || "",
    provider: input.provider || "",
    evidence_refs: input.evidence_refs || [],
    current_status: "CAPTURED",
    root_cause_status: "UNKNOWN"
  };
}

export function classifyIncident(i={}) {
  const blob = norm(evidenceBlob(i));
  const signals=[];

  if (has(blob,"tool not found","schema/runtime","schema exposed","runtime missing"))
    signals.push(["SCHEMA_RUNTIME",0.96,"tool/schema advertised but runtime action missing"]);
  if (has(blob,"not_installed","installed/enabled","control-plane","install state"))
    signals.push(["INSTALL_CONTROL_PLANE",0.90,"installation/control-plane states diverge"]);
  if (has(blob,"not exposed","missing tool","tool absent","unavailable in this chat"))
    signals.push(["TOOL_EXPOSURE",0.88,"expected tool absent from active execution surface"]);
  if (has(blob,"401","unauthorized","oauth","refresh token","invalid_grant"))
    signals.push(["AUTH_OAUTH",0.93,"authentication/session evidence"]);
  if (has(blob,"this conversation does not support developer mcps","conversation does not support developer mcp"))
    signals.push(["CHATGPT_CONVERSATION_MCP_GATE",0.995,"developer/custom MCP rejected by ChatGPT conversation execution gate before provider execution"]);
  if (has(blob,"403","permission denied","insufficient_scope","forbidden"))
    signals.push(["PERMISSION",0.90,"permission/scope evidence"]);
  if (has(blob,"429","rate limit","quota","too many requests"))
    signals.push(["RATE_LIMIT_QUOTA",0.95,"rate/quota evidence"]);
  if (has(blob,"timeout","network","connection reset","dns","econn","socket"))
    signals.push(["NETWORK_PATH",0.72,"network/transport symptom"]);
  if (has(blob,"about:blank","reclaim","session lost","process exited","deployment unhealthy"))
    signals.push(["DEPLOYMENT_RUNTIME",0.86,"runtime/session lifecycle evidence"]);
  if (has(blob,"old thread","new thread works","thread-local","existing thread"))
    signals.push(["THREAD_LOCAL",0.94,"thread-local divergence evidence"]);
  if (has(blob,"android","mobile","web works","desktop works"))
    signals.push(["SURFACE",0.66,"surface-specific evidence; verify before concluding"]);
  if (has(blob,"read works","write fails","read pass","write denied"))
    signals.push(["WRITE_ONLY",0.91,"read/write asymmetry"]);
  if (has(blob,"stale pointer","missing pointer","statehead mismatch","registry mismatch"))
    signals.push(["STATE_MEMORY_POINTER",0.92,"state/pointer integrity evidence"]);
  if (has(blob,"duplicate write","hash mismatch","corrupt","data loss"))
    signals.push(["DATA_INTEGRITY",0.96,"data-integrity evidence"]);
  if (has(blob,"unauthorized mutation","authority violation","scope violation"))
    signals.push(["AUTHORITY_GOVERNANCE",0.93,"authority-boundary evidence"]);
  if (has(blob,"provider down","backend 5","service unavailable","upstream"))
    signals.push(["PROVIDER_BACKEND",0.76,"provider/backend symptom; independent probe required"]);
  if (has(blob,"registry pressure","collision","custom mcp","apps disappear"))
    signals.push(["TOOL_COLLISION_REGISTRY_PRESSURE",0.78,"tool-registry collision hypothesis"]);

  if (!signals.length) return {
    failure_class:"UNKNOWN", confidence:0.35,
    rationale:"no deterministic signature matched", alternatives:[],
    next_probe:"collect exact error + expected capability + independent backend evidence"
  };
  signals.sort((a,b)=>b[1]-a[1]);
  const [failure_class,confidence,rationale]=signals[0];
  return {
    failure_class,confidence,rationale,
    alternatives:signals.slice(1,4).map(([c,p,r])=>({failure_class:c,confidence:p,rationale:r})),
    next_probe:discriminatingProbe(failure_class)
  };
}

export function findExpectedProfile(incident, context) {
  const profiles=context?.expected_profiles || [];
  return profiles
    .map(p=>({p,score:
      (norm(p.capability)===norm(incident.capability)?5:0)+
      (norm(p.supervisor)===norm(incident.supervisor)?2:0)+
      jaccard(p.capability,incident.capability)*2
    }))
    .sort((a,b)=>b.score-a.score)[0]?.p || null;
}

export function retrieveSimilarIncidents(incident, context, limit=5) {
  const blob=evidenceBlob(incident);
  return (context?.recent_incidents || [])
    .filter(x=>x.incident_id!==incident.incident_id)
    .map(x=>({
      ...x,
      similarity:
        (norm(x.capability)===norm(incident.capability)?0.35:0)+
        (norm(x.provider)===norm(incident.provider)?0.15:0)+
        jaccard(evidenceBlob(x),blob)*0.5
    }))
    .filter(x=>x.similarity>0.12)
    .sort((a,b)=>b.similarity-a.similarity)
    .slice(0,limit);
}

export function retrieveMatchingPatterns(incident, context, limit=5) {
  const blob=evidenceBlob(incident);
  return (context?.patterns || [])
    .map(p=>({
      ...p,
      match_score: Math.max(
        jaccard(p.signature||"",blob),
        jaccard(p.best_discriminating_tests||"",blob)*0.5
      )
    }))
    .filter(p=>p.match_score>0.10)
    .sort((a,b)=>b.match_score-a.match_score)
    .slice(0,limit);
}

export function contextualizeDiagnosis(incident, preliminary, context) {
  const profile=findExpectedProfile(incident,context);
  const similar=retrieveSimilarIncidents(incident,context);
  const patterns=retrieveMatchingPatterns(incident,context);

  let confidence=preliminary.confidence;
  let rationale=preliminary.rationale;
  let history_support=0;

  for (const x of similar) {
    if (x.failure_class && x.failure_class===preliminary.failure_class) history_support+=Math.min(0.12,x.similarity*0.2);
  }
  const patternSupport=patterns
    .filter(p=>p.failure_class===preliminary.failure_class || norm(p.signature).includes(norm(preliminary.failure_class)))
    .reduce((s,p)=>s+Math.min(0.08,p.match_score*0.15),0);

  confidence=clamp(confidence + Math.min(0.15,history_support+patternSupport));
  if (history_support || patternSupport) rationale += "; prior ND evidence supports this class";

  return {
    ...preliminary,
    confidence,
    rationale,
    expected_profile:profile,
    similar_incidents:similar,
    matching_patterns:patterns,
    history_support:Math.min(0.15,history_support+patternSupport)
  };
}

export function discriminatingProbe(failureClass) {
  switch (failureClass) {
    case "CHATGPT_CONVERSATION_MCP_GATE": return "TOOL_EXPOSURE + CONTROL_PLANE_STATE + PROVIDER_PROFILE + SAME_CHAT_RELAY";
    case "SCHEMA_RUNTIME": return "TOOL_EXPOSURE + exact runtime action + PROVIDER_PROFILE";
    case "INSTALL_CONTROL_PLANE": return "CONTROL_PLANE_STATE + PROVIDER_PROFILE";
    case "TOOL_EXPOSURE": return "TOOL_EXPOSURE + PROVIDER_PROFILE + optional THREAD_CANARY";
    case "AUTH_OAUTH": return "PROVIDER_PROFILE";
    case "PERMISSION": return "PROVIDER_PROFILE + SAFE_READ + optional REVERSIBLE_WRITE";
    case "THREAD_LOCAL": return "THREAD_CANARY";
    case "SURFACE": return "SURFACE_CANARY";
    case "WRITE_ONLY": return "SAFE_READ + REVERSIBLE_WRITE";
    case "PROVIDER_BACKEND": return "PROVIDER_PROFILE + SAFE_READ";
    case "DEPLOYMENT_RUNTIME": return "RUNTIME_HEALTH";
    case "RATE_LIMIT_QUOTA": return "PROVIDER_PROFILE or provider quota probe";
    case "STATE_MEMORY_POINTER": return "POINTER_VERIFY";
    default: return "smallest independent probe separating ChatGPT state from provider/backend state";
  }
}

export function planProbes(incident, diagnosis, context={}, options={}) {
  const max=options.max_probes ?? 4;
  const allowReversible=Boolean(options.allow_reversible_qualification_write);
  const c=diagnosis.failure_class;
  let names=[];

  if (c==="CHATGPT_CONVERSATION_MCP_GATE") names=["TOOL_EXPOSURE","CONTROL_PLANE_STATE","PROVIDER_PROFILE"];
  else if (c==="SCHEMA_RUNTIME") names=["TOOL_EXPOSURE","PROVIDER_PROFILE"];
  else if (c==="INSTALL_CONTROL_PLANE") names=["CONTROL_PLANE_STATE","PROVIDER_PROFILE","SAFE_READ"];
  else if (c==="TOOL_EXPOSURE") names=["TOOL_EXPOSURE","PROVIDER_PROFILE","SAFE_READ","THREAD_CANARY"];
  else if (c==="AUTH_OAUTH") names=["PROVIDER_PROFILE"];
  else if (c==="PERMISSION") names=["PROVIDER_PROFILE","SAFE_READ","REVERSIBLE_WRITE"];
  else if (c==="THREAD_LOCAL") names=["THREAD_CANARY","PROVIDER_PROFILE"];
  else if (c==="SURFACE") names=["SURFACE_CANARY","PROVIDER_PROFILE"];
  else if (c==="WRITE_ONLY") names=["SAFE_READ","REVERSIBLE_WRITE"];
  else if (c==="PROVIDER_BACKEND") names=["PROVIDER_PROFILE","SAFE_READ"];
  else if (c==="DEPLOYMENT_RUNTIME") names=["RUNTIME_HEALTH"];
  else if (c==="STATE_MEMORY_POINTER") names=["POINTER_VERIFY"];
  else if (norm(incident.system).includes("browser") || norm(incident.provider).includes("browserless"))
    names=["BROWSER_SESSION","RUNTIME_HEALTH"];
  else names=["PROVIDER_PROFILE","SAFE_READ"];

  return unique(names)
    .map(n=>PROBE_SPECS[n])
    .filter(Boolean)
    .filter(p=>p.mutation_class==="NONE" || allowReversible)
    .slice(0,max)
    .map(p=>({...p,reason:"discriminate "+c}));
}

export function createProbeReceipt(spec, result={}) {
  return {
    probe_receipt_id:result.probe_receipt_id || id("PRB"),
    probe_id:spec.probe_id,
    started_at:result.started_at || null,
    finished_at:result.finished_at || now(),
    status:result.status || (result.ok===true?"PASS":result.ok===false?"FAIL":"UNKNOWN"),
    ok:result.ok ?? null,
    mutation_class:spec.mutation_class,
    failure_domain:spec.failure_domain,
    observed:result.observed || null,
    error:result.error || null,
    evidence_refs:result.evidence_refs || [],
    adapter:result.adapter || spec.adapter_method
  };
}

function probe(receipts,id) {
  return (receipts||[]).find(x=>x.probe_id===id);
}
function pass(receipts,id) { return probe(receipts,id)?.status==="PASS"; }
function fail(receipts,id) { return probe(receipts,id)?.status==="FAIL"; }

export function refineDiagnosis(incident, diagnosis, receipts=[]) {
  let d={...diagnosis};
  const exposure=probe(receipts,"tool_exposure");
  const cp=probe(receipts,"control_plane_state");
  const provider=probe(receipts,"provider_profile");
  const read=probe(receipts,"safe_read");
  const write=probe(receipts,"reversible_write");
  const thread=probe(receipts,"thread_canary");
  const surface=probe(receipts,"surface_canary");
  const runtime=probe(receipts,"runtime_health");
  const pointer=probe(receipts,"pointer_verify");

  // Exact conversation-gate signature plus healthy control/provider evidence isolates ChatGPT routing.
  if (/this conversation does not support developer mcps/i.test(incident.error_signature||incident.runtime_error||"") &&
      (cp?.status==="PASS" || provider?.status==="PASS" || read?.status==="PASS")) {
    d={...d,failure_class:"CHATGPT_CONVERSATION_MCP_GATE",confidence:0.995,
      rationale:"exact developer-MCP conversation gate reproduced while permission/provider evidence remains healthy"};
  }

  // Independent provider success is negative evidence for provider outage.
  if ((pass(receipts,"provider_profile") || pass(receipts,"safe_read")) &&
      d.failure_class==="PROVIDER_BACKEND") {
    d={...d,failure_class: exposure?.status==="FAIL"?"TOOL_EXPOSURE":d.alternatives?.[0]?.failure_class || "UNKNOWN",
      confidence:0.82,rationale:"independent provider/read probe passed; provider-down hypothesis rejected"};
  }
  if (d.failure_class!=="CHATGPT_CONVERSATION_MCP_GATE" && exposure?.status==="FAIL" && (provider?.status==="PASS" || read?.status==="PASS")) {
    d={...d,failure_class:"TOOL_EXPOSURE",confidence:0.97,
      rationale:"active tool exposure failed while independent provider path passed"};
  }
  if (cp?.status==="FAIL" && (provider?.status==="PASS" || read?.status==="PASS")) {
    d={...d,failure_class:"INSTALL_CONTROL_PLANE",confidence:0.97,
      rationale:"control-plane state diverges while provider path is healthy"};
  }
  if (provider?.status==="FAIL" && /401|unauth|oauth|invalid_grant/i.test(provider.error||provider.observed||"")) {
    d={...d,failure_class:"AUTH_OAUTH",confidence:0.98,rationale:"provider auth probe returned authentication failure"};
  }
  if (provider?.status==="PASS" && read?.status==="FAIL" &&
      /403|permission|scope|forbidden/i.test(read.error||read.observed||"")) {
    d={...d,failure_class:"PERMISSION",confidence:0.96,rationale:"auth/profile succeeds but operation is denied by permission/scope"};
  }
  if (read?.status==="PASS" && write?.status==="FAIL") {
    d={...d,failure_class:"WRITE_ONLY",confidence:0.97,rationale:"read path passed while bounded write/read-back failed"};
  }
  if (thread?.status==="PASS" && /fresh.*pass|new.*works/i.test(thread.observed||"")) {
    d={...d,failure_class:"THREAD_LOCAL",confidence:0.98,rationale:"equivalent fresh-thread canary passed"};
  }
  if (surface?.status==="PASS" && /alternate.*pass|web.*pass|desktop.*pass|android.*pass/i.test(surface.observed||"")) {
    d={...d,failure_class:"SURFACE",confidence:0.93,rationale:"equivalent alternate-surface canary passed"};
  }
  if (runtime?.status==="FAIL") {
    d={...d,failure_class:"DEPLOYMENT_RUNTIME",confidence:0.94,rationale:"owned runtime health probe failed"};
  }
  if (pointer?.status==="FAIL") {
    d={...d,failure_class:"STATE_MEMORY_POINTER",confidence:0.96,rationale:"authoritative pointer verification failed"};
  }
  return {
    ...d,
    probe_count:receipts.length,
    probe_summary: {
      tool_exposure: exposure?.status || null,
      control_plane_state: cp?.status || null,
      provider_profile: provider?.status || null,
      safe_read: read?.status || null,
      reversible_write: write?.status || null,
      thread_canary: thread?.status || null,
      surface_canary: surface?.status || null,
      runtime_health: runtime?.status || null,
      pointer_verify: pointer?.status || null
    },
    validated_at:now()
  };
}

export function continuityDecision(incident, diagnosis, context={}) {
  const c=diagnosis.failure_class;
  const profile=diagnosis.expected_profile || findExpectedProfile(incident,context);
  const alternates=profile?.qualified_alternates || [];

  if (["DATA_INTEGRITY","AUTHORITY_GOVERNANCE"].includes(c))
    return {action:"FAIL_CLOSED",reason:"integrity/authority invariant at risk",alternate:null};
  if (c==="INSTALL_CONTROL_PLANE" && diagnosis.probe_summary?.safe_read==="PASS")
    return {action:"CONTINUE_PRIMARY",reason:"required primary read path is live despite control-plane inconsistency; repair metadata state out-of-band",alternate:null};
  if (c==="CHATGPT_CONVERSATION_MCP_GATE")
    return {action:"RESTORE_SAME_CHAT_CAPABILITY",reason:"native custom-MCP route is conversation-blocked; restore equivalent provider capability through an already-authorized independent relay in this same chat",alternate:alternates[0]||null};
  if (c==="THREAD_LOCAL")
    return {action:"MIGRATE_THREAD",reason:"thread-local failure with durable context recovery required",alternate:null};
  if (c==="SURFACE")
    return {action:"SWITCH_SURFACE",reason:"surface-local failure",alternate:null};
  if (alternates.length)
    return {action:"USE_QUALIFIED_FAILOVER",reason:"primary degraded and a declared alternate exists",alternate:alternates[0]};
  if (["TOOL_EXPOSURE","SCHEMA_RUNTIME","INSTALL_CONTROL_PLANE","PROVIDER_BACKEND","DEPLOYMENT_RUNTIME","RATE_LIMIT_QUOTA"].includes(c))
    return {action:"CONTINUE_DEGRADED",reason:"preserve parent objective where a safe local workaround exists",alternate:null};
  if (["AUTH_OAUTH","PERMISSION"].includes(c))
    return {action:"HUMAN_GATE",reason:"credential/permission changes may require irreducible user action",alternate:null};
  return {action:"CONTINUE_DEGRADED",reason:"unknown failure: preserve state and investigate without unsafe mutation",alternate:null};
}

export function repairRoute(incident, diagnosis, context={}) {
  const c=diagnosis.failure_class;
  const continuity=continuityDecision(incident,diagnosis,context);
  const base={
    failure_class:c,
    diagnosis_confidence:diagnosis.confidence,
    continuity,
    actions:[],
    verification:[],
    mutation_allowed:false,
    executable_safe_recipe_ids:[],
    authority_required:"existing local authority for safe containment; Agent assignment for material engineering/mutation",
    terminal_if_unrepairable:"UPSTREAM_ONLY_OR_QUALIFIED_FAILOVER"
  };
  const add=(...xs)=>base.actions.push(...xs);
  const verify=(...xs)=>base.verification.push(...xs);

  if (c==="CHATGPT_CONVERSATION_MCP_GATE") {
    add("preserve parent objective and incident evidence","do not reinstall or repair provider OAuth when provider/control-plane probes pass","bind an independent same-chat relay to the same provider capability","repeat the original provider operation through the relay","keep native route eligible for later recovery");
    verify("relay reaches the intended provider","original operation semantics succeed in this same chat","no privilege widening or duplicate side effects","native provider role is not silently demoted");
    base.executable_safe_recipe_ids.push("SAFE_SAME_CHAT_RELAY");
  } else if (c==="THREAD_LOCAL") {
    add("capture durable incident+context packet","package fresh-thread bootstrap","rehydrate from True Memory","repeat exact parent operation once");
    verify("same operation succeeds","current pointers and parent objective preserved");
    base.executable_safe_recipe_ids.push("SAFE_CONTEXT_REHYDRATE");
  } else if (c==="TOOL_EXPOSURE" || c==="SCHEMA_RUNTIME") {
    add("capture schema/exposure evidence","run independent provider probe","use already-qualified alternate if parent work must continue");
    verify("primary action succeeds OR qualified failover completes equivalent operation");
    base.executable_safe_recipe_ids.push("SAFE_QUALIFIED_FAILOVER");
  } else if (c==="INSTALL_CONTROL_PLANE") {
    add("do not reinstall blindly","compare control-plane views","confirm provider/backend independently","reconnect only if auth/install evidence requires it");
    verify("control-plane converges OR provider/failover capability remains proven");
  } else if (c==="AUTH_OAUTH") {
    add("preserve state","attempt supported non-destructive refresh if available","request exactly one minimal human reconnect only if irreducible");
    verify("profile/read probe","required write semantics if applicable");
  } else if (c==="PERMISSION") {
    add("read current scopes/policy","identify minimum missing permission","do not expand privileges speculatively");
    verify("previously denied bounded action succeeds","no unrelated privilege expansion");
  } else if (c==="RATE_LIMIT_QUOTA") {
    add("bounded backoff","avoid duplicate side effects","use qualified alternate if policy allows");
    verify("retry or alternate completes exactly once");
    base.executable_safe_recipe_ids.push("SAFE_BOUNDED_RETRY");
  } else if (c==="DEPLOYMENT_RUNTIME") {
    add("recover fresh owned runtime if already authorized","rehydrate state from durable source","do not assume reclaimed ephemeral session persists");
    verify("health","state recovery","parent capability resumes");
  } else if (c==="STATE_MEMORY_POINTER") {
    add("quarantine stale pointer","resolve authoritative source directly","repair projection only after source verification");
    verify("authoritative source current","pointer read-back matches source locator/revision");
  } else if (["DATA_INTEGRITY","AUTHORITY_GOVERNANCE"].includes(c)) {
    add("fail closed","preserve evidence","route to Agent+True Version before mutation");
    verify("no further side effects","integrity/authority invariant restored");
  } else {
    add("preserve incident evidence","run smallest discriminating probe","continue parent work only through qualified safe path","route uncertainty to True Research");
    verify("capability resumes OR blocker is explicitly classified");
  }
  return base;
}

export function buildLearningCandidate(episode) {
  const verified=episode.verification?.status==="PASS";
  const recurring=(episode.contextual_diagnosis?.similar_incidents||[]).length>=1;
  const useful=verified || recurring || episode.refined_diagnosis?.failure_class==="UNKNOWN";
  if (!useful) return null;
  return {
    learning_candidate_id:id("LRN"),
    doctor_id:DOCTOR_ID,
    incident_id:episode.incident.incident_id,
    created_at:now(),
    failure_class:episode.refined_diagnosis?.failure_class || episode.contextual_diagnosis?.failure_class,
    recurring,
    verified_outcome:episode.verification?.status || "UNKNOWN",
    proposal_type: recurring ? "PATTERN_OR_RECIPE_UPDATE" : "REGRESSION_FIXTURE_OR_RESEARCH",
    evidence_refs:unique([
      ...(episode.incident.evidence_refs||[]),
      ...(episode.probe_receipts||[]).flatMap(x=>x.evidence_refs||[])
    ]),
    authority:"PROPOSAL_ONLY",
    next_owner:"ND Automation Agent"
  };
}

export function doctorStart(input={}, contextInput={}) {
  const invocation=createInvocationEnvelope(input);
  const context=createContextSnapshot(contextInput);
  const incident=createIncidentEnvelope(input,invocation);
  const preliminary=classifyIncident(incident);
  const contextual=contextualizeDiagnosis(incident,preliminary,context);
  const probe_plan=planProbes(incident,contextual,context,{
    max_probes: input.max_probes ?? 4,
    allow_reversible_qualification_write:
      Boolean(invocation.authority_context?.reversible_qualification_write)
  });
  return {
    doctor_id:DOCTOR_ID,
    doctor_version:DOCTOR_VERSION,
    contract_version:CONTRACT_VERSION,
    invocation,
    incident,
    context_revision:context.context_revision,
    contextual_diagnosis:contextual,
    probe_plan,
    probe_receipts:[],
    phase:"PROBE",
    mutations:false
  };
}

export function doctorObserve(episode, probeReceipts=[]) {
  const receipts=[...(episode.probe_receipts||[]),...probeReceipts];
  const refined=refineDiagnosis(episode.incident,episode.contextual_diagnosis,receipts);
  const route=repairRoute(episode.incident,refined,{
    expected_profiles: refined.expected_profile ? [refined.expected_profile] : []
  });
  return {
    ...episode,
    probe_receipts:receipts,
    refined_diagnosis:refined,
    repair_plan:route,
    phase:"PLAN_REPAIR",
    mutations:false
  };
}

export function doctorFinalize(episode, outcome={}) {
  const verification={
    status:outcome.verification_status || "UNKNOWN",
    checks:outcome.verification_checks || [],
    evidence_refs:outcome.evidence_refs || [],
    parent_objective_status:outcome.parent_objective_status || "UNKNOWN",
    finished_at:now()
  };
  const finished={
    ...episode,
    repair_outcome:outcome.repair_outcome || null,
    verification,
    phase:"COMPLETE",
    finished_at:now()
  };
  return {...finished,learning_candidate:buildLearningCandidate(finished)};
}

export async function runPlannedProbes(episode, adapter={}, options={}) {
  const max=options.max_probes ?? episode.probe_plan.length;
  const receipts=[];
  for (const spec of episode.probe_plan.slice(0,max)) {
    const fn=adapter[spec.adapter_method];
    if (typeof fn!=="function") {
      receipts.push(createProbeReceipt(spec,{status:"UNAVAILABLE",observed:"adapter method not available"}));
      continue;
    }
    if (spec.mutation_class!=="NONE" &&
        !episode.invocation.authority_context?.reversible_qualification_write) {
      receipts.push(createProbeReceipt(spec,{status:"SKIPPED",observed:"mutation authority absent"}));
      continue;
    }
    try {
      const result=await fn({episode,spec});
      receipts.push(createProbeReceipt(spec,result||{}));
    } catch (e) {
      receipts.push(createProbeReceipt(spec,{status:"FAIL",ok:false,error:String(e?.message||e)}));
    }
  }
  return doctorObserve(episode,receipts);
}

export async function executeSafeRecipe(episode, recipeId, adapter={}) {
  const allowed=episode.repair_plan?.executable_safe_recipe_ids || [];
  if (!allowed.includes(recipeId))
    return {status:"DENIED",reason:"recipe not authorized for this diagnosis",mutated:false};
  if (!episode.invocation.authority_context?.safe_recipe_execution)
    return {status:"DENIED",reason:"invocation authority forbids safe-recipe execution",mutated:false};

  const map={
    SAFE_BOUNDED_RETRY:"boundedRetry",
    SAFE_CONTEXT_REHYDRATE:"contextRehydrate",
    SAFE_QUALIFIED_FAILOVER:"qualifiedFailover",
    SAFE_SAME_CHAT_RELAY:"sameChatRelay"
  };
  const fn=adapter[map[recipeId]];
  if (typeof fn!=="function")
    return {status:"UNAVAILABLE",reason:"repair adapter missing",mutated:false};

  const result=await fn({episode,recipe_id:recipeId,idempotency_key:episode.incident.correlation_id});
  return {
    status:result?.ok===true?"PASS":"FAIL",
    recipe_id:recipeId,
    idempotency_key:episode.incident.correlation_id,
    mutated:Boolean(result?.mutated),
    observed:result?.observed||null,
    evidence_refs:result?.evidence_refs||[]
  };
}

export function doctorStatus(contextInput={}) {
  const context=createContextSnapshot(contextInput);
  return {
    doctor_id:DOCTOR_ID,
    doctor_version:DOCTOR_VERSION,
    field_ready:true,
    modes:[...INVOCATION_MODES],
    shared_context:true,
    context_revision:context.context_revision,
    recent_incidents:context.recent_incidents.length,
    patterns:context.patterns.length,
    repair_recipes:context.repair_recipes.length,
    expected_profiles:context.expected_profiles.length,
    broad_autonomous_mutation:false,
    next_maturity_gate:"v0.4 same-chat repair bridge field qualification"
  };
}
