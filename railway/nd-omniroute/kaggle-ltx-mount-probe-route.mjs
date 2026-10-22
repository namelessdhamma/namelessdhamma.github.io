/**
 * Kaggle LTX Model Mount Probe Route
 * Hono route for nd-external-intelligence service
 * 
 * GET /kaggle/ltx-mount-probe
 *   - Creates private CPU kernel with model datasource
 *   - Polls until terminal state
 *   - Returns mounted paths, file sizes, disk usage
 * 
 * Read-only: Only creates kernel, no other mutations
 */

import { spawn } from 'child_process';
import { writeFileSync, readFileSync, mkdirSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

const KERNEL_SLUG = 'nd-ltx-model-mount-probe';
const MODEL_DATASOURCE = 'marcelolmesilva/ltxv-13b-0.9.7-distilled-fp8.safetensors/pytorch/default/1';

/**
 * Python script for model mount inspection (embedded)
 */
const PROBE_SCRIPT = `#!/usr/bin/env python3
import os, sys, json, shutil
from pathlib import Path

results = {"mounted_paths": [], "discovered_models": [], "disk_usage": {}, "errors": []}

input_root = Path("/kaggle/input")
if input_root.exists():
    for root, dirs, files in os.walk(input_root):
        depth = root.replace(str(input_root), "").count(os.sep)
        if depth > 5:
            dirs.clear()
            continue
        for file in files:
            fpath = Path(root) / file
            try:
                stat = fpath.stat()
                is_readable = os.access(fpath, os.R_OK)
                entry = {
                    "absolute_path": str(fpath.resolve()),
                    "relative_path": str(fpath.relative_to(input_root)),
                    "size_bytes": stat.st_size,
                    "readable": is_readable,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2)
                }
                results["mounted_paths"].append(entry)
                if file.endswith(".safetensors"):
                    results["discovered_models"].append(entry)
            except Exception as e:
                results["errors"].append(f"Error: {str(e)[:100]}")

try:
    usage = shutil.disk_usage("/kaggle/working")
    results["disk_usage"] = {
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "used_bytes": usage.used,
        "total_gb": round(usage.total / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2)
    }
except Exception as e:
    results["errors"].append(f"disk_usage: {str(e)[:100]}")

print("=== KAGGLE_MOUNT_PROBE_RESULTS ===")
print(json.dumps(results))
print("=== END_RESULTS ===")
`;

/**
 * Execute child process and capture output
 */
function execAsync(cmd, args = [], options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: options.timeout || 30000,
      ...options
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('Process timeout'));
    }, options.timeout || 30000);

    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0 && !options.allowNonZero) {
        reject(new Error(`Exit code ${code}: ${stderr}`));
      } else {
        resolve({ stdout, stderr, code });
      }
    });

    child.on('error', reject);
  });
}

/**
 * Create kernel metadata JSON
 */
function createKernelMetadata(username) {
  return {
    id: `${username}/${KERNEL_SLUG}`,
    title: 'LTX Model Mount Probe',
    code_file: 'probe.py',
    language: 'python',
    kernel_type: 'script',
    is_private: true,
    enable_internet: false,
    enable_gpu: false,
    competition_sources: [],
    dataset_sources: [],
    kernel_sources: [],
    model_sources: [
      {
        source_slug: MODEL_DATASOURCE,
        status: 'active'
      }
    ]
  };
}

/**
 * Main probe execution
 */
export async function executeKaggleLtxMountProbe() {
  const startTime = Date.now();
  const results = {
    timestamp: new Date().toISOString(),
    kernel_slug: KERNEL_SLUG,
    model_datasource: MODEL_DATASOURCE,
    status: 'PENDING',
    kernel_version: null,
    kernel_status: null,
    provider_error: null,
    invalid_model_sources: [],
    mounted_paths: [],
    discovered_models: [],
    disk_usage: null,
    execution_time_ms: 0,
    errors: []
  };

  try {
    // Step 1: Get Kaggle username
    console.log('[PROBE] Getting Kaggle username...');
    const configRes = await execAsync('kaggle', ['config', 'view', '--json'], { allowNonZero: true });
    let kaggleUsername = 'unknown';
    try {
      const config = JSON.parse(configRes.stdout);
      kaggleUsername = config.username || 'unknown';
    } catch (e) {
      results.errors.push(`Could not parse Kaggle config: ${e.message}`);
    }

    // Step 2: Create temp kernel directory
    const tempDir = join(tmpdir(), `kaggle-probe-${Date.now()}`);
    mkdirSync(tempDir, { recursive: true });
    
    // Write probe script
    const probeScriptPath = join(tempDir, 'probe.py');
    writeFileSync(probeScriptPath, PROBE_SCRIPT);
    
    // Write metadata
    const metadataPath = join(tempDir, 'kernel-metadata.json');
    const metadata = createKernelMetadata(kaggleUsername);
    writeFileSync(metadataPath, JSON.stringify(metadata, null, 2));

    console.log(`[PROBE] Kernel files created in ${tempDir}`);

    // Step 3: Push kernel
    console.log(`[PROBE] Pushing kernel: ${KERNEL_SLUG}`);
    const pushRes = await execAsync('kaggle', ['kernels', 'push', '-p', KERNEL_SLUG], {
      cwd: tempDir,
      timeout: 60000,
      allowNonZero: true
    });
    
    if (pushRes.code !== 0) {
      results.errors.push(`Push failed: ${pushRes.stderr.slice(0, 200)}`);
      results.status = 'PUSH_FAILED';
      return results;
    }

    console.log('[PROBE] Kernel pushed, polling for completion...');

    // Step 4: Poll kernel status until terminal
    let pollAttempts = 0;
    const maxPolls = 120; // 10 minutes with 5s intervals
    let kernelComplete = false;

    for (pollAttempts = 0; pollAttempts < maxPolls && !kernelComplete; pollAttempts++) {
      await new Promise(r => setTimeout(r, 5000)); // Wait 5s between polls

      const statusRes = await execAsync('kaggle', ['kernels', 'status', KERNEL_SLUG, '--json'], {
        timeout: 15000,
        allowNonZero: true
      });

      if (statusRes.code !== 0) {
        console.log(`[PROBE] Status poll ${pollAttempts + 1}/${maxPolls}: Connection issue, retrying...`);
        continue;
      }

      try {
        const status = JSON.parse(statusRes.stdout);
        const { kernelVersionNumber, versionStatus, invalidModelSources } = status;

        console.log(`[PROBE] Status poll ${pollAttempts + 1}/${maxPolls}: v${kernelVersionNumber} → ${versionStatus}`);

        results.kernel_version = kernelVersionNumber;
        results.kernel_status = versionStatus;
        if (invalidModelSources?.length > 0) {
          results.invalid_model_sources = invalidModelSources;
        }

        if (['complete', 'error', 'timedOut', 'crashed', 'cancelled'].includes(versionStatus)) {
          console.log(`[PROBE] Terminal state reached: ${versionStatus}`);
          kernelComplete = true;
        }
      } catch (e) {
        console.log(`[PROBE] Status poll ${pollAttempts + 1}/${maxPolls}: Parse error, retrying...`);
      }
    }

    if (!kernelComplete) {
      results.errors.push(`Kernel did not reach terminal state within ${maxPolls * 5}s`);
      results.status = 'POLL_TIMEOUT';
      return results;
    }

    // Step 5: Download kernel output
    if (results.kernel_status === 'complete') {
      console.log(`[PROBE] Reading kernel output...`);
      const outputDir = join(tmpdir(), `kernel-output-${Date.now()}`);
      mkdirSync(outputDir, { recursive: true });

      const outputRes = await execAsync('kaggle', ['kernels', 'output', KERNEL_SLUG, '-p', outputDir, '--quiet'], {
        timeout: 30000,
        allowNonZero: true
      });

      if (outputRes.code === 0) {
        try {
          const stdoutPath = join(outputDir, 'stdout');
          const logs = readFileSync(stdoutPath, 'utf-8');

          // Extract probe results
          const match = logs.match(/=== KAGGLE_MOUNT_PROBE_RESULTS ===\n?([\s\S]*?)\n?=== END_RESULTS ===/);
          if (match) {
            const probeData = JSON.parse(match[1]);
            results.mounted_paths = probeData.mounted_paths || [];
            results.discovered_models = probeData.discovered_models || [];
            results.disk_usage = probeData.disk_usage || null;
            if (probeData.errors?.length > 0) {
              results.errors.push(...probeData.errors);
            }
            results.status = 'SUCCESS';
          } else {
            results.errors.push('Could not parse probe results from kernel output');
            results.status = 'PARSE_FAILED';
          }
        } catch (e) {
          results.errors.push(`Output parsing error: ${e.message}`);
          results.status = 'OUTPUT_ERROR';
        }
      } else {
        results.errors.push(`Could not retrieve kernel output: ${outputRes.stderr.slice(0, 200)}`);
        results.status = 'OUTPUT_FAILED';
      }
    } else {
      results.status = `KERNEL_${results.kernel_status.toUpperCase()}`;
      results.errors.push(`Kernel reached non-success terminal state: ${results.kernel_status}`);
    }

  } catch (e) {
    results.status = 'ERROR';
    results.errors.push(e.message);
  }

  results.execution_time_ms = Date.now() - startTime;
  return results;
}

/**
 * Hono route handler
 */
export function registerKaggleLtxProbeRoute(app) {
  app.get('/kaggle/ltx-mount-probe', async (c) => {
    try {
      console.log(`[ROUTE] GET /kaggle/ltx-mount-probe initiated`);
      const results = await executeKaggleLtxMountProbe();
      return c.json(results, 200);
    } catch (e) {
      console.error('[ROUTE] Error:', e.message);
      return c.json({
        status: 'ERROR',
        error: e.message
      }, 500);
    }
  });
}

