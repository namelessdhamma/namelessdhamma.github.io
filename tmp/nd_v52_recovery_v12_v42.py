import os, subprocess, time, urllib.request

# ND VK recovery V52
# Reuses the proven V42 Father VK gateway and V12 Safe Tool front.
# V12 differs from proven V11 only by a bounded startup qualification probe
# for sandbox_research_save with mandatory sandbox_read verification.
FRONT="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/cfecd50305738b4f640eb6803a72335332c861fe/tmp/nd_safe_tool_broker_v12_research_qualification.js"
V42="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"

print("ND_V52_RECOVERY_BOOT", flush=True)
subprocess.run(["apk","add","--no-cache","nodejs"],check=True,stdout=subprocess.DEVNULL)
urllib.request.urlretrieve(FRONT,"/tmp/nd-drive-front-v12.mjs")
front_env=dict(os.environ)
front_env["PORT"]=os.environ.get("PORT","3000")
front=subprocess.Popen(["node","/tmp/nd-drive-front-v12.mjs"],env=front_env)
time.sleep(5)
if front.poll() is not None:
    raise RuntimeError("ND V52 V12 front exited during startup")

os.environ["PORT"]="3001"
src=urllib.request.urlopen(V42,timeout=30).read().decode("utf-8")
print("ND_V52_RECOVERY_V12_V42_READY", flush=True)
try:
    exec(compile(src,"nd_v52_recovery_v12_v42.py","exec"))
finally:
    if front.poll() is None:
        front.terminate()
