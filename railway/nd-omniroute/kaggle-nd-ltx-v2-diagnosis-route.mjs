/**
 * Read-only diagnosis route for savvasavchenko/nd-ltx-first-last-production v2
 * Inspects kernel metadata, provider status, output files, and logs without mutations
 * 
 * Usage: GET /kaggle/nd-ltx-v2-diagnosis
 * Returns: JSON with metadata, session status, provider messages, output files, and log tail
 */

export function registerKaggleNdLtxV2DiagnosisRoute(app) {
  app.get("/kaggle/nd-ltx-v2-diagnosis", async (c) => {
    const KERNEL_SLUG = "savvasavchenko/nd-ltx-first-last-production";
    const KERNEL_VERSION = 2;

    const diagnosis = {
      kernel: KERNEL_SLUG,
      version: KERNEL_VERSION,
      timestamp: new Date().toISOString(),
      metadata: {},
      sessions: [],
      output_files: {
        result_mp4_exists: false,
        result_json_exists: false,
        files: [],
      },
      logs: {
        tail_2000_chars: "",
        total_chars: 0,
      },
      errors: [],
    };

    try {
      const token = Bun.env.KAGGLE_API_TOKEN;
      if (!token) {
        throw new Error(
          "KAGGLE_API_TOKEN not set in environment; cannot authenticate"
        );
      }

      // Helper: make authenticated Kaggle API calls
      const callKaggleApi = async (endpoint, method = "GET") => {
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
            `Kaggle API ${response.status}: ${text.substring(0, 200)}`
          );
        }

        return response.json();
      };

      // Fetch kernel metadata
      diagnosis.metadata = await callKaggleApi(
        `/kernels/${KERNEL_SLUG.replace("/", "%2F")}`
      );

      // Fetch output files
      try {
        const outputData = await callKaggleApi(
          `/kernels/${KERNEL_SLUG.replace("/", "%2F")}/output`
        );
        if (outputData.files) {
          diagnosis.output_files.files = outputData.files.map((f) => ({
            name: f.fileName || f.name,
            bytes: f.totalBytes || f.bytes,
          }));

          diagnosis.output_files.result_mp4_exists = outputData.files.some(
            (f) => (f.fileName || f.name) === "result.mp4"
          );
          diagnosis.output_files.result_json_exists = outputData.files.some(
            (f) => (f.fileName || f.name) === "result.json"
          );
        }
      } catch (e) {
        diagnosis.errors.push(`Failed to fetch output files: ${e.message}`);
      }

      // Fetch kernel sessions (includes status & provider messages)
      try {
        const sessionsData = await callKaggleApi(
          `/kernels/${KERNEL_SLUG.replace("/", "%2F")}/sessions?pageSize=100`
        );
        if (sessionsData.data) {
          diagnosis.sessions = sessionsData.data.map((session) => {
            const isV2 = session.kernelVersionNumber === KERNEL_VERSION;
            return {
              kernel_version: session.kernelVersionNumber,
              is_target_v2: isV2,
              status: session.status,
              created: session.createdDate,
              finished: session.finishTime || null,
              provider_status: session.providerStatus || null,
              failure_message: session.failureMessage || null,
            };
          });
        }
      } catch (e) {
        diagnosis.errors.push(`Failed to fetch sessions: ${e.message}`);
      }

      // Fetch kernel output logs (tail)
      try {
        const logsData = await callKaggleApi(
          `/kernels/${KERNEL_SLUG.replace("/", "%2F")}/sessions/output?pageSize=100`
        );
        if (logsData.data && Array.isArray(logsData.data)) {
          const allLines = [];
          logsData.data.forEach((entry) => {
            if (entry.outputText) allLines.push(entry.outputText);
            if (entry.errorOutput) allLines.push(`[ERROR] ${entry.errorOutput}`);
          });

          const fullOutput = allLines.join("\n");
          diagnosis.logs.total_chars = fullOutput.length;
          diagnosis.logs.tail_2000_chars = fullOutput.slice(-2000);
        }
      } catch (e) {
        diagnosis.errors.push(`Failed to fetch logs: ${e.message}`);
      }

      return c.json(diagnosis);
    } catch (error) {
      return c.json(
        {
          error: error.message,
          kernel: KERNEL_SLUG,
          version: KERNEL_VERSION,
        },
        500
      );
    }
  });
}

