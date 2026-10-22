#!/usr/bin/env node
/**
 * Test harness for Kaggle LTX Mount Probe
 * Designed to run within nd-external-intelligence service context
 * where KAGGLE_API_TOKEN and Kaggle CLI are available
 */

import { executeKaggleLtxMountProbe } from './kaggle-ltx-mount-probe-route.mjs';

async function main() {
  console.log('='.repeat(70));
  console.log('KAGGLE LTX MODEL MOUNT PROBE - STANDALONE TEST');
  console.log('='.repeat(70));
  console.log(`Started: ${new Date().toISOString()}`);
  console.log('');
  
  try {
    const results = await executeKaggleLtxMountProbe();
    
    console.log('\n' + '='.repeat(70));
    console.log('PROBE RESULTS');
    console.log('='.repeat(70));
    console.log(JSON.stringify(results, null, 2));
    
    console.log('\n' + '='.repeat(70));
    console.log('SUMMARY');
    console.log('='.repeat(70));
    console.log(`Status: ${results.status}`);
    console.log(`Kernel Version: ${results.kernel_version}`);
    console.log(`Kernel Status: ${results.kernel_status}`);
    console.log(`Mounted Paths: ${results.mounted_paths.length}`);
    console.log(`Discovered Models: ${results.discovered_models.length}`);
    console.log(`Execution Time: ${results.execution_time_ms}ms`);
    
    if (results.discovered_models.length > 0) {
      console.log('\nDiscovered Safetensors Models:');
      results.discovered_models.forEach(model => {
        console.log(`  → ${model.absolute_path}`);
        console.log(`     Size: ${model.size_mb} MB (${model.size_bytes} bytes)`);
        console.log(`     Readable: ${model.readable}`);
      });
    }
    
    if (results.disk_usage) {
      console.log('\nDisk Usage (/kaggle/working):');
      console.log(`  Total: ${results.disk_usage.total_gb} GB (${results.disk_usage.total_bytes} bytes)`);
      console.log(`  Free:  ${results.disk_usage.free_gb} GB (${results.disk_usage.free_bytes} bytes)`);
      console.log(`  Used:  ${results.disk_usage.used_gb} GB (${results.disk_usage.used_bytes} bytes)`);
    }
    
    if (results.errors.length > 0) {
      console.log('\nErrors/Warnings:');
      results.errors.forEach(err => {
        console.log(`  ⚠ ${err}`);
      });
    }
    
    console.log('\n' + '='.repeat(70));
    
    process.exit(results.status === 'SUCCESS' ? 0 : 1);
    
  } catch (e) {
    console.error('[ERROR]', e.message);
    console.error(e.stack);
    process.exit(1);
  }
}

main();

