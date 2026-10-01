#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "mcp_stdio_call.py"


class McpStdioCallTests(unittest.TestCase):
    def _run(self, server_source: str, timeout: float = 1.0):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            server = root / "server.js"
            out = root / "result.json"
            server.write_text(textwrap.dedent(server_source), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(HARNESS),
                    "--server",
                    str(server),
                    "--tool",
                    "probe",
                    "--args",
                    "{}",
                    "--out",
                    str(out),
                    "--timeout",
                    str(timeout),
                    "--shutdown-timeout",
                    "0.2",
                ],
                text=True,
                capture_output=True,
                timeout=5,
            )
            payload = json.loads(out.read_text(encoding="utf-8"))
            return proc, payload

    def test_matching_response_completes_before_persistent_server_exit(self):
        proc, payload = self._run(
            r"""
            const readline = require("readline");
            const rl = readline.createInterface({input: process.stdin});
            rl.on("line", (line) => {
              let msg;
              try { msg = JSON.parse(line); } catch (_) { return; }
              if (msg.id === 1) {
                console.log(JSON.stringify({
                  jsonrpc: "2.0",
                  id: 1,
                  result: {protocolVersion: "2024-11-05", capabilities: {}, serverInfo: {name: "mock", version: "1"}}
                }));
              }
              if (msg.id === 2) {
                console.log(JSON.stringify({jsonrpc: "2.0", id: 2, result: {content: [{type: "text", text: "ok"}]}}));
                setInterval(() => {}, 1000);
              }
            });
            """
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(payload["timed_out"])
        self.assertEqual(payload["response"]["id"], 2)
        self.assertEqual(payload["shutdown"], "terminated")

    def test_jsonrpc_error_is_written_and_returns_error_code(self):
        proc, payload = self._run(
            r"""
            const readline = require("readline");
            const rl = readline.createInterface({input: process.stdin});
            rl.on("line", (line) => {
              let msg;
              try { msg = JSON.parse(line); } catch (_) { return; }
              if (msg.id === 2) {
                console.log(JSON.stringify({jsonrpc: "2.0", id: 2, error: {code: -32000, message: "boom"}}));
                setInterval(() => {}, 1000);
              }
            });
            """
        )
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(payload["timed_out"])
        self.assertEqual(payload["response"]["error"]["message"], "boom")

    def test_missing_or_malformed_response_hits_deadline_and_cleans_up(self):
        proc, payload = self._run(
            r"""
            const readline = require("readline");
            const rl = readline.createInterface({input: process.stdin});
            rl.on("line", () => {
              console.log("not-json");
              setInterval(() => {}, 1000);
            });
            """,
            timeout=0.25,
        )
        self.assertEqual(proc.returncode, 4)
        self.assertTrue(payload["timed_out"])
        self.assertIsNone(payload["response"])
        self.assertIn(payload["shutdown"], {"terminated", "killed"})

    def test_server_exit_without_matching_response_is_explicit_failure(self):
        proc, payload = self._run(
            r"""
            process.stdin.resume();
            process.stdin.on("end", () => process.exit(0));
            """
        )
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(payload["timed_out"])
        self.assertIsNone(payload["response"])


if __name__ == "__main__":
    unittest.main()
