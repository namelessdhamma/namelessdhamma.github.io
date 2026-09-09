# ND integration policy — zero recurring cost by default

Effective: 2026-09-09

For ND external integrations and automation infrastructure, the default admissibility gate is **zero expected recurring infrastructure cost**.

Priority order:

1. Native ChatGPT/OpenAI plugin or direct provider integration already included in an existing plan.
2. Direct MCP/API using a provider-native free tier with no expected recurring charge.
3. Small custom adapter on a provider-native Always Free/serverless free tier, configured to scale to zero where possible.
4. Existing already-paid or already-free infrastructure, only when it does not add a new recurring charge.
5. Paid middleware/runtime (n8n Cloud, Make, Railway paid resources, external hosted gateways, paid IP/NAT/load-balancer components) only after an explicit human decision that no sufficiently reliable zero-cost path exists and the paid path is economically justified.

Before creating a new integration component, verify:

- whether a direct/native ChatGPT Plugin/App exists;
- whether a direct MCP exists;
- whether an official API exists;
- whether a custom adapter can use a true free tier;
- whether any hidden always-on charge exists (external IPv4, NAT, minimum instances, storage, egress, secret access, build/image storage, tunnel/domain fee);
- whether the expected usage can remain within published free quotas.

A billing account or payment method required only to activate an Always Free quota is **not itself evidence of a recurring cost**, but the deployment must not intentionally create paid-only resources. Where possible, scripts should fail closed if a paid networking/runtime component appears unexpectedly.

If a zero-cost design is materially less reliable than a paid orchestration service, report that trade-off explicitly instead of silently accepting recurring cost.

Current NotebookLM target:

`ChatGPT -> OpenAI Secure MCP Tunnel -> Google Compute Engine e2-micro (Free Tier, IPv6-only, no external IPv4) -> notebooklm-py -> NotebookLM`

The current deployment is pinned to `notebooklm-py==0.8.2` until separately requalified.
