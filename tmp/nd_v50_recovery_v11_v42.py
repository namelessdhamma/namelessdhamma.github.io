import os, subprocess, time, urllib.request, signal, sys

# ND VK runtime recovery V50
# Purpose: restore the previously proven V11 Drive/Safe-Tool front + V42 Father VK gateway
# in one Railway service after the V49 qualification snapshot stopped booting.
# This is a bounded recovery launcher, not a production-authority promotion.

FRONT = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js"
V42 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"

print("ND_V50_RECOVERY_BOOT", flush=True)
subprocess.run(["apk", "add", "--no-cache", "nodejs"], check=True, stdout=subprocess.DEVNULL)

urllib.request.urlretrieve(FRONT, "/tmp/nd-drive-front.mjs")
front_env = dict(os.environ)
front_env["PORT"] = os.environ.get("PORT", "3000")
front = subprocess.Popen(["node", "/tmp/nd-drive-front.mjs"], env=front_env)

time.sleep(5)
if front.poll() is not None:
    raise RuntimeError("ND V50 Drive front exited during startup")

os.environ["PORT"] = "3001"
src = urllib.request.urlopen(V42, timeout=30).read().decode("utf-8")
print("ND_V50_RECOVERY_V11_V42_READY", flush=True)

try:
    exec(compile(src, "nd_v50_recovery_v11_v42.py", "exec"))
finally:
    if front.poll() is None:
        front.terminate()
