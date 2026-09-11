import os, subprocess, time, urllib.request

FRONT="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js"
GATEWAY="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"

subprocess.run(["apk","add","--no-cache","nodejs"],check=True,stdout=subprocess.DEVNULL)
urllib.request.urlretrieve(FRONT,"/tmp/nd-drive-front.mjs")
front_env=dict(os.environ)
front_env["PORT"]=os.environ.get("PORT","3000")
front=subprocess.Popen(["node","/tmp/nd-drive-front.mjs"],env=front_env)
time.sleep(4)
if front.poll() is not None:
    raise RuntimeError("ND Drive front exited during startup")

os.environ["PORT"]="3001"
src=urllib.request.urlopen(GATEWAY,timeout=30).read().decode("utf-8")
print("ND_V11_FRONT_V42_LAUNCHER_READY",flush=True)
exec(compile(src,"nd_vk_gateway_v42_father_handoff.py","exec"))
