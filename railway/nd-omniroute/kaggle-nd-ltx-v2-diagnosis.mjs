import { KaggleApi } from "kaggle";

const api = new KaggleApi();
api.authenticateUsingOAuthToken();

/**
 * Read-only diagnosis of savvasavchenko/nd-ltx-first-last-production v2
 * Inspects kernel metadata, provider status, and output logs without mutations
 */
async function diagnoseNdLtxV2() {
  const KERNEL_SLUG = "savvasavchenko/nd-ltx-first-last-production";
  const KERNEL_VERSION = 2;

  console.log(`\n=== ND-LTX-FIRST-LAST-PRODUCTION v${KERNEL_VERSION} DIAGNOSIS ===\n`);

  try {
    // Fetch kernel metadata (read-only)
    console.log("Fetching kernel metadata...");
    const kernelMeta = await api.kernelsViewRequest({
      kernelSlug: KERNEL_SLUG,
    });

    console.log(`\nKernel: ${KERNEL_SLUG}`);
    console.log(`Current Version: ${kernelMeta.versionNumber}`);
    console.log(`Latest Push: ${kernelMeta.lastKernelPushTimeSeconds}`);
    console.log(`Creator: ${kernelMeta.creatorName}`);

    // Fetch output metadata (read-only)
    console.log("\n--- Kernel Output Metadata ---");
    const outputList = await api.kernelOutputRequest({
      kernelSlug: KERNEL_SLUG,
    });

    if (!outputList || !outputList.files || outputList.files.length === 0) {
      console.log("No output files found.");
    } else {
      console.log(`Output files (${outputList.files.length}):`);
      outputList.files.forEach((file) => {
        console.log(`  - ${file.name} (${file.totalBytes} bytes)`);
      });

      // Check for result.mp4 and result.json
      const hasResultMp4 = outputList.files.some((f) => f.name === "result.mp4");
      const hasResultJson = outputList.files.some((f) => f.name === "result.json");

      console.log(`\n✓ result.mp4 exists: ${hasResultMp4}`);
      console.log(`✓ result.json exists: ${hasResultJson}`);
    }

    // Fetch kernel sessions (read-only, includes status & provider messages)
    console.log("\n--- Kernel Sessions (All Versions) ---");
    const sessions = await api.kernelSessionsListRequest({
      kernelSlug: KERNEL_SLUG,
      pageSize: 100,
    });

    if (!sessions || !sessions.data || sessions.data.length === 0) {
      console.log("No kernel sessions found.");
    } else {
      sessions.data.forEach((session, idx) => {
        const isV2 = session.kernelVersionNumber === KERNEL_VERSION;
        const marker = isV2 ? " [v2 TARGET]" : "";

        console.log(`\nSession ${idx + 1}${marker}:`);
        console.log(`  Kernel Version: ${session.kernelVersionNumber}`);
        console.log(`  Status: ${session.status}`);
        console.log(`  Created: ${session.createdDate}`);
        if (session.finishTime) {
          console.log(`  Finished: ${session.finishTime}`);
        }

        // Provider status message (captures quota, account, or other blocks)
        if (session.providerStatus) {
          console.log(`  Provider Status: ${session.providerStatus}`);
        }

        // Failure message (reason kernel did not run)
        if (session.failureMessage) {
          console.log(`  Failure Message: ${session.failureMessage}`);
        }
      });
    }

    // Attempt to fetch ListKernelSessionOutput (tail of logs)
    console.log("\n--- Output Log (Last 2000 chars) ---");
    try {
      const logs = await api.kernelSessionOutputRequest({
        kernelSlug: KERNEL_SLUG,
        pageSize: 100,
      });

      if (logs && logs.data && logs.data.length > 0) {
        // Collect all output lines
        const allLines = [];
        logs.data.forEach((entry) => {
          if (entry.outputText) {
            allLines.push(entry.outputText);
          }
          if (entry.errorOutput) {
            allLines.push(`[ERROR] ${entry.errorOutput}`);
          }
        });

        const fullOutput = allLines.join("\n");
        const tail = fullOutput.slice(-2000); // Last 2000 chars

        console.log(tail);
        console.log(
          `\n(Showing last 2000 chars of ${fullOutput.length} total)`
        );
      } else {
        console.log("No output logs found.");
      }
    } catch (logErr) {
      console.log(`Unable to fetch logs: ${logErr.message}`);
    }

    console.log("\n=== DIAGNOSIS COMPLETE ===\n");
  } catch (error) {
    console.error(`Diagnosis failed: ${error.message}`);
    if (error.response && error.response.statusCode) {
      console.error(`HTTP Status: ${error.response.statusCode}`);
      if (error.response.body) {
        console.error(`Response: ${error.response.body}`);
      }
    }
    process.exit(1);
  }
}

await diagnoseNdLtxV2();

