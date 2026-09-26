#!/usr/bin/env node
/**
 * Kaggle LTX Model Mount Probe Launcher
 * Creates a private CPU-only kernel with model datasource
 * Polls until terminal, reads output, returns results
 * Read-only: No mutations beyond kernel creation
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const execAsync = promisify(exec);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const KAGGLE_TOKEN = process.env.KAGGLE_API_TOKEN;
if (!KAGGLE_TOKEN) {
  console.error('ERROR: KAGGLE_API_TOKEN not set');
  process.exit(1);
}

const KERNEL_SLUG = 'nd-ltx-model-mount-probe';
const MODEL_DATASOURCE = 'marcelolmesilva/ltxv-13b-0.9.7-distilled-fp8.safetensors/pytorch/default/1';
const PYTHON_SCRIPT = 'kaggle-ltx-model-mount-probe.py';

async function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function readKaggleConfig() {
  const configPath = path.join(process.env.HOME, '.kaggle', 'kaggle.json');
  try {
    const content = fs.readFileSync(configPath, 'utf-8');
    return JSON.parse(content);
  } catch (e) {
    throw new Error(`Cannot read Kaggle config at ${configPath}: ${e.message}`);
  }
}

async function createKernelMetadata() {
  /**
   * Metadata file format for Kaggle kernel creation
   * See: https://github.com/Kaggle/kaggle-api/wiki/Kernel-Metadata-and-Settings
   */
  const pythonScriptPath = path.join(__dirname, PYTHON_SCRIPT);
  const pythonContent = fs.readFileSync(pythonScriptPath, 'utf-8');
  
  const metadata = {
    id: `${process.env.USER || 'namelessdhamma'}/${KERNEL_SLUG}`,
    title: 'LTX Model Mount Probe',
    code_file: PYTHON_SCRIPT,
    language: 'python',
    kernel_type: 'script',
    is_private: true,
    enable_internet: false,
    enable_gpu: false,
    competition_sources: [],
    dataset_sources: [
      {
        source_slug: MODEL_DATASOURCE,
        status: 'active'
      }
    ],
    kernel_sources: [],
    model_sources: [
      {
        source_slug: MODEL_DATASOURCE,
        status: 'active'
      }
    ]
  };
  
  return metadata;
}

async function createKernelFiles() {
  const tempDir = path.join('/tmp', `kaggle-probe-${Date.now()}`);
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true });
  }
  
  // Copy Python script
  const pythonScriptPath = path.join(__dirname, PYTHON_SCRIPT);
  const pythonDest = path.join(tempDir, PYTHON_SCRIPT);
  fs.copyFileSync(pythonScriptPath, pythonDest);
  
  // Create kernel metadata
  const metadata = await createKernelMetadata();
  const metadataPath = path.join(tempDir, 'kernel-metadata.json');
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2));
  
  console.log(`[SETUP] Kernel files prepared in ${tempDir}`);
  return tempDir;
}

async function pushKernel(kernelDir) {
  console.log(`[PUSH] Pushing kernel: ${KERNEL_SLUG}`);
  console.log(`[PUSH] Model datasource: ${MODEL_DATASOURCE}`);
  
  try {
    const { stdout, stderr } = await execAsync(
      `cd ${kernelDir} && kaggle kernels push -p ${KERNEL_SLUG} 2>&1`,
      { timeout: 60000, env: { ...process.env, KAGGLE_API_TOKEN } }
    );
    
    console.log('[PUSH] Output:', stdout);
    if (stderr) console.log('[PUSH] Stderr:', stderr);
    
    return true;
  } catch (e) {
    console.error('[PUSH] Failed:', e.message);
    throw e;
  }
}

async function pollKernelStatus(maxAttempts = 120) {
  /**
   * Poll kernel status every 5 seconds, max 10 minutes
   * Terminal states: complete, error, timedOut, crashed, cancelled
   */
  console.log(`[POLL] Starting poll for ${KERNEL_SLUG}`);
  
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const { stdout } = await execAsync(
        `kaggle kernels status ${KERNEL_SLUG} --json 2>&1`,
        { timeout: 15000, env: { ...process.env, KAGGLE_API_TOKEN } }
      );
      
      let status;
      try {
        status = JSON.parse(stdout);
      } catch {
        console.log(`[POLL] Attempt ${i + 1}/${maxAttempts}: Parsing response...`);
        await delay(5000);
        continue;
      }
      
      const { kernelVersionNumber, versionStatus } = status;
      console.log(`[POLL] Attempt ${i + 1}/${maxAttempts}: v${kernelVersionNumber} → ${versionStatus}`);
      
      if (['complete', 'error', 'timedOut', 'crashed', 'cancelled'].includes(versionStatus)) {
        console.log(`[POLL] Terminal state reached: ${versionStatus}`);
        return { version: kernelVersionNumber, status: versionStatus, details: status };
      }
      
      await delay(5000);
    } catch (e) {
      console.log(`[POLL] Attempt ${i + 1}/${maxAttempts}: Error querying (will retry): ${e.message.slice(0, 100)}`);
      await delay(5000);
    }
  }
  
  throw new Error(`Kernel did not reach terminal state within ${maxAttempts * 5}s`);
}

async function readKernelOutput(version) {
  console.log(`[OUTPUT] Reading logs for v${version}...`);
  
  try {
    const { stdout, stderr } = await execAsync(
      `kaggle kernels output ${KERNEL_SLUG} -p /tmp/kernel-output --quiet 2>&1`,
      { timeout: 30000, env: { ...process.env, KAGGLE_API_TOKEN } }
    );
    
    console.log('[OUTPUT] Downloaded kernel output');
    
    // Try to read stdout.log
    const outputPath = '/tmp/kernel-output/stdout';
    if (fs.existsSync(outputPath)) {
      const content = fs.readFileSync(outputPath, 'utf-8');
      return { success: true, logs: content };
    }
    
    return { success: true, logs: '[No output file found]' };
  } catch (e) {
    console.error('[OUTPUT] Failed to read output:', e.message.slice(0, 200));
    return { success: false, error: e.message };
  }
}

async function extractProbeResults(logs) {
  /**
   * Parse JSON results from kernel output
   * Format: =\== KAGGLE_MOUNT_PROBE_RESULTS ===
   *         {...JSON...}
   *         === END_RESULTS ===
   */
  const match = logs.match(/=== KAGGLE_MOUNT_PROBE_RESULTS ===\n?([\s\S]*?)\n?=== END_RESULTS ===/);
  if (!match) {
    return { error: 'Could not parse probe results from kernel output' };
  }
  
  try {
    return JSON.parse(match[1]);
  } catch (e) {
    return { error: `JSON parse failed: ${e.message}`, raw_output: match[1].slice(0, 500) };
  }
}

async function main() {
  console.log('='.repeat(60));
  console.log('KAGGLE LTX MODEL MOUNT PROBE');
  console.log('='.repeat(60));
  
  try {
    // Verify Kaggle config
    const config = await readKaggleConfig();
    console.log(`[AUTH] Kaggle user: ${config.username}`);
    
    // Create kernel files
    const kernelDir = await createKernelFiles();
    
    // Push kernel
    await pushKernel(kernelDir);
    
    // Poll until terminal
    const result = await pollKernelStatus();
    console.log(`\n[RESULT] Kernel v${result.version}: ${result.status}`);
    
    if (result.status !== 'complete') {
      console.error(`[RESULT] Non-success terminal state: ${result.status}`);
      if (result.details?.outputLog) {
        console.log(`[RESULT] Provider output:\n${result.details.outputLog.slice(0, 1000)}`);
      }
    }
    
    // Read output
    const output = await readKernelOutput(result.version);
    if (!output.success) {
      console.error('[RESULT] Could not read kernel output:', output.error);
    }
    
    // Extract probe results
    const probeResults = await extractProbeResults(output.logs);
    
    console.log('\n' + '='.repeat(60));
    console.log('PROBE RESULTS');
    console.log('='.repeat(60));
    console.log(JSON.stringify({
      kernel_version: result.version,
      kernel_status: result.status,
      invalid_model_sources: result.details?.invalidModelSources || [],
      provider_status: result.details?.versionStatus,
      probe_output: probeResults
    }, null, 2));
    
    console.log('='.repeat(60));
    console.log('[COMPLETE] Probe execution finished');
    
  } catch (e) {
    console.error('[ERROR]', e.message);
    process.exit(1);
  }
}

main();

