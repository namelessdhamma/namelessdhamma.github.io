import os, subprocess, time, urllib.request

SIDECAR="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/16c415d4ba91b9464e814c3d6ac0531647d4c69b/tmp/nd_safe_tool_broker_v10g_node.js"
GATEWAY="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9769ed2c49a0f96ddb1e2539fcd99668cb676df2/tmp/nd_vk_gateway_v45b_drive_proxy.py"

subprocess.run(["apk","add","--no-cache","nodejs"],check=True,stdout=subprocess.DEVNULL)
urllib.request.urlretrieve(SIDECAR,"/tmp/nd-drive-broker.mjs")
env=dict(os.environ);env["PORT"]="3001"
sidecar=subprocess.Popen(["node","/tmp/nd-drive-broker.mjs"],env=env)
time.sleep(4)
if sidecar.poll() is not None:
    raise RuntimeError("ND Drive broker sidecar exited during startup")
src=urllib.request.urlopen(GATEWAY,timeout=30).read().decode("utf-8")
print("ND_V45B_LAUNCHER_READY",flush=True)
exec(compile(src,"nd_vk_gateway_v45b_drive_proxy.py","exec"))
