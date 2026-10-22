# Kaggle Read-Only Diagnosis Guide

## Overview

This guide describes the read-only diagnostic tools for querying Kaggle API status, notebook sessions, and GPU quotas **without modifying any kernels or resources**.

## Tools Provided

### 1. CLI Script: `kaggle-read-only-diagnosis.mjs`

A Node.js script that queries Kaggle APIs and prints a human-readable diagnosis.

**Usage:**
```bash
node railway/nd-omniroute/kaggle-read-only-diagnosis.mjs
```

**Requirements:**
- `KAGGLE_API_TOKEN` environment variable set
- `KAGGLE_USERNAME_SLUG` (optional, for reference)

**Output:**
- Account information
- GPU quota (exhausted and available)
- All running/active/queued kernels (across entire account)
- Status of 5 specific kernels: nd-gpu-probe, nd-wangp-bootstrap, nd-wangp-i2v-qualification, nd-wangp-disk-fit, nd-sdcpp-flf-qualification
- Provider messages (if any blocking restrictions exist)
- Summary and recommendations

**Example Output:**
```
═══════════════════════════════════════════════════════════════════════════════
KAGGLE READ-ONLY DIAGNOSIS
═══════════════════════════════════════════════════════════════════════════════

📋 STEP 1: Account Information
────────────────────────────────────────────────────────────────────────────────
✓ Account: your-kaggle-username
  Tier: Premium
  Member since: 2023-01-15

💾 STEP 2: GPU Quota & Limits
────────────────────────────────────────────────────────────────────────────────
GPU Types: 3

✓ Available Quota (3):
  - P100: 20/40 hours remaining
  - T4: 100/100 hours remaining
  - V100: 5/10 hours remaining

🔍 STEP 3: All Running/Active/Queued Kernel Sessions
────────────────────────────────────────────────────────────────────────────────
Total kernels: 42
Running/Queued/Flushed: 0

✓ No kernels currently running, queued, or flushed.

🎯 STEP 4: Specific Kernel Status Check
────────────────────────────────────────────────────────────────────────────────
Checking 5 kernels...

  nd-gpu-probe... ✓ completed (GPU: none)
  nd-wangp-bootstrap... ⚠ NOT FOUND / ERROR: Kernel not found
  nd-wangp-i2v-qualification... ✓ completed (GPU: P100)
  nd-wangp-disk-fit... ✓ running (GPU: T4)
  nd-sdcpp-flf-qualification... ✓ completed (GPU: none)

⚠️  STEP 5: Provider Messages & 403 Blocking Factors
────────────────────────────────────────────────────────────────────────────────
✓ No active provider messages blocking operations.

📊 STEP 6: Diagnosis Summary
────────────────────────────────────────────────────────────────────────────────
✓ Total kernels: 42
✓ Any kernel running/queued/flushed: NO
✓ Checked kernels actively running: 0/5

✓ No checked kernels currently running (safe to create new SaveKernel)

═══════════════════════════════════════════════════════════════════════════════
```

### 2. HTTP Routes: `kaggle-diagnosis-route.mjs`

Exposes three read-only HTTP endpoints on your nd-external-intelligence service.

**Integration:**
In your main route handler, import and register:
```javascript
import { registerKaggleDiagnosisRoutes } from './kaggle-diagnosis-route.mjs';

// In your Hono app:
registerKaggleDiagnosisRoutes(app);
```

**Endpoints:**

#### `GET /kaggle/diagnosis`
Full JSON diagnosis with all details.

**Response:**
```json
{
  "timestamp": "2026-09-26T12:34:56.789Z",
  "account": {
    "username": "your-username",
    "tier": "Premium",
    "dateJoined": "2023-01-15"
  },
  "quota": {
    "types": 3,
    "exhausted": [],
    "available": [
      {
        "name": "P100",
        "remaining": 20,
        "total": 40
      }
    ],
    "all": [...]
  },
  "allKernels": {
    "total": 42,
    "active": 0,
    "list": []
  },
  "checkedKernels": {
    "nd-gpu-probe": {
      "status": "completed",
      "gpuType": "none",
      "dateTimeUpdated": "2026-09-20T10:00:00Z"
    },
    "nd-wangp-disk-fit": {
      "status": "running",
      "gpuType": "T4",
      "dateTimeUpdated": "2026-09-26T12:30:00Z"
    },
    ...
  },
  "providerMessage": null,
  "summary": {
    "anyKernelRunning": false,
    "checkedKernelsRunning": 1,
    "checkedKernelsTotal": 5,
    "quotaExhausted": false,
    "providerBlocking": false,
    "safe_to_savekernel": false
  }
}
```

#### `GET /kaggle/diagnosis/summary`
Lighter JSON response with key information only.

**Response:**
```json
{
  "timestamp": "2026-09-26T12:34:56.789Z",
  "summary": {
    "anyKernelRunning": false,
    "checkedKernelsRunning": 1,
    "checkedKernelsTotal": 5,
    "quotaExhausted": false,
    "providerBlocking": false,
    "safe_to_savekernel": false
  },
  "activeKernels": [],
  "quotaSummary": {
    "exhausted": [],
    "available": [
      { "name": "P100", "remaining": 20, "total": 40 }
    ]
  },
  "checkedKernels": { ... },
  "providerMessage": null
}
```

#### `GET /kaggle/diagnosis/text`
Human-readable text summary.

**Response:**
```
KAGGLE DIAGNOSIS SUMMARY
============================================================

ANALYSIS:
- Any kernel running: NO ✓
- Checked kernels running: 1/5
- GPU quota exhausted: NO ✓
- Provider blocking: NO ✓
- Safe to SaveKernel: NO ⚠

CHECKED KERNELS:
- nd-gpu-probe: completed (GPU: none)
- nd-wangp-disk-fit: running (GPU: T4)
...
```

---

## Key Findings: What They Mean

### "Safe to SaveKernel"

**True** when:
- No checked kernels are currently in `running`, `queued`, or `flushed` state
- No provider message is blocking operations
- GPU quota is available

**False** when:
- Any of the 5 checked kernels is actively running/queued
- Kaggle has an active provider message (quota exhaustion, account restriction, etc.)

### "Any Kernel Running"

Indicates whether **any kernel in your entire account** is actively running, queued, or flushed. This is broader than the 5 checked kernels and includes all your notebooks.

### HTTP 403 on SaveKernel

Possible causes identified by this tool:
1. **Quota Exhausted**: `quotaExhausted: true` in summary
2. **Provider Blocking**: `providerBlocking: true` — check `providerMessage` field
3. **Active Batch Session**: `checkedKernelsRunning > 0` — another kernel is still executing
4. **Account Restriction**: Check Kaggle dashboard or provider message for account-level blocks

---

## Running the Diagnosis

### Option 1: Local CLI (Development)

Set up credentials in your shell:
```bash
export KAGGLE_API_TOKEN="your_token_here"
export KAGGLE_USERNAME_SLUG="your_username"

node railway/nd-omniroute/kaggle-read-only-diagnosis.mjs
```

### Option 2: Via HTTP Endpoint (Production)

Once deployed with route registration:
```bash
# Full diagnosis
curl "https://nd-external-intelligence-production.up.railway.app/kaggle/diagnosis"

# Summary only
curl "https://nd-external-intelligence-production.up.railway.app/kaggle/diagnosis/summary"

# Human-readable text
curl "https://nd-external-intelligence-production.up.railway.app/kaggle/diagnosis/text"
```

If `REQUIRE_API_KEY` is enabled, add the API key:
```bash
curl "https://nd-external-intelligence-production.up.railway.app/kaggle/diagnosis?key=YOUR_OMNIROUTE_API_KEY"
```

### Option 3: One-Time Check with Kubernetes Pod

If running on Railway with SSH access, exec into the container:
```bash
railway run node railway/nd-omniroute/kaggle-read-only-diagnosis.mjs
```

---

## Security Notes

- **No token in output**: The KAGGLE_API_TOKEN is used for authentication but is **never printed, logged, or echoed** in any response.
- **Read-only**: All operations are GET requests; no kernels are created, modified, deleted, or rerun.
- **Error handling**: Failures to connect to Kaggle are reported as `{ error: "..." }` in responses, never exposing credentials.

---

## Troubleshooting

### "KAGGLE_API_TOKEN not set"
Ensure the token is exported in your shell or available in the container environment.

### "Unexpected response format"
Kaggle API may have changed. Check the Kaggle API v1 docs: https://kaggle.com/api/v1

### Diagnosis times out
Kaggle API may be slow. Increase the timeout in the script (default 15 seconds per request).

### "403 Forbidden" on HTTP endpoints
- Check that `REQUIRE_API_KEY` is `false` or include the correct API key
- Verify KAGGLE_API_TOKEN is set in the service environment
- Check Railway logs for more details

---

## References

- **Kaggle API Docs**: https://kaggle.com/api/v1
- **Kaggle Settings**: https://kaggle.com/settings/account
- **GPU Quotas**: https://kaggle.com/settings/account → Utilities → GPU quota

