# Linear OAuth2 Client Credentials Bootstrap

**Status**: Authorization boundary established (pending credential registration on Linear dashboard)

## Overview

This document guides the setup of an independent Linear OAuth2 client_credentials authorization boundary for `nd-external-intelligence`, using the existing `ND_LINEAR_API_KEY` for server-side validation while establishing a separate OAuth2 client identity for resilience and scope isolation.

### Configuration

| Component | Value | Status |
|-----------|-------|--------|
| **OAuth App Name** | ND Navigator Resilience | Pending creation |
| **Developer** | Nameless Dhamma | Configured |
| **Developer URL** | https://namelessdhamma.org | Configured |
| **Grant Types** | `authorization_code`, `client_credentials` | Specified |
| **Scopes** | `read`, `write` | Configured |
| **Redirect URI** | https://nd-external-intelligence-production.up.railway.app/linear/oauth/callback | Configured |

## Setup Instructions

### 1. Create OAuth App on Linear Dashboard

1. Go to **Linear Settings** → **API** → **OAuth Applications**
2. Click **Create Application**
3. Fill in details:
   - **Name**: `ND Navigator Resilience`
   - **Developer**: `Nameless Dhamma`
   - **Developer URL**: `https://namelessdhamma.org`
   - **Redirect URIs**: `https://nd-external-intelligence-production.up.railway.app/linear/oauth/callback`
4. Select grant types:
   - ✓ `authorization_code`
   - ✓ `client_credentials`
5. Select scopes:
   - ✓ `read` (read teams, issues, projects, etc.)
   - ✓ `write` (create/update issues, comments, projects, etc.)
6. **Save** and note the generated credentials

### 2. Extract and Register Credentials

From the Linear dashboard, copy:
- **Client ID** (visible in app list)
- **Client Secret** (shown only once—save immediately)
- **App ID** (from URL or app details)

### 3. Update Railway Variables

Set on `nd-external-intelligence` service (exact names required):

```bash
# Non-secret metadata (safe to version control / log)
ND_LINEAR_OAUTH_APP_ID=<app-id-from-linear>
ND_LINEAR_OAUTH_CLIENT_ID=<client-id-from-linear>
ND_LINEAR_OAUTH_SCOPE=read,write

# Secret (obtain from Linear, never version control or log)
ND_LINEAR_OAUTH_CLIENT_SECRET=<client-secret-from-linear>

# Reference (set automatically)
ND_LINEAR_OAUTH_REDIRECT_URI=https://nd-external-intelligence-production.up.railway.app/linear/oauth/callback
```

**Security**: `ND_LINEAR_OAUTH_CLIENT_SECRET` is the only sensitive credential. Set it only on Railway via the UI or secure CLI—never commit to git.

### 4. Verify Setup

After setting variables and deploying:

```bash
# Check OAuth app registration
curl https://nd-external-intelligence-production.up.railway.app/linear/oauth/status

# Verify team access and destructive mutations
curl https://nd-external-intelligence-production.up.railway.app/linear/health
```

Expected response (simplified):
```json
{
  "ok": true,
  "route": "railway_external_official_linear_mcp",
  "full_destructive_surface": true
}
```

## Implementation Details

### Token Flow

1. **Service to Linear (client_credentials)**:
   - Endpoint: `https://auth.linear.app/oauth/token`
   - Grant: `client_credentials`
   - Credentials: `ND_LINEAR_OAUTH_CLIENT_ID` + `ND_LINEAR_OAUTH_CLIENT_SECRET`
   - Response: Access token (no refresh needed)

2. **Service to Linear (direct API)**:
   - Existing: `ND_LINEAR_API_KEY` (personal API key, higher privilege)
   - New: OAuth client token (scoped, delegated, resilient)
   - Both routed through `/linear/*` endpoints in `drive_proxy.mjs`

### Scope Isolation

- **`read` scope**: Query teams, issues, projects, comments, documents, initiatives, releases
- **`write` scope**: Create/update issues, comments, projects, documents, and labels
- **Destructive operations** (delete, archive): Require additional `admin` or service-account level (via `ND_LINEAR_API_KEY`)

### Error Handling

| Scenario | Handling |
|----------|----------|
| Client secret missing | Return 503 with `oauth_client_secret_missing` |
| Token exchange fails | Retry with exponential backoff; fall back to `ND_LINEAR_API_KEY` |
| Scope insufficient | Return 403 with required scopes listed |
| Team not found | Return 404; verify team name in Linear |

## Security Model

### Credentials Boundary

| Credential | Storage | Exposure | Usage |
|-----------|---------|----------|-------|
| `ND_LINEAR_API_KEY` | Railway variable (hidden) | Never logged | Direct GraphQL, destructive ops, admin scope |
| `ND_LINEAR_OAUTH_CLIENT_ID` | Railway variable | Safe to log | OAuth token exchange, public in client requests |
| `ND_LINEAR_OAUTH_CLIENT_SECRET` | Railway variable (hidden) | Never logged | OAuth token exchange only (server-side) |
| `ND_LINEAR_OAUTH_SCOPE` | Railway variable | Safe to log | Token claims validation, scope advertisement |

### Redaction in Logs

All error messages and logs redact:
- `ND_LINEAR_API_KEY` → `[REDACTED]`
- `ND_LINEAR_OAUTH_CLIENT_SECRET` → `[REDACTED]`
- OAuth tokens (if logged) → `[REDACTED]`

## Verification Checklist

- [ ] Linear OAuth app created with correct name and developer info
- [ ] Client ID and Secret copied from Linear dashboard
- [ ] `ND_LINEAR_OAUTH_APP_ID` set on Railway
- [ ] `ND_LINEAR_OAUTH_CLIENT_ID` set on Railway
- [ ] `ND_LINEAR_OAUTH_CLIENT_SECRET` set on Railway (securely, via UI)
- [ ] `ND_LINEAR_OAUTH_SCOPE` = `read,write` confirmed
- [ ] Service redeployed after variable changes
- [ ] `/linear/health` endpoint returns `ok: true`
- [ ] `/linear/oauth/status` shows team access verified
- [ ] Destructive mutation test passed (see `linearFullSelftest()` in code)

## Maintenance

### Rotating Credentials

1. **Client Secret** (if compromised):
   - Linear Dashboard: Regenerate secret
   - Copy new secret
   - Update `ND_LINEAR_OAUTH_CLIENT_SECRET` on Railway
   - Redeploy

2. **OAuth App** (if deprecated):
   - Create new app with same config
   - Update `ND_LINEAR_OAUTH_CLIENT_ID` and secret on Railway
   - Deactivate old app on Linear dashboard

### Token Caching

OAuth tokens are cached in memory with 90-second refresh margin. No persistent token store is used; tokens are obtained on-demand.

## References

- **Linear OAuth Docs**: https://developers.linear.app/docs/oauth
- **Linear GraphQL API**: https://developers.linear.app/docs/graphql/working-with-the-graphql-api
- **Service Code**: `railway/nd-omniroute/drive_proxy.mjs` (search `linearPost`, `linearGraphql`, `handleLinearMcp`)

