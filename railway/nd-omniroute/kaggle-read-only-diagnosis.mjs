#!/usr/bin/env node
/**
 * Kaggle Read-Only Diagnosis Tool
 * 
 * Purpose: Query Kaggle APIs to diagnose notebook/kernel sessions and GPU quota status.
 * No mutations: read-only queries only.
 * 
 * Usage: node kaggle-read-only-diagnosis.mjs
 * 
 * Required environment variables:
 *   - KAGGLE_API_TOKEN (your Kaggle API token, not printed in any output)
 *   - KAGGLE_USERNAME_SLUG (optional, for reference only)
 */

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

const KAGGLE_TOKEN = process.env.KAGGLE_API_TOKEN;
const KAGGLE_USER = process.env.KAGGLE_USERNAME_SLUG || 'unknown';

const KERNELS_TO_CHECK = [
  'nd-gpu-probe',
  'nd-wangp-bootstrap',
  'nd-wangp-i2v-qualification',
  'nd-wangp-disk-fit',
  'nd-sdcpp-flf-qualification'
];

if (!KAGGLE_TOKEN) {
  console.error('ERROR: KAGGLE_API_TOKEN environment variable is not set');
  console.error('This script requires the Kaggle API token to run diagnostics.');
  process.exit(1);
}

console.log('✓ Kaggle credentials found');
console.log(`  User: ${KAGGLE_USER}`);
console.log('');

/**
 * Execute a curl request to Kaggle API
 * Token is NOT printed in output/errors
 */
async function curlKaggle(endpoint, verbose = false) {
  const baseUrl = 'https://kaggle.com/api/v1';
  const url = `${baseUrl}${endpoint}`;
  
  const cmd = `curl -s -H "Authorization: Bearer ${KAGGLE_TOKEN}" -H "Content-Type: application/json" "${url}"`;
  
  try {
    const { stdout, stderr } = await execAsync(cmd, { maxBuffer: 10 * 1024 * 1024 });
    
    if (stderr && verbose) {
      console.warn(`[curl stderr] ${stderr}`);
    }
    
    try {
      return JSON.parse(stdout);
    } catch (e) {
      if (verbose) {
        console.warn(`Failed to parse JSON: ${stdout.substring(0, 100)}`);
      }
      return { error: 'Invalid JSON response', rawResponse: stdout.substring(0, 200) };
    }
  } catch (error) {
    return { error: error.message };
  }
}

async function diagnose() {
  console.log('═'.repeat(80));
  console.log('KAGGLE READ-ONLY DIAGNOSIS');
  console.log('═'.repeat(80));
  console.log('');
  
  // Step 1: Account info
  console.log('📋 STEP 1: Account Information');
  console.log('─'.repeat(80));
  
  const user = await curlKaggle('/users/view/my', true);
  
  if (user.error) {
    console.log(`⚠ Error fetching account info: ${user.error}`);
  } else {
    console.log(`✓ Account: ${user.username || user.ref || '(unknown)'}`);
    if (user.tier) console.log(`  Tier: ${user.tier}`);
    if (user.dateJoined) console.log(`  Member since: ${user.dateJoined}`);
  }
  console.log('');
  
  // Step 2: GPU quota
  console.log('💾 STEP 2: GPU Quota & Limits');
  console.log('─'.repeat(80));
  
  const quota = await curlKaggle('/kernels/view/gputypes', true);
  
  if (quota.error) {
    console.log(`⚠ Error fetching GPU quota: ${quota.error}`);
  } else if (Array.isArray(quota)) {
    const exhausted = quota.filter(q => (q.remaining ?? 0) <= 0);
    const available = quota.filter(q => (q.remaining ?? 0) > 0);
    
    console.log(`GPU Types: ${quota.length}`);
    
    if (exhausted.length > 0) {
      console.log(`\n⚠️  QUOTA EXHAUSTED (${exhausted.length}):`);
      exhausted.forEach(q => {
        const name = q.name || q.gpuType || 'unknown';
        const remaining = q.remaining ?? 0;
        const total = q.total ?? '?';
        console.log(`  - ${name}: ${remaining}/${total} hours remaining`);
      });
    }
    
    if (available.length > 0) {
      console.log(`\n✓ Available Quota (${available.length}):`);
      available.forEach(q => {
        const name = q.name || q.gpuType || 'unknown';
        const remaining = q.remaining ?? 0;
        const total = q.total ?? '?';
        console.log(`  - ${name}: ${remaining}/${total} hours remaining`);
      });
    }
  } else {
    console.log(`Unexpected response: ${JSON.stringify(quota).substring(0, 200)}`);
  }
  console.log('');
  
  // Step 3: All active/running kernels
  console.log('🔍 STEP 3: All Running/Active/Queued Kernel Sessions');
  console.log('─'.repeat(80));
  
  const allKernels = await curlKaggle('/kernels/list?page=1&pageSize=100&sortBy=dateTimeCreated&sortDirection=desc', true);
  
  if (allKernels.error) {
    console.log(`⚠ Error fetching kernel list: ${allKernels.error}`);
  } else if (Array.isArray(allKernels)) {
    const running = allKernels.filter(k => ['running', 'queued', 'flushed'].includes(k.status));
    
    console.log(`Total kernels: ${allKernels.length}`);
    console.log(`Running/Queued/Flushed: ${running.length}`);
    
    if (running.length > 0) {
      console.log('\nActive Sessions:');
      running.forEach(k => {
        const ref = k.ref || k.slug || '(unknown)';
        const status = k.status || '?';
        const gpu = k.gpuType || 'none';
        const created = k.dateTimeCreated || '?';
        console.log(`  - ${ref}`);
        console.log(`    Status: ${status}, GPU: ${gpu}`);
        console.log(`    Created: ${created}`);
      });
    } else {
      console.log('\n✓ No kernels currently running, queued, or flushed.');
    }
  } else {
    console.log(`Unexpected response format: ${typeof allKernels}`);
  }
  console.log('');
  
  // Step 4: Check specific kernels
  console.log('🎯 STEP 4: Specific Kernel Status Check');
  console.log('─'.repeat(80));
  console.log(`Checking ${KERNELS_TO_CHECK.length} kernels...`);
  console.log('');
  
  const kernelStatuses = {};
  
  for (const slug of KERNELS_TO_CHECK) {
    process.stdout.write(`  ${slug}... `);
    
    const kernel = await curlKaggle(`/kernels/view/${slug}`, false);
    
    if (kernel.error) {
      console.log(`⚠ NOT FOUND / ERROR: ${kernel.error}`);
      kernelStatuses[slug] = { status: 'error', message: kernel.error };
    } else if (!kernel.status) {
      console.log(`⚠ INVALID RESPONSE`);
      kernelStatuses[slug] = { status: 'invalid', message: 'No status field in response' };
    } else {
      const status = kernel.status || '?';
      const gpu = kernel.gpuType || 'none';
      const updated = kernel.dateTimeUpdated || '?';
      console.log(`✓ ${status} (GPU: ${gpu})`);
      kernelStatuses[slug] = { status, gpu, updated };
    }
  }
  console.log('');
  
  // Step 5: Provider messages
  console.log('⚠️  STEP 5: Provider Messages & 403 Blocking Factors');
  console.log('─'.repeat(80));
  
  const kernelsStatus = await curlKaggle('/kernels/status', true);
  
  if (kernelsStatus.error) {
    console.log(`⚠ Error fetching status: ${kernelsStatus.error}`);
  } else {
    const providerMsg = kernelsStatus.providerMessage || kernelsStatus.message;
    
    if (providerMsg) {
      console.log(`⚠️  PROVIDER MESSAGE:\n  "${providerMsg}"`);
      console.log('\nThis message may explain HTTP 403 on new SaveKernel operations.');
    } else {
      console.log('✓ No active provider messages blocking operations.');
    }
    
    if (kernelsStatus.quotaMessage) {
      console.log(`\nQuota Message: ${kernelsStatus.quotaMessage}`);
    }
  }
  console.log('');
  
  // Step 6: Summary
  console.log('📊 STEP 6: Diagnosis Summary');
  console.log('─'.repeat(80));
  
  const activeKernels = allKernels && Array.isArray(allKernels) 
    ? allKernels.filter(k => ['running', 'queued', 'flushed'].includes(k.status))
    : [];
  
  const checkedKernels = Object.values(kernelStatuses);
  const checkedRunning = checkedKernels.filter(k => k.status === 'running' || k.status === 'queued' || k.status === 'flushed');
  
  console.log(`✓ Total kernels: ${allKernels && Array.isArray(allKernels) ? allKernels.length : '?'}`);
  console.log(`✓ Any kernel running/queued/flushed: ${activeKernels.length > 0 ? 'YES' : 'NO'}`);
  console.log(`✓ Checked kernels actively running: ${checkedRunning.length}/${KERNELS_TO_CHECK.length}`);
  
  if (checkedRunning.length > 0) {
    console.log('\n⚠️  Active Batch/Commit Sessions Detected:');
    checkedRunning.forEach(k => {
      const slug = Object.entries(kernelStatuses).find(([_, v]) => v === k)?.[0];
      console.log(`  - ${slug}: ${k.status}`);
    });
  } else {
    console.log('\n✓ No checked kernels currently running (safe to create new SaveKernel)');
  }
  
  console.log('');
  console.log('═'.repeat(80));
  console.log('DIAGNOSIS COMPLETE');
  console.log('═'.repeat(80));
  console.log('');
  console.log('Next Steps:');
  console.log('  - If any kernel is "running" or "queued": wait for completion before SaveKernel');
  console.log('  - If HTTP 403 occurs: check provider message above for quota/account restrictions');
  console.log('  - For detailed Kaggle API docs: https://kaggle.com/api/v1');
  console.log('');
}

diagnose().catch(err => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});

