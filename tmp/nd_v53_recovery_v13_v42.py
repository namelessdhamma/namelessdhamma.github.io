import os, subprocess, time, urllib.request

FRONT="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/fe8a0ff9d029b3026b76d43863f1cc5e0168ae21/tmp/nd_safe_tool_broker_v13_research_qualification.js"
V42="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"

print("ND_V53_RECOVERY_BOOT",flush=True)
subprocess.run(["apk","add","--no-cache","nodejs"],check=True,stdout=subprocess.DEVNULL)
urllib.request.urlretrieve(FRONT,"/tmp/nd-drive-front-v13.mjs")
front_env=dict(os.environ);front_env["PORT"]=os.environ.get("PORT","3000")
front=subprocess.Popen(["node","/tmp/nd-drive-front-v13.mjs"],env=front_env)
time.sleep(5)
if front.poll() is not None:raise RuntimeError("ND V53 V13 front exited during startup")
os.environ["PORT"]="3001"
src=urllib.request.urlopen(V42,timeout=30).read().decode("utf-8")
print("ND_V53_RECOVERY_V13_V42_READY",flush=True)
try:exec(compile(src,"nd_v53_recovery_v13_v42.py","exec"))
finally:
    if front.poll() is None:front.terminate()
