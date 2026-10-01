#!/usr/bin/env python3
import argparse
import json
import os
import selectors
import subprocess
import sys
import time


def _terminate(proc, timeout):
    if proc.poll() is not None:
        return "already_exited"
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
        return "terminated"
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return "kill_timeout"
        return "killed"


def _consume_json_lines(buffer, responses):
    target = None
    while b"\n" in buffer:
        raw, rest = buffer.split(b"\n", 1)
        buffer[:] = rest
        if not raw.strip():
            continue
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        responses.append(response)
        if response.get("id") == 2:
            target = response
    return target


def _consume_final_json(buffer, responses):
    if not buffer.strip():
        return None
    raw = bytes(buffer)
    buffer.clear()
    try:
        response = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    responses.append(response)
    return response if response.get("id") == 2 else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", required=True)
    p.add_argument("--tool", required=True)
    p.add_argument("--args", default="{}")
    p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--shutdown-timeout", type=float, default=2.0)
    ns = p.parse_args()
    args = json.loads(ns.args)
    messages = [
        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"nd-godot-cloud","version":"1"}}},
        {"jsonrpc":"2.0","method":"notifications/initialized"},
        {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":ns.tool,"arguments":args}},
    ]

    proc = subprocess.Popen(
        ["node", ns.server],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

    payload = b"".join(
        json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
        for message in messages
    )
    proc.stdin.write(payload)
    proc.stdin.flush()
    proc.stdin.close()

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")

    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    responses = []
    target = None
    deadline = time.monotonic() + ns.timeout

    while target is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        events = selector.select(timeout=min(remaining, 0.25))
        if not events:
            if proc.poll() is not None and not selector.get_map():
                break
            continue

        for key, _ in events:
            chunk = os.read(key.fileobj.fileno(), 65536)
            if not chunk:
                try:
                    selector.unregister(key.fileobj)
                except Exception:
                    pass
                if key.data == "stdout":
                    maybe = _consume_final_json(stdout_buffer, responses)
                    if target is None and maybe is not None:
                        target = maybe
                continue

            if key.data == "stderr":
                stderr_buffer.extend(chunk)
                continue

            stdout_buffer.extend(chunk)
            maybe = _consume_json_lines(stdout_buffer, responses)
            if target is None and maybe is not None:
                target = maybe
                break

        if proc.poll() is not None and not selector.get_map():
            break

    timed_out = target is None and time.monotonic() >= deadline
    shutdown = _terminate(proc, max(0.05, ns.shutdown_timeout))

    # Once the child is stopped, draining the remaining raw pipes cannot wait on
    # a long-lived server and cannot hide bytes in TextIO buffering.
    try:
        rest = proc.stdout.read() or b""
    except Exception:
        rest = b""
    if rest:
        stdout_buffer.extend(rest)
    maybe = _consume_json_lines(stdout_buffer, responses)
    if target is None and maybe is not None:
        target = maybe
    maybe = _consume_final_json(stdout_buffer, responses)
    if target is None and maybe is not None:
        target = maybe

    try:
        rest_err = proc.stderr.read() or b""
    except Exception:
        rest_err = b""
    if rest_err:
        stderr_buffer.extend(rest_err)

    # A matching response discovered during final drain wins over the deadline:
    # the provider effect/result was observable before cleanup completed.
    if target is not None:
        timed_out = False

    result = {
        "tool": ns.tool,
        "arguments": args,
        "server_exit_code": proc.returncode,
        "response": target,
        "stderr": stderr_buffer.decode("utf-8", errors="replace")[-20000:],
        "timed_out": timed_out,
        "shutdown": shutdown,
    }

    with open(ns.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))

    if timed_out and target is None:
        return 4
    if target is None or "error" in target:
        return 2
    if isinstance(target.get("result"), dict) and target["result"].get("isError"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
