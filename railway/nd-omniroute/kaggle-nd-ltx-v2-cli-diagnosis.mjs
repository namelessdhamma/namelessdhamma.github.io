#!/usr/bin/env node

/**
 * CLI tool: Read-only diagnosis of savvasavchenko/nd-ltx-first-last-production v2
 * 
 * Run from Railway environment where KAGGLE_API_TOKEN is available:
 *   node railway/nd-omniroute/kaggle-nd-ltx-v2-cli-diagnosis.mjs
 * 
 * Does NOT: rerun, cancel, create, or modify anything
 * Does NOT: print KAGGLE_API_TOKEN
 */

const KERNEL_SLUG = "savvasavchenko/nd-ltx-first-last-production";
const KERNEL_VERSION = 2;

async function diagnoseKernel() {
  const token = Bun.env.KAGGLE_API_TOKEN;
  if (!token) {
    console.error(
      "ERROR: KAGGLE_API_TOKEN not set. Run this script in Railway environment."
    );
    process.exit(1);
  }

  console.log(
    `\n=== ND-LTX-FIRST-LAST-PRODUCTION v${KERNEL_VERSION} READ-ONLY DIAGNOSIS ===\n`
  );

  // Helper: authenticated Kaggle API call
  const call = async (endpoint, method = "GET") => {
    try {
      const response = await fetch(`https://www.kaggle.com/api/v1${endpoint}`, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(
          `HTTP ${response.status}: ${text.substring(0, 300)}`
        );
      }

      return response.json();
    } catch (e) {
      throw new Error(`API call failed: ${e.message}`);
    }
  };

  // 1. Kernel metadata
  console.log("--- KERNEL METADATA ---");
  try {
    const meta = await call(`/kernels/${KERNEL_SLUG.replace("/", "%2F")}`);
    console.log(`Slug: ${meta.ref || KERNEL_SLUG}`);
    console.log(`Creator: ${meta.creatorName || "N/A"}`);
    console.log(`Current Version: ${meta.versionNumber || "N/A"}`);
    console.log(`Last Push: ${meta.lastKernelPushTimeSeconds || "N/A"}`);
  } catch (e) {
    console.error(`✗ Metadata fetch failed: ${e.message}`);
  }

  // 2. Output files
  console.log("\n--- OUTPUT FILES ---");
  try {
    const output = await call(
      `/kernels/${KERNEL_SLUG.replace("/", "%2F")}/output`
    );
    if (output.files && output.files.length > 0) {
      output.files.forEach((f) => {
        const name = f.fileName || f.name;
        const bytes = f.totalBytes || f.bytes;
        const mb = (bytes / 1024 / 1024).toFixed(2);
        console.log(`  ✓ ${name} (${mb} MB)`);
      });

      const hasResultMp4 = output.files.some(
        (f) => (f.fileName || f.name) === "result.mp4"
      );
      const hasResultJson = output.files.some(
        (f) => (f.fileName || f.name) === "result.json"
      );

      console.log(`\n✓ result.mp4 exists: ${hasResultMp4}`);
      console.log(`✓ result.json exists: ${hasResultJson}`);
    } else {
      console.log("No output files.");
    }
  } catch (e) {
    console.error(`✗ Output files fetch failed: ${e.message}`);
  }

  // 3. Kernel sessions & provider status
  console.log("\n--- KERNEL SESSIONS ---");
  try {
    const sessions = await call(
      `/kernels/${KERNEL_SLUG.replace("/", "%2F")}/sessions?pageSize=100`
    );
    if (sessions.data && sessions.data.length > 0) {
      sessions.data.forEach((session, idx) => {
        const isV2 = session.kernelVersionNumber === KERNEL_VERSION;
        const mark = isV2 ? " [v2 TARGET]" : "";

        console.log(`\nSession ${idx + 1}${mark}`);
        console.log(`  Kernel Version: ${session.kernelVersionNumber}`);
        console.log(`  Status: ${session.status}`);
        console.log(`  Created: ${session.createdDate}`);

        if (session.finishTime) {
          console.log(`  Finished: ${session.finishTime}`);
        }

        // Provider status (captures quota/account blocks)
        if (session.providerStatus) {
          console.log(`  Provider Status: ${session.providerStatus}`);
        } else {
          console.log(`  Provider Status: (none)`);
        }

        // Failure message
        if (session.failureMessage) {
          console.log(`  Failure Message: ${session.failureMessage}`);
        } else {
          console.log(`  Failure Message: (none)`);
        }
      });
    } else {
      console.log("No sessions found.");
    }
  } catch (e) {
    console.error(`✗ Sessions fetch failed: ${e.message}`);
  }

  // 4. Output logs (tail)
  console.log("\n--- OUTPUT LOGS (LAST 2000 CHARS) ---");
  try {
    const logs = await call(
      `/kernels/${KERNEL_SLUG.replace("/", "%2F")}/sessions/output?pageSize=100`
    );
    if (logs.data && Array.isArray(logs.data)) {
      const allLines = [];
      logs.data.forEach((entry) => {
        if (entry.outputText) allLines.push(entry.outputText);
        if (entry.errorOutput) allLines.push(`[ERROR] ${entry.errorOutput}`);
      });

      const fullOutput = allLines.join("\n");
      const tail = fullOutput.slice(-2000);

      console.log(tail || "(no logs)");
      console.log(
        `\n[Showing last 2000 of ${fullOutput.length} total characters]`
      );
    } else {
      console.log("(no logs)");
    }
  } catch (e) {
    console.error(`✗ Logs fetch failed: ${e.message}`);
  }

  console.log("\n=== DIAGNOSIS COMPLETE ===\n");
}

await diagnoseKernel();

