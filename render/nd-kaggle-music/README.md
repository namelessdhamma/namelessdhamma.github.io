# ND Private Kaggle Music Bridge

Scope: **FREE_ONLY**, **private Kaggle kernels**, ACE-Step music workflows. It is a thin CPU-only Render HTTPS control plane. This does **not** place GPU inference on Render, copy secrets from Railway, or modify the legacy ND LTX route.

Environment variables:
- `KAGGLE_API_TOKEN`: current Kaggle personal access token (must be configured **privately**, never committed to public source).
- `KAGGLE_USERNAME_SLUG`: Kaggle account handle (expected `savvasavchenko` only if verified by provider; optional, mismatches rejected).
- `ND_KAGGLE_BRIDGE_TOKEN`: random long bearer token protecting all control methods (set via authenticated Render secrets API).

API: `GET /health` unprivileged; authenticated `GET /v1/preflight`, `POST /v1/submit`, `POST /v1/reconcile`, `POST /v1/status`, `POST /v1/result`. Include `Authorization: Bearer <ND_KAGGLE_BRIDGE_TOKEN>`.

Submit JSON: `{ "idempotency_key":"niti-ace15-pilot-v3", "python_source":"<entire standalone Kaggle Python script>", "confirm_private":true }`. Source is sent via authenticated TLS to Render and directly forwarded to a private Kaggle kernel; Render does not store it. SHA-based deterministic slug prevents blind duplicate submits. Never include source or lyrics in the public GitHub repository, logs or URL.

Run context: Kaggle is free when quota permits; requires `NvidiaTeslaT4`, `isPrivate=true`, `enableInternet=true`, `SaveAndRunAll`. A 20-minute minimum GPU quota is enforced before submission. Request states are grounded in Kaggle, not Render memory. `SUBMIT_OUTCOME_UNKNOWN` means reconcile same effect before any reattempt; no new execution until effect state is resolved. Results currently provide Kaggle-managed temporary output URLs, not permanent storage.

Limitations: The Kaggle authenticated configuration and end-to-end GPU inference remain **unqualified** until a live token and real private T4 provider run are observed. Service probe is not proof of successful generation. Render free web services may sleep. Caller must supply the actual private Python script at runtime (use the approved v3 notebook's script), keep the model/lyrics private and inspect generated sound before claiming creative success.