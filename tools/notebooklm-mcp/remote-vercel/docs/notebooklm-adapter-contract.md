# NotebookLM Adapter Contract — Stage B

Date: 2026-09-10
Status: runtime-feasibility design, no secrets provisioned

## Decision

Use the already-qualified Node/TypeScript Streamable HTTP MCP as the ChatGPT-facing transport and evaluate a separate Python provider adapter for NotebookLM itself.

Preferred provider backend: `notebooklm-py==0.8.2` with `backend="android"`.

Important: "Android backend" here names the NotebookLM native mobile gRPC protocol. It does **not** require an Android device. The library explicitly positions this backend for unattended CI, containers, and long-running services.

## Why this backend is preferred

`notebooklm-py` 0.8.2 added a native gRPC backend which:

- mints short-lived OAuth bearer tokens on demand from `master_token.json`;
- avoids browser-cookie session expiry and browser re-login;
- avoids NotebookLM Web build labels, obfuscated Web RPC ids, and positional `batchexecute` decoding;
- exposes all eleven public API namespaces without falling back to Web transport;
- is specifically documented as a better fit for unattended CI/containers;
- requires only the durable master token at runtime.

This is materially better for a scale-to-zero/serverless runtime than reproducing the Web backend.

## Stage-B interface

The MCP-facing operation remains deliberately narrow:

```text
notebook_list()
```

Provider adapter contract:

```text
list_notebooks() -> normalized array of
{
  id: string,
  title: string,
  ...minimum stable metadata only
}
```

The MCP layer must not expose raw gRPC/provider payloads.

## Runtime construction

Canonical provider call pattern:

```python
from notebooklm import NotebookLMClient

async with NotebookLMClient.from_storage(
    profile="default",
    backend="android",
) as client:
    notebooks = await client.notebooks.list()
```

The library does not accept a raw public `master_token=` constructor parameter. It expects a profile-backed `master_token.json`.

Therefore the serverless adapter must reconstruct an ephemeral profile from managed secret input before opening the client.

Conceptual request lifecycle:

```text
Vercel managed secret
    -> ephemeral profile/master_token.json
    -> NotebookLMClient.from_storage(..., backend="android")
    -> short-lived bearer minted in-process
    -> client.notebooks.list()
    -> normalized response
    -> ephemeral request state discarded
```

No browser or cookie snapshot is part of this route.

## Secret contract

Expected managed secret name:

```text
NOTEBOOKLM_MASTER_TOKEN_JSON
```

The value is the exact JSON contents of the already-qualified `master_token.json`.

Rules:

- never commit the value to Git;
- never place it in `qualification-state.json`;
- never print/log the value;
- never include it in exception text or MCP tool results;
- write it only to an ephemeral profile file required by `notebooklm-py`;
- set file permissions to owner-only where supported;
- delete/overwrite temporary credential material at request end where useful, while treating serverless instance storage as ephemeral rather than durable state;
- if the secret is absent, fail closed with a sanitized configuration error.

The master token is a durable full-account Google credential. Treat compromise as equivalent to a password-level incident.

## Runtime split

### Frontend transport

Existing Node function:

```text
/api/mcp
```

Responsibilities:

- MCP protocol;
- tool schemas;
- ChatGPT-facing authentication boundary;
- input validation;
- sanitized tool results.

### Provider adapter

Candidate Vercel Python function:

```text
/api/notebooklm/list
```

Responsibilities:

- reconstruct ephemeral NotebookLM profile;
- select `backend="android"`;
- mint bearer credentials;
- call NotebookLM;
- normalize output;
- map provider failures to sanitized categories.

The provider function must not become an unauthenticated public data endpoint in production. During runtime feasibility tests, expose only harmless import/capability probes and no user data.

## Dependency target

Runtime-feasibility probe should first try:

```text
notebooklm-py[android]==0.8.2
```

The important difference from the failed Termux build is platform ABI:

- Termux/Android lacked compatible wheels for parts of the FastMCP/watchfiles path and triggered a very long native Rust build;
- Vercel Python executes on standard Linux serverless infrastructure, where `grpcio` and related Python dependencies normally have Linux wheels;
- the Stage-B provider adapter does **not** require the `mcp` extra or FastMCP at all, because the MCP protocol is already handled by the Node layer.

Thus the heavy Termux failure path is structurally removed.

## Runtime-feasibility gates before provisioning Google secret

1. Vercel can build a Python function in the same project or an adjacent provider-adapter deployment.
2. `notebooklm-py==0.8.2` imports successfully.
3. Android-backend dependencies (`grpcio`, `protobuf`, `gpsoauth`) import successfully.
4. `NotebookLMClient.from_storage(..., backend="android")` can be constructed without performing authentication I/O.
5. Function cold start remains within acceptable interactive latency.
6. Function bundle stays within Vercel Hobby limits.
7. No FastMCP/watchfiles/maturin/Rust compilation is required.

Only after all seven pass should the Google master token be provisioned.

## Stage-B live qualification after secret provisioning

1. Reconstruct profile from managed secret.
2. Call `notebook_list()`.
3. Verify the expected account/notebook set.
4. Invoke again after an idle/cold start.
5. Verify bearer re-mint/reconstruction works with no browser.
6. Verify no raw credential appears in Vercel logs or MCP output.
7. Deliberately test missing/invalid-secret failure and confirm sanitization.

## Stage-C extension

Only after Stage B passes, add:

```text
notebook_create(title)
```

Then perform create -> independent list -> ID/title read-back, followed by cold-start repetition.

## Evidence basis

- `notebooklm-py` 0.8.2 changelog: Android backend designed for unattended CI/containers and bearer minting from master token.
- library configuration docs: explicit `backend="android"`; profile-backed `master_token.json` is mandatory; construction itself does not read credentials until client open/context entry.
- Python API docs: canonical `NotebookLMClient.from_storage()` async context-manager pattern.
- Vercel docs: Python Functions support dependency installation from `requirements.txt`/`pyproject.toml` and serverless execution alongside the deployed application architecture.
