# ND NotebookLM Remote MCP Design

Date: 2026-09-10
Status: approved architecture, implementation specification
Branch: `notebooklm-remote-mcp`

## Goal

Replace the current browser/Cloud-Shell/Android-dependent NotebookLM transport with a phone-independent remote MCP architecture that ChatGPT can call directly over Streamable HTTP, with expected recurring infrastructure cost of $0.

NotebookLM is the reference integration for a reusable Nameless Dhamma direct-integration runtime pattern.

## Established baseline

The following is treated as already qualified evidence and is not re-litigated in this implementation:

- consumer NotebookLM is reachable from ChatGPT through the existing custom MCP integration;
- `notebooklm-py` 0.8.2 successfully authenticated the intended Google account and passed notebook list, create, and independent read-after-write tests;
- the current Secure MCP Tunnel topology works while its private runtime remains alive;
- Cloud Shell is ephemeral and therefore not a persistent production runtime;
- Android/Termux is retained as a separate backup path, but the first bootstrap path failed operationally because FastMCP/watchfiles/maturin triggered a very long native Rust build;
- the primary architecture must not depend on the user's Android device, browser session, n8n, Make, or Railway;
- zero expected recurring infrastructure cost is the default requirement.

## Primary architecture

```text
ChatGPT custom MCP app
        |
        | Streamable HTTP
        v
ND remote MCP endpoint
        |
        | HTTPS calls / NotebookLM adapter
        v
consumer NotebookLM
```

The primary path does not use OpenAI Secure MCP Tunnel. The tunnel remains relevant only to private/local fallback runtimes.

The remote endpoint should execute on demand and may scale to zero between requests. No always-on user-owned machine is required.

## Why this architecture

OpenAI currently documents that ChatGPT connects to remote MCP servers directly. Local/private MCP servers need Secure MCP Tunnel, which means a public remote MCP endpoint removes the structural requirement for a continuously running tunnel client.

Cloudflare currently documents stateless remote MCP servers over Streamable HTTP using `createMcpHandler()`, which is a suitable first transport qualification target.

The implementation deliberately separates two questions:

1. Can ChatGPT reliably discover and invoke a phone-independent remote MCP endpoint?
2. Can the NotebookLM adapter and authentication lifecycle fit inside a free on-demand host?

Transport is qualified before any Google secret is moved.

## Implementation stages

### Stage A — Remote MCP transport qualification

Build a minimal stateless MCP server exposing only:

```text
nd_ping()
```

Expected result:

```json
{
  "ok": true,
  "service": "nd-notebooklm-remote-mcp",
  "mode": "transport-qualification"
}
```

No Google credentials, NotebookLM state, or OpenAI tunnel credentials are present in Stage A.

Qualification gates:

1. deploy the endpoint on a zero-cost remote host;
2. endpoint is reachable at `/mcp` over HTTPS;
3. ChatGPT `Scan Tools` succeeds;
4. ChatGPT discovers `nd_ping`;
5. ChatGPT successfully calls `nd_ping`;
6. repeat the call after host idle/cold-start conditions;
7. redeploy/restart and repeat discovery/call;
8. no Android, browser process, or Secure MCP Tunnel is involved.

Stage A PASS proves the remote transport architecture.

### Stage B — NotebookLM read-only adapter

After Stage A passes, expose a minimal NotebookLM operation first:

```text
notebook_list()
```

Do not mirror the entire `notebooklm-py` MCP surface immediately. Reuse the smallest provider behavior required for authenticated list/read operations.

Requirements:

- NotebookLM auth material is stored only as managed deployment secrets;
- no secret appears in Git, logs, error messages, tool output, or ChatGPT prompts;
- the runtime reconstructs the required NotebookLM session headlessly when invoked;
- auth survives scale-to-zero/cold start;
- failures are explicit and bounded rather than silently falling back to browser automation.

Qualification gates:

1. runtime can reconstruct NotebookLM auth from managed secret state;
2. `notebook_list` returns the expected account data;
3. cold-start invocation returns the same account;
4. auth refresh/reconstruction works after idle;
5. no user interaction is required after the initial secret provisioning.

### Stage C — Bounded write/read-back

Add one write operation only after read-only qualification:

```text
notebook_create(title)
```

Qualification:

1. create a clearly marked test notebook;
2. capture returned notebook ID;
3. invoke `notebook_list` independently;
4. verify the same notebook ID/title appears;
5. delete the test object if a safe delete path is available, otherwise leave it clearly named as a qualification artifact;
6. repeat after cold start.

No broad write surface is exposed before this passes.

### Stage D — Production tool surface

Only after Stages A–C pass, add the minimum useful NotebookLM operations required by ND. Tool design follows capability needs, not the upstream library's complete schema.

Initial likely groups:

- notebook discovery/read;
- notebook creation/update where materially useful;
- source management;
- grounded NotebookLM query/chat;
- artifact generation where supported and qualified.

Each write-capable tool receives an explicit safety/confirmation classification before production adoption.

## Hosting strategy

### First qualification host: Cloudflare Workers Free

Use Cloudflare first because it currently provides first-class remote MCP documentation and stateless Streamable HTTP handling.

This is a qualification target, not a production assumption.

Known constraints to test:

- Workers Free request quota is sufficient for qualification;
- free-plan CPU time is very small, while network wait does not consume CPU in the same way;
- memory is bounded;
- NotebookLM adapter logic may not fit if it requires a heavy Python/FastMCP runtime;
- therefore Stage A uses a small TypeScript server with no Python stack.

If Cloudflare passes Stage A but fails Stage B due runtime/CPU/library constraints, retain the same remote Streamable HTTP architecture and move only the host or adapter implementation.

## Adapter strategy

Do not attempt to run the full Android/Cloud-Shell Python MCP stack unchanged inside every host.

Preferred order:

1. reuse a minimal portion of `notebooklm-py` behavior if the host supports it cleanly;
2. otherwise implement a small runtime-native NotebookLM adapter using the already-qualified authentication/session knowledge;
3. use a heavier container/runtime only if the protocol cannot be reproduced safely in a lighter worker.

FastMCP is not an architectural requirement. It was an implementation choice of the local Python server and must not be carried into the remote design unless it provides material value.

## Authentication and secret model

Two independent authentication layers must not be confused:

1. ChatGPT -> remote MCP endpoint authentication;
2. remote MCP -> Google/NotebookLM authentication.

Stage A may temporarily use an unauthenticated endpoint because it exposes only harmless `nd_ping` and contains no user data.

Before Stage B, the endpoint must not remain openly callable with access to NotebookLM credentials. Use the minimum supported secure authentication mechanism appropriate to the selected host and ChatGPT MCP configuration.

Google NotebookLM auth material is treated as high-sensitivity full-account credential material. It must only be provisioned through managed secret input and never committed to Git.

## State model

The remote MCP server should remain protocol-stateless wherever possible.

Durable state is limited to what is genuinely required:

- encrypted/managed credential material;
- optional minimal auth/session cache if provider behavior requires it;
- qualification metadata/last-known-good version outside the request path;
- no conversational state in the MCP host.

GitHub remains the code/update/control plane, not the live credential store.

## Error handling

The server must distinguish at least:

- MCP protocol/validation error;
- host/runtime limitation;
- Google auth expired/invalid;
- NotebookLM upstream changed/broke;
- transient network/rate-limit failure;
- unsupported tool/action.

Errors returned to ChatGPT must be sanitized and must not include raw credentials, cookies, master tokens, request headers, or provider-internal sensitive payloads.

No automatic fallback to a browser or user device is performed by the primary runtime.

## Update and rollback

Keep version qualification conservative:

```text
candidate -> automated tests -> live canary -> qualified -> production
```

The existing qualified manifest currently records `notebooklm-py` 0.8.2 and tunnel-client v0.0.14 for the legacy/local path. The remote runtime receives its own versioned deployment state without replacing those backup-path records prematurely.

GitHub should be able to build/test/deploy candidate code, while the runtime should expose a harmless version/health response that can be verified after deployment.

Retain last-known-good deployment/version for rollback.

## Reuse for Nameless Dhamma

This implementation must avoid NotebookLM-specific infrastructure where unnecessary.

Reusable layers:

```text
ChatGPT
  -> remote MCP transport
  -> ND service adapter
  -> external provider
```

Future direct integrations should be able to reuse:

- Streamable HTTP MCP server pattern;
- deployment/update workflow;
- authentication boundary;
- secret handling conventions;
- health/version tool pattern;
- qualification ladder;
- rollback model.

Service-specific behavior stays inside each provider adapter.

## Non-goals

This implementation does not:

- make n8n/Make/Railway mandatory intermediaries;
- make Android the primary runtime;
- migrate Google credentials before transport-only qualification;
- expose the entire upstream NotebookLM MCP surface immediately;
- treat GitHub Actions as a permanent daemon host;
- promise that Cloudflare is the final host before live qualification.

## Success criteria

Primary architecture is production-qualified only when all are demonstrated:

- ChatGPT connects directly to the remote MCP endpoint;
- no Secure MCP Tunnel is required in the primary route;
- no Android/browser/user-owned always-on machine is required;
- expected recurring infrastructure cost is $0;
- idle/cold-start wake works;
- NotebookLM authenticated read works;
- bounded write/read-back works;
- credential reconstruction/refresh survives idle and redeployment as designed;
- secrets remain out of Git/logs/tool outputs;
- restart/redeploy recovery works;
- a last-known-good rollback path exists;
- the transport/deployment pattern is reusable for additional ND direct integrations.
