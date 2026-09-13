// ND True Doctor v0.1 — deterministic incident classifier and bounded repair router.
// Qualification artifact. No global WorkItem authority and no canonical mutation authority.

export const DOCTOR_VERSION = "0.1.0";

export const FAILURE_CLASSES = Object.freeze([
  "TOOL_EXPOSURE",
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

const norm = v => String(v ?? "").toLowerCase();
const has = (s, ...xs) => xs.some(x => s.includes(x));

export function classifyIncident(i = {}) {
  const blob = norm([
    i.error_signature, i.observed_state, i.expected_state, i.provider,
    i.surface, i.notes, i.runtime_error
  ].filter(Boolean).join(" | "));

  const signals = [];

  if (has(blob, "tool not found", "schema/runtime", "schema exposed", "runtime missing"))
    signals.push(["SCHEMA_RUNTIME", 0.96, "tool/schema advertised but runtime action missing"]);

  if (has(blob, "not_installed", "installed/enabled", "control-plane", "install state"))
    signals.push(["INSTALL_CONTROL_PLANE", 0.90, "installation/control-plane states diverge"]);

  if (has(blob, "not exposed", "missing tool", "tool absent", "unavailable in this chat"))
    signals.push(["TOOL_EXPOSURE", 0.88, "expected tool is absent from active execution surface"]);

  if (has(blob, "401", "unauthorized", "oauth", "refresh token", "invalid_grant"))
    signals.push(["AUTH_OAUTH", 0.93, "authentication/session evidence"]);

  if (has(blob, "403", "permission denied", "insufficient_scope", "forbidden"))
    signals.push(["PERMISSION", 0.90, "permission/scope evidence"]);

  if (has(blob, "429", "rate limit", "quota", "too many requests"))
    signals.push(["RATE_LIMIT_QUOTA", 0.95, "rate/quota evidence"]);

  if (has(blob, "timeout", "network", "connection reset", "dns", "econn", "socket"))
    signals.push(["NETWORK_PATH", 0.72, "network/transport symptom"]);

  if (has(blob, "about:blank", "reclaim", "session lost", "process exited", "deployment unhealthy"))
    signals.push(["DEPLOYMENT_RUNTIME", 0.86, "runtime/session lifecycle evidence"]);

  if (has(blob, "old thread", "new thread works", "thread-local", "existing thread"))
    signals.push(["THREAD_LOCAL", 0.94, "thread-local divergence evidence"]);

  if (has(blob, "android", "mobile", "web works", "desktop works", "surface"))
    signals.push(["SURFACE", 0.66, "surface-specific evidence; verify before concluding"]);

  if (has(blob, "read works", "write fails", "read pass", "write denied"))
    signals.push(["WRITE_ONLY", 0.91, "read/write asymmetry"]);

  if (has(blob, "stale pointer", "missing pointer", "statehead mismatch", "registry mismatch"))
    signals.push(["STATE_MEMORY_POINTER", 0.92, "state/pointer integrity evidence"]);

  if (has(blob, "duplicate write", "hash mismatch", "corrupt", "data loss"))
    signals.push(["DATA_INTEGRITY", 0.96, "data integrity evidence"]);

  if (has(blob, "authority", "unauthorized mutation", "scope violation"))
    signals.push(["AUTHORITY_GOVERNANCE", 0.93, "authority boundary evidence"]);

  if (has(blob, "provider down", "backend 5", "service unavailable", "upstream"))
    signals.push(["PROVIDER_BACKEND", 0.76, "provider/backend symptom; independent probe required"]);

  if (has(blob, "registry pressure", "collision", "custom mcp", "apps disappear"))
    signals.push(["TOOL_COLLISION_REGISTRY_PRESSURE", 0.78, "tool-registry collision hypothesis"]);

  if (!signals.length) return {
    failure_class: "UNKNOWN",
    confidence: 0.35,
    rationale: "no deterministic signature matched",
    alternatives: [],
    next_probe: "collect exact error, expected capability, surface/thread/model, provider probe and last-known-good"
  };

  signals.sort((a,b) => b[1]-a[1]);
  const [failure_class, confidence, rationale] = signals[0];
  return {
    failure_class,
    confidence,
    rationale,
    alternatives: signals.slice(1,4).map(([c,p,r]) => ({failure_class:c,confidence:p,rationale:r})),
    next_probe: discriminatingProbe(failure_class)
  };
}

export function discriminatingProbe(failureClass) {
  switch (failureClass) {
    case "SCHEMA_RUNTIME":
      return "compare exposed schema with one exact runtime invocation; repeat in fresh thread/surface before provider conclusions";
    case "INSTALL_CONTROL_PLANE":
      return "compare catalog/dependency/permission state, then run direct backend/profile probe";
    case "TOOL_EXPOSURE":
      return "same exact operation in affected thread and fresh thread with model/surface held constant";
    case "AUTH_OAUTH":
      return "provider-auth/profile probe without reconnect; reconnect only if auth evidence confirms";
    case "PERMISSION":
      return "read current scopes/policy and run minimal denied/allowed action pair";
    case "THREAD_LOCAL":
      return "fresh-thread canary with same model/surface and same operation";
    case "SURFACE":
      return "same-thread or equivalent operation on Android/web/desktop with model held constant";
    case "WRITE_ONLY":
      return "read probe then reversible qualification-resource write/read-back";
    case "PROVIDER_BACKEND":
      return "independent provider/API health probe outside ChatGPT tool exposure";
    case "DEPLOYMENT_RUNTIME":
      return "fresh runtime/session plus recovery-state verification; distinguish continuity from post-reclaim recovery";
    case "RATE_LIMIT_QUOTA":
      return "read provider quota/rate status and retry only after bounded backoff";
    case "STATE_MEMORY_POINTER":
      return "resolve authoritative source directly and compare current revision/hash to pointer";
    default:
      return "run smallest independent probe that separates ChatGPT surface/tool state from provider/backend state";
  }
}

export function repairRoute(i = {}, diagnosis = classifyIncident(i)) {
  const c = diagnosis.failure_class;
  const base = {
    failure_class: c,
    diagnosis_confidence: diagnosis.confidence,
    mutation_allowed: false,
    authority_required: "Agent assignment for material mutation; local bounded safe recovery may execute within existing authority",
    actions: [],
    verification: [],
    terminal_if_unrepairable: "UPSTREAM_ONLY_OR_QUALIFIED_FAILOVER"
  };

  const add = (...xs) => base.actions.push(...xs);
  const verify = (...xs) => base.verification.push(...xs);

  switch (c) {
    case "THREAD_LOCAL":
      add("capture incident", "rehydrate minimum context", "migrate to fresh thread", "reuse same primary provider if healthy");
      verify("same operation succeeds in fresh thread", "context pointers/currentness preserved");
      break;
    case "SURFACE":
      add("capture exact client/model/surface", "switch to already-qualified surface only if needed", "do not infer global unsupported state");
      verify("same operation succeeds on alternate surface", "return-path documented");
      break;
    case "TOOL_EXPOSURE":
    case "SCHEMA_RUNTIME":
      add("capture expected vs exposed schema", "run fresh-thread canary", "use qualified independent path if parent work must continue");
      verify("runtime tool call succeeds OR incident is classified upstream-only while failover continues");
      break;
    case "INSTALL_CONTROL_PLANE":
      add("do not reinstall blindly", "probe live provider/backend", "compare control-plane states", "reselect/reconnect only if evidence identifies install/auth fault");
      verify("catalog/control-plane state converges OR live path remains proven and divergence is documented");
      break;
    case "AUTH_OAUTH":
      add("preserve state", "attempt supported token/session refresh if available", "request one minimal human reconnect only if irreducible");
      verify("profile/read probe", "required write probe if applicable");
      break;
    case "PERMISSION":
      add("read current policy/scopes", "apply smallest allowed permission correction within authority");
      verify("previously denied bounded action succeeds", "no privilege expansion beyond requirement");
      break;
    case "RATE_LIMIT_QUOTA":
      add("bounded backoff", "switch to qualified provider/path if available", "avoid duplicate side effects");
      verify("request succeeds or failover succeeds", "quota state recorded");
      break;
    case "DEPLOYMENT_RUNTIME":
      add("start/recover fresh runtime", "rehydrate state from durable source", "do not assume reclaimed session persistence");
      verify("health probe", "state recovery probe", "parent capability resumes");
      break;
    case "STATE_MEMORY_POINTER":
      add("quarantine stale pointer", "resolve authoritative source", "repair projection/navigation after source verification");
      verify("source exists/current", "pointer read-back matches authoritative locator/revision");
      break;
    case "DATA_INTEGRITY":
    case "AUTHORITY_GOVERNANCE":
      add("fail closed", "preserve evidence", "require Agent/Version review before mutation");
      verify("no further side effects", "authority/data invariant restored");
      break;
    default:
      add("capture incident", "run diagnosis next_probe", "use already-qualified failover if available", "escalate uncertainty to True Research");
      verify("capability resumes OR blocker is explicitly classified");
  }
  return base;
}

export function createIncidentEnvelope(input = {}) {
  return {
    incident_id: input.incident_id || null,
    detected_at: input.detected_at || new Date().toISOString(),
    detected_by: input.detected_by || "true-doctor",
    system: input.system || "unknown",
    supervisor: input.supervisor || "unknown",
    capability: input.capability || "unknown",
    expected_state: input.expected_state || "",
    observed_state: input.observed_state || "",
    error_signature: input.error_signature || "",
    severity: input.severity || "MEDIUM",
    surface: input.surface || "",
    model: input.model || "",
    thread_or_run: input.thread_or_run || "",
    client_version: input.client_version || "",
    provider: input.provider || "",
    evidence_refs: input.evidence_refs || [],
    current_status: "CAPTURED",
    root_cause_status: "UNKNOWN"
  };
}

export function doctorDiagnose(input = {}) {
  const incident = createIncidentEnvelope(input);
  const diagnosis = classifyIncident(incident);
  return {
    doctor_version: DOCTOR_VERSION,
    mode: "DIAGNOSE",
    incident,
    diagnosis,
    health: diagnosis.failure_class === "UNKNOWN" ? "UNKNOWN" : "DEGRADED",
    mutations: false,
    routing: {
      research: diagnosis.confidence < 0.85 || diagnosis.failure_class === "UNKNOWN",
      developer: false,
      writer: true,
      memory: true,
      version: false,
      agent_workitem_required: false
    }
  };
}

export function doctorRepair(input = {}) {
  const incident = createIncidentEnvelope(input);
  const diagnosis = classifyIncident(incident);
  const repair = repairRoute(incident, diagnosis);
  return {
    doctor_version: DOCTOR_VERSION,
    mode: "REPAIR",
    incident,
    diagnosis,
    repair,
    mutations: false,
    note: "v0.1 returns bounded repair routing; side-effect execution is delegated to already-authorized tools/True Developer/Agent.",
    routing: {
      research: diagnosis.confidence < 0.85 || diagnosis.failure_class === "UNKNOWN",
      developer: repair.actions.some(a => /config|runtime|permission|reconnect|repair/i.test(a)),
      writer: true,
      memory: true,
      version: ["DATA_INTEGRITY","AUTHORITY_GOVERNANCE"].includes(diagnosis.failure_class),
      agent_workitem_required: repair.actions.some(a => /require Agent|permission correction|fresh runtime/i.test(a))
    }
  };
}
