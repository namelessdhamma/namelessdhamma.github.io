#!/usr/bin/env python3
import argparse, json, selectors, subprocess, sys, time


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
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

    for message in messages:
        proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    proc.stdin.close()

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    responses = []
    stderr_parts = []
    target = None
    timed_out = False
    deadline = time.monotonic() + ns.timeout

    while target is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break

        events = selector.select(timeout=min(remaining, 0.25))
        if not events:
            if proc.poll() is not None:
                break
            continue

        for key, _ in events:
            line = key.fileobj.readline()
            if line == "":
                try:
                    selector.unregister(key.fileobj)
                except Exception:
                    pass
                continue

            if key.data == "stderr":
                stderr_parts.append(line)
                continue

            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue

            responses.append(response)
            if response.get("id") == 2:
                target = response
                break

        if proc.poll() is not None and not selector.get_map():
            break

    shutdown = _terminate(proc, max(0.05, ns.shutdown_timeout))

    for stream, bucket, parse_json in (
        (proc.stdout, None, True),
        (proc.stderr, stderr_parts, False),
    ):
        try:
            rest = stream.read()
        except Exception:
            rest = ""
        if not rest:
            continue

        if parse_json:
            for line in rest.splitlines():
                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
                    continue
                responses.append(response)
                if target is None and response.get("id") == 2:
                    target = response
        else:
            bucket.append(rest)

    result = {
        "tool": ns.tool,
        "arguments": args,
        "server_exit_code": proc.returncode,
        "response": target,
        "stderr": "".join(stderr_parts)[-20000:],
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
