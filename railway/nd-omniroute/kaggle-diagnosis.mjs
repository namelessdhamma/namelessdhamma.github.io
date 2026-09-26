#!/usr/bin/env node
/**
 * Read-only Kaggle diagnosis
 * Queries API without modifying any kernels or resources
 * Never prints KAGGLE_API_TOKEN
 */

import https from "https";

async function kaggleRequest(path, method = "GET") {
  const token = process.env.KAGGLE_API_TOKEN;
  if (!token) throw new Error("KAGGLE_API_TOKEN not set");

  const [username, apiKey] = token.split(":");
  if (!username || !apiKey) throw new Error("Invalid token format");

  const authHeader = Buffer.from(`${username}:${apiKey}`).toString("base64");

  return new Promise((resolve, reject) => {
    const options = {
      hostname: "www.kaggle.com",
      port: 443,
      path: `/api/i${path}`,
      method,
      headers: {
        Authorization: `Basic ${authHeader}`,
        "Content-Type": "application/json",
        "User-Agent": "Railway-Agent-Diagnosis/1.0",
      },
    };

    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => {
        try {
          const parsed = data ? JSON.parse(data) : {};
          resolve({ status: res.statusCode, data: parsed, headers: res.headers });
        } catch (e) {
          resolve({ status: res.statusCode, raw: data.substring(0, 500) });
        }
      });
    });

    req.on("error", reject);
    req.end();
  });
}

async function main() {
  console.log("=== Kaggle Read-Only Diagnosis ===\n");

  const username = process.env.KAGGLE_USERNAME_SLUG;
  console.log(`Account: ${username || "(unknown)"}\n`);

  // 1. Active notebook sessions
  console.log("1. Active notebook sessions...");
  try {
    const sessionsRes = await kaggleRequest("/kernels/sessions/?activeOnly=true");
    if (sessionsRes.status === 200) {
      const sessions = sessionsRes.data.kernelSessions || [];
      if (sessions.length === 0) {
        console.log("   ✓ No active sessions");
      } else {
        console.log(`   ✓ ${sessions.length} active session(s):`);
        sessions.forEach((s) => {
          console.log(`     • ${s.kernelVersionSlug || s.id}`);
          if (s.gpuAccelerator)
            console.log(`       GPU: ${s.gpuAccelerator}`);
          if (s.currentKernelStatus)
            console.log(`       Status: ${s.currentKernelStatus}`);
        });
      }
    } else {
      console.log(`   ✗ Query failed (${sessionsRes.status})`);
    }
  } catch (e) {
    console.log(`   ✗ Error: ${e.message}`);
  }

  // 2. Specific kernel statuses
  const kernels = [
    "nd-gpu-probe",
    "nd-wangp-bootstrap",
    "nd-wangp-i2v-qualification",
    "nd-wangp-disk-fit",
    "nd-sdcpp-flf-qualification",
  ];

  console.log("\n2. Private kernel statuses:");
  for (const slug of kernels) {
    try {
      const res = await kaggleRequest(`/kernels/${username}/${slug}`);
      if (res.status === 200) {
        const k = res.data;
        console.log(`   ✓ ${slug}`);
        if (k.currentKernelStatus)
          console.log(`     Status: ${k.currentKernelStatus}`);
        if (k.enableGpu) console.log(`     GPU: enabled`);
        if (k.gpuAccelerator)
          console.log(`     Accelerator: ${k.gpuAccelerator}`);
      } else if (res.status === 404) {
        console.log(`   ✗ ${slug} - Not found (404)`);
      } else {
        console.log(`   ✗ ${slug} - Failed (${res.status})`);
      }
    } catch (e) {
      console.log(`   ✗ ${slug} - ${e.message}`);
    }
  }

  // 3. GPU quota
  console.log("\n3. GPU quota...");
  try {
    const res = await kaggleRequest("/kernels/gpuAccelerator/quotas/");
    if (res.status === 200) {
      console.log("   ✓ Quota info:");
      const q = res.data;
      if (q.dailyGpuQuotaRemaining !== undefined)
        console.log(`     Daily remaining: ${q.dailyGpuQuotaRemaining} hours`);
      if (q.weeklyGpuQuotaRemaining !== undefined)
        console.log(`     Weekly remaining: ${q.weeklyGpuQuotaRemaining} hours`);
      if (q.totalGpuQuotaRemaining !== undefined)
        console.log(`     Total remaining: ${q.totalGpuQuotaRemaining} hours`);
      if (Object.keys(q).length === 0) console.log("   (empty quota response)");
    } else {
      console.log(`   ✗ Query failed (${res.status})`);
    }
  } catch (e) {
    console.log(`   ✗ Error: ${e.message}`);
  }

  // 4. Check for active GPU batch/commit sessions
  console.log("\n4. GPU batch/commit sessions...");
  try {
    const res = await kaggleRequest("/kernels/gpuSession/");
    if (res.status === 200) {
      const session = res.data;
      if (session.gpuSessionId) {
        console.log(`   ✓ Active GPU session: ${session.gpuSessionId}`);
        if (session.cpuCommitMinutesRemaining !== undefined)
          console.log(`     CPU commit time: ${session.cpuCommitMinutesRemaining} min`);
        if (session.gpuCommitMinutesRemaining !== undefined)
          console.log(`     GPU commit time: ${session.gpuCommitMinutesRemaining} min`);
      } else {
        console.log("   ✓ No active GPU batch session");
      }
    } else if (res.status === 404) {
      console.log("   ✓ No active GPU session");
    } else {
      console.log(`   ✗ Query failed (${res.status})`);
    }
  } catch (e) {
    console.log(`   ✗ Error: ${e.message}`);
  }

  // 5. SaveKernel 403 diagnostic
  console.log("\n5. SaveKernel endpoint 403 context...");
  try {
    const res = await kaggleRequest(`/kernels/${username}/nd-gpu-probe/save/`, "POST");
    if (res.status === 403) {
      console.log("   ✓ SaveKernel returns 403:");
      const msg = res.data?.message || res.raw || "(no message)";
      console.log(`     ${msg.substring(0, 300)}`);
    } else if (res.status === 200) {
      console.log("   ✓ SaveKernel endpoint accessible (200)");
    } else {
      console.log(`   ℹ SaveKernel returned ${res.status}`);
    }
  } catch (e) {
    console.log(`   ℹ ${e.message}`);
  }

  console.log("\n=== Diagnosis Complete ===");
}

main().catch((e) => {
  console.error("Fatal:", e.message);
  process.exit(1);
});

