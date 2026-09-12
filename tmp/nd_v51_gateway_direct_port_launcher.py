import os, urllib.request

# V51 stabilization candidate: preserve the immutable, previously-qualified V46
# gateway/model-routing logic, but remove the obsolete in-process Node/Drive
# front. VK already reaches the independently deployed Safe Tool Broker through
# ND_GOOGLE_GATEWAY_URL, so a second broker/front inside the gateway service is
# not part of the VK authority boundary and must not be able to kill startup.
#
# This is intentionally a bounded compatibility launcher, not a new semantic
# gateway or broker implementation. It changes only process topology:
#   before: Railway PORT -> embedded Node front -> Python VK gateway on 3001
#   after:  Railway PORT -> Python VK gateway directly
#
# Fail closed: if the exact immutable V46 bootstrap shape is not present, abort
# instead of executing a partially modified launcher.
V46 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9a9872a6ba0fba807ef6b7e4139e95de14a88c6a/tmp/nd_v46_fail_closed_strong_free_launcher.py"

src = urllib.request.urlopen(V46, timeout=30).read().decode("utf-8")

front_const = 'FRONT = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js"\n'
front_boot = '''subprocess.run(["apk", "add", "--no-cache", "nodejs"], check=True, stdout=subprocess.DEVNULL)\nurllib.request.urlretrieve(FRONT, "/tmp/nd-drive-front.mjs")\nfront_env = dict(os.environ)\nfront_env["PORT"] = os.environ.get("PORT", "3000")\nfront = subprocess.Popen(["node", "/tmp/nd-drive-front.mjs"], env=front_env)\ntime.sleep(4)\nif front.poll() is not None:\n    raise RuntimeError("ND Drive front exited during startup")\n\nos.environ["PORT"] = "3001"\n'''

if front_const not in src:
    raise RuntimeError("V51 expected V46 FRONT constant missing")
if front_boot not in src:
    raise RuntimeError("V51 expected V46 embedded-front bootstrap missing")

src = src.replace(front_const, "", 1)
src = src.replace(front_boot, "", 1)

# The legacy variable has previously been involved in staged launcher drift. It
# is not part of V46's contract. Remove it only from this process environment so
# downstream code cannot accidentally treat it as executable source. Railway's
# stored secret/config value is not changed by this launcher.
os.environ.pop("ND_TW_UPLOAD_SRC", None)

print("ND_V51_DIRECT_PORT_LAUNCHER_READY", flush=True)
exec(compile(src, "nd_v51_v46_direct_port.py", "exec"))
