# ND-LTX-FIRST-LAST-PRODUCTION v2 Read-Only Diagnosis

## Overview

Provides **read-only inspection** of `savvasavchenko/nd-ltx-first-last-production` kernel version 2 without mutations (no reruns, cancellations, creates, or modifications).

## What It Reports

✓ **Provider Status**: Exact status message from Kaggle (quota blocks, account restrictions, etc.)  
✓ **Failure Message**: Reason kernel did not run (if applicable)  
✓ **Output Files**: result.mp4 and result.json existence/status  
✓ **Log Tail**: Last 2000 characters of ListKernelSessionOutput logs  
✓ **Session Metadata**: All kernel versions, status, created/finished timestamps

## Usage

### Option 1: HTTP Route (Recommended for nd-external-intelligence)

Add to your Hono app in `drive_proxy.mjs`:

```typescript
import { registerKaggleNdLtxV2DiagnosisRoute } from "./kaggle-nd-ltx-v2-diagnosis-route.mjs";

// In your Hono app initialization:
registerKaggleNdLtxV2DiagnosisRoute(app);
```

Then call:
```bash
curl https://nd-external-intelligence-production.up.railway.app/kaggle/nd-ltx-v2-diagnosis
```

**Returns JSON**:
```json
{
  "kernel": "savvasavchenko/nd-ltx-first-last-production",
  "version": 2,
  "timestamp": "2026-09-26T14:30:00Z",
  "metadata": { ... },
  "sessions": [
    {
      "kernel_version": 2,
      "is_target_v2": true,
      "status": "complete|error|running|...",
      "created": "2026-09-26T...",
      "finished": "2026-09-26T...",
      "provider_status": "string or null",
      "failure_message": "string or null"
    }
  ],
  "output_files": {
    "result_mp4_exists": true|false,
    "result_json_exists": true|false,
    "files": [
      { "name": "result.mp4", "bytes": 1234567 }
    ]
  },
  "logs": {
    "tail_2000_chars": "...",
    "total_chars": 12345
  },
  "errors": []
}
```

### Option 2: CLI Tool (Manual Invocation)

Requires KAGGLE_API_TOKEN in environment (available in Railway service):

```bash
# From within nd-external-intelligence service or Railway shell:
node railway/nd-omniroute/kaggle-nd-ltx-v2-cli-diagnosis.mjs
```

**Output**:
```
=== ND-LTX-FIRST-LAST-PRODUCTION v2 READ-ONLY DIAGNOSIS ===

--- KERNEL METADATA ---
Slug: savvasavchenko/nd-ltx-first-last-production
Creator: savvasavchenko
Current Version: 2
Last Push: 2026-09-25T...

--- OUTPUT FILES ---
  ✓ result.mp4 (156.45 MB)
  ✓ result.json (2.34 KB)

✓ result.mp4 exists: true
✓ result.json exists: true

--- KERNEL SESSIONS ---

Session 1 [v2 TARGET]
  Kernel Version: 2
  Status: complete
  Created: 2026-09-26T...
  Finished: 2026-09-26T...
  Provider Status: (none)
  Failure Message: (none)

--- OUTPUT LOGS (LAST 2000 CHARS) ---
[LTX-Video-ZeroGPU output...]
...
[Showing last 2000 of 45678 total characters]

=== DIAGNOSIS COMPLETE ===
```

## Security & Guarantees

✓ **No mutations**: GET requests only; no rerun, cancel, create, or delete  
✓ **No secret printing**: KAGGLE_API_TOKEN never logged or echoed  
✓ **Read-only Kaggle API calls**: Only information retrieval endpoints used  
✓ **Sandbox-safe**: No side effects; safe to run multiple times  
✓ **Error resilience**: Individual call failures do not halt diagnosis; reported in `errors[]` array

## Kaggle API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/kernels/{slug}` | GET | Kernel metadata (version, creator, etc.) |
| `/kernels/{slug}/output` | GET | Output files list (result.mp4, result.json, etc.) |
| `/kernels/{slug}/sessions` | GET | All kernel sessions with provider status & failure messages |
| `/kernels/{slug}/sessions/output` | GET | Kernel session output logs |

## Interpreting Results

### Provider Status

**What it shows**: Kaggle's assessment of why the kernel cannot run (quota, account block, etc.)

Examples:
- `null` or `(none)`: No provider block; kernel can run
- `"GPU quota exhausted"`: Your account has no GPU hours remaining
- `"Account restricted"`: Kaggle has flagged the account
- `"Kernel locked"`: Manual or automatic platform block

### Failure Message

**What it shows**: Reason the last run did not complete (if applicable)

Examples:
- `null` or `(none)`: No failure; kernel completed successfully
- `"Build failed"`: Docker/package issues
- `"Out of memory"`: Runtime memory exceeded
- `"Execution timeout"`: Took >60 minutes

### Output Files

**result.mp4**: Video output from LTX model  
**result.json**: Metadata/manifest file (if generated)

Both must exist for a successful run.

### Logs

The last 2000 characters of the kernel's stdout/stderr, useful for diagnosing:
- Model loading issues
- MCP server connection problems
- Memory or timing issues
- API errors from upstream services

If logs are empty, the kernel likely failed before producing output (build phase error).

## No Mutations Guarantee

This diagnostic **never**:
- Reruns the kernel
- Cancels or deletes the kernel
- Creates a new version
- Modifies kernel metadata
- Changes environment variables
- Commits or saves changes

It only **reads** public and semi-public kernel information via the Kaggle API.

---

**Created**: 2026-09-26  
**Last Updated**: 2026-09-26  
**Files**:
- `kaggle-nd-ltx-v2-diagnosis-route.mjs` — HTTP route handler
- `kaggle-nd-ltx-v2-cli-diagnosis.mjs` — CLI tool
- `ND_LTX_V2_DIAGNOSIS_GUIDE.md` — This guide

