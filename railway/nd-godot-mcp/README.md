# ND Godot MCP — cloud developer runtime

Purpose: give ChatGPT/ND full Godot developer access without depending on a
user computer.

## Architecture

- **Durable source authority:** GitHub.
- **Engine execution:** Godot 4.7.2 Mono in Railway.
- **Developer interface:** pinned `blentz/godot-mcp`.
- **Private transport:** OpenAI Secure MCP Tunnel (outbound HTTPS only).
- **Visual verification:** Xvfb provides a virtual 1920×1080 display.
- **Media tooling:** FFmpeg is installed for generated-video conversion.

The Godot-MCP working copy is disposable. Durable project changes are committed
through the existing GitHub write route, then re-qualified against Godot.
This prevents the cloud editor from becoming a competing source of truth.

## Capability tiers

- Tier A — structural read/write of scenes/resources/scripts/project config.
- Tier B — real Godot headless execution, validation and .NET reserve.
- Tier C — live editor bridge via a headless editor process.
- Tier D — render/screenshot tools through Xvfb.

## Required runtime variables

The service can boot without these and reports `WAITING_FOR_TUNNEL_CONFIG`.

- `CONTROL_PLANE_TUNNEL_ID`
- `CONTROL_PLANE_API_KEY` — OpenAI Platform runtime key with Tunnels Read + Use.

Optional:

- `BLUE_SEA_REPO_URL`
- `BLUE_SEA_BRANCH` (default: `main`)
- `BLUE_SEA_PROJECT_REL` (default: `sinee-more-godot`)

Do not expose the service through a Railway public domain. Secure MCP Tunnel is
the only intended remote transport.
