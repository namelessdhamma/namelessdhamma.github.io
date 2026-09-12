#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def start(cmd: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(cmd, env=env)


def terminate(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    env = os.environ.copy()
    public_port = env.get("PORT", "3000")
    env["PORT"] = public_port
    env.setdefault("ND_VK_INNER_PORT", "3001")
    env.setdefault("ND_VK_VENDOR_ROOT", "/app/vendor")

    broker = start(["node", "/app/run_broker.mjs"], env)
    gateway = None

    def stop_all(signum=None, frame=None):
        terminate(gateway)
        terminate(broker)
        if signum is not None:
            raise SystemExit(128 + int(signum))

    signal.signal(signal.SIGTERM, stop_all)
    signal.signal(signal.SIGINT, stop_all)

    time.sleep(5)
    if broker.poll() is not None:
        print(f"ND_VK_PACKAGED_BROKER_EXIT code={broker.returncode}", flush=True)
        return 21

    gateway_env = env.copy()
    gateway_env["PORT"] = env["ND_VK_INNER_PORT"]
    gateway = start(["python3", "-u", "/app/run_gateway.py"], gateway_env)
    print(
        f"ND_VK_PACKAGED_RUNTIME_READY public_port={public_port} inner_port={env['ND_VK_INNER_PORT']}",
        flush=True,
    )

    while True:
        broker_code = broker.poll()
        gateway_code = gateway.poll()
        if broker_code is not None:
            print(f"ND_VK_PACKAGED_BROKER_EXIT code={broker_code}", flush=True)
            terminate(gateway)
            return 22
        if gateway_code is not None:
            print(f"ND_VK_PACKAGED_GATEWAY_EXIT code={gateway_code}", flush=True)
            terminate(broker)
            return 23
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
