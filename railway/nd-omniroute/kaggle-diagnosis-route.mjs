/**
 * Kaggle Diagnosis HTTP Route
 * 
 * Exposes a read-only endpoint that queries Kaggle APIs for:
 * - Current running/active notebook sessions
 * - Status of specific kernels
 * - GPU quota information
 * - Provider messages that may explain HTTP 403 on SaveKernel
 * 
 * Usage:
 *   GET /kaggle/diagnosis
 *   GET /kaggle/diagnosis/summary
 * 
 * Requires:
 *   - KAGGLE_API_TOKEN environment variable (not exposed in response)
 *   - REQUIRE_API_KEY set to false OR include ?key=OMNIROUTE_API_KEY
 * 
 * No mutations: read-only queries only.
 */

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

const KERNELS_TO_CHECK = [
  'nd-gpu-probe',
  'nd-wangp-bootstrap',
  'nd-wangp-i2v-qualification',
  'nd-wangp-disk-fit',
  'nd-sdcpp-flf-qualification'
];

/**
 * Execute a curl request to Kaggle API (read-only)
 * Token is NOT included in any response
 */
async function curlKaggle(endpoint) {
  const token = process.env.KAGGLE_API_TOKEN;
  
  if (!token) {
    throw new Error('KAGGLE_API_TOKEN not configured');
  }
  
  const baseUrl = 'https://kaggle.com/api/v1';
  const url = `${baseUrl}${endpoint}`;
  
  const cmd = `curl -s -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" "${url}"`;
  
  try {
    const { stdout } = await execAsync(cmd, { maxBuffer: 10 * 1024 * 1024, timeout: 15000 });
    return JSON.parse(stdout);
  } catch (error) {
    return { error: error.message };
  }
}

/**
 * Full diagnosis: account, quota, kernels, provider messages
 */
async function fullDiagnosis() {
  const result = {
    timestamp: new Date().toISOString(),
    account: null,
    quota: null,
    allKernels: { total: 0, active: 0, list: [] },
    checkedKernels: {},
    providerMessage: null,
    summary: {}
  };
  
  // Account info
  try {
    result.account = await curlKaggle('/users/view/my');
  } catch (e) {
    result.account = { error: e.message };
  }
  
  // GPU quota
  try {
    const quota = await curlKaggle('/kernels/view/gputypes');
    if (Array.isArray(quota)) {
      result.quota = {
        types: quota.length,
        exhausted: quota.filter(q => (q.remaining ?? 0) <= 0),
        available: quota.filter(q => (q.remaining ?? 0) > 0),
        all: quota
      };
    } else {
      result.quota = quota;
    }
  } catch (e) {
    result.quota = { error: e.message };
  }
  
  // All kernels
  try {
    const allKernels = await curlKaggle('/kernels/list?page=1&pageSize=100&sortBy=dateTimeCreated&sortDirection=desc');
    if (Array.isArray(allKernels)) {
      const active = allKernels.filter(k => ['running', 'queued', 'flushed'].includes(k.status));
      result.allKernels = {
        total: allKernels.length,
        active: active.length,
        list: active.map(k => ({
          ref: k.ref || k.slug,
          status: k.status,
          gpuType: k.gpuType,
          dateTimeCreated: k.dateTimeCreated,
          dateTimeUpdated: k.dateTimeUpdated
        }))
      };
    } else {
      result.allKernels = { error: allKernels.error || 'Invalid response' };
    }
  } catch (e) {
    result.allKernels = { error: e.message };
  }
  
  // Check specific kernels
  for (const slug of KERNELS_TO_CHECK) {
    try {
      const kernel = await curlKaggle(`/kernels/view/${slug}`);
      if (kernel.error || !kernel.status) {
        result.checkedKernels[slug] = {
          status: 'not_found',
          error: kernel.error || 'Invalid response'
        };
      } else {
        result.checkedKernels[slug] = {
          status: kernel.status,
          gpuType: kernel.gpuType || 'none',
          dateTimeUpdated: kernel.dateTimeUpdated
        };
      }
    } catch (e) {
      result.checkedKernels[slug] = { status: 'error', error: e.message };
    }
  }
  
  // Provider message
  try {
    const statusResp = await curlKaggle('/kernels/status');
    result.providerMessage = statusResp.providerMessage || statusResp.message || null;
  } catch (e) {
    result.providerMessage = `Error fetching: ${e.message}`;
  }
  
  // Summary
  const checkedRunning = Object.values(result.checkedKernels)
    .filter(k => ['running', 'queued', 'flushed'].includes(k.status));
  
  result.summary = {
    anyKernelRunning: result.allKernels.active > 0 || checkedRunning.length > 0,
    checkedKernelsRunning: checkedRunning.length,
    checkedKernelsTotal: KERNELS_TO_CHECK.length,
    quotaExhausted: result.quota.exhausted ? result.quota.exhausted.length > 0 : false,
    providerBlocking: result.providerMessage ? true : false,
    safe_to_savekernel: checkedRunning.length === 0 && !result.providerMessage
  };
  
  return result;
}

/**
 * Summary-only diagnosis (lighter response)
 */
async function summaryDiagnosis() {
  const full = await fullDiagnosis();
  
  return {
    timestamp: full.timestamp,
    summary: full.summary,
    activeKernels: full.allKernels.list || [],
    quotaSummary: full.quota && Array.isArray(full.quota.all)
      ? {
          exhausted: full.quota.exhausted.map(q => ({ 
            name: q.name || q.gpuType, 
            remaining: q.remaining, 
            total: q.total 
          })),
          available: full.quota.available.slice(0, 3).map(q => ({ 
            name: q.name || q.gpuType, 
            remaining: q.remaining, 
            total: q.total 
          }))
        }
      : full.quota,
    checkedKernels: full.checkedKernels,
    providerMessage: full.providerMessage
  };
}

/**
 * Register routes on a given Hono app or express-like router
 */
export function registerKaggleDiagnosisRoutes(app) {
  // Full diagnosis
  app.get('/kaggle/diagnosis', async (c) => {
    try {
      const diagnosis = await fullDiagnosis();
      return c.json(diagnosis);
    } catch (error) {
      return c.json({ error: error.message }, 500);
    }
  });
  
  // Summary diagnosis
  app.get('/kaggle/diagnosis/summary', async (c) => {
    try {
      const diagnosis = await summaryDiagnosis();
      return c.json(diagnosis);
    } catch (error) {
      return c.json({ error: error.message }, 500);
    }
  });
  
  // Text summary (human-readable)
  app.get('/kaggle/diagnosis/text', async (c) => {
    try {
      const diagnosis = await summaryDiagnosis();
      const { summary, activeKernels, quotaSummary, providerMessage, checkedKernels } = diagnosis;
      
      let text = 'KAGGLE DIAGNOSIS SUMMARY\n';
      text += '='.repeat(60) + '\n\n';
      
      text += 'ANALYSIS:\n';
      text += `- Any kernel running: ${summary.anyKernelRunning ? 'YES ⚠' : 'NO ✓'}\n`;
      text += `- Checked kernels running: ${summary.checkedKernelsRunning}/${summary.checkedKernelsTotal}\n`;
      text += `- GPU quota exhausted: ${summary.quotaExhausted ? 'YES ⚠' : 'NO ✓'}\n`;
      text += `- Provider blocking: ${summary.providerBlocking ? 'YES ⚠' : 'NO ✓'}\n`;
      text += `- Safe to SaveKernel: ${summary.safe_to_savekernel ? 'YES ✓' : 'NO ⚠'}\n\n`;
      
      if (activeKernels.length > 0) {
        text += `ACTIVE KERNELS (${activeKernels.length}):\n`;
        activeKernels.forEach(k => {
          text += `- ${k.ref}: ${k.status} (GPU: ${k.gpuType})\n`;
        });
        text += '\n';
      }
      
      if (checkedKernels && Object.keys(checkedKernels).length > 0) {
        text += 'CHECKED KERNELS:\n';
        Object.entries(checkedKernels).forEach(([slug, data]) => {
          text += `- ${slug}: ${data.status} (GPU: ${data.gpuType || 'N/A'})\n`;
        });
        text += '\n';
      }
      
      if (quotaSummary && Array.isArray(quotaSummary)) {
        // Handle legacy quota format
        text += 'GPU QUOTA:\n';
        quotaSummary.forEach(q => {
          text += `- ${q.name || q.gpuType}: ${q.remaining}/${q.total} hours\n`;
        });
        text += '\n';
      } else if (quotaSummary && quotaSummary.exhausted) {
        // Handle new quota format
        if (quotaSummary.exhausted.length > 0) {
          text += 'EXHAUSTED GPU QUOTA:\n';
          quotaSummary.exhausted.forEach(q => {
            text += `- ${q.name}: ${q.remaining}/${q.total} hours\n`;
          });
          text += '\n';
        }
        
        if (quotaSummary.available.length > 0) {
          text += 'AVAILABLE GPU QUOTA:\n';
          quotaSummary.available.forEach(q => {
            text += `- ${q.name}: ${q.remaining}/${q.total} hours\n`;
          });
          text += '\n';
        }
      }
      
      if (providerMessage) {
        text += `PROVIDER MESSAGE:\n"${providerMessage}"\n`;
        text += '(This may explain HTTP 403 on SaveKernel)\n\n';
      }
      
      return c.text(text);
    } catch (error) {
      return c.text(`ERROR: ${error.message}`, 500);
    }
  });
}

export { fullDiagnosis, summaryDiagnosis };

