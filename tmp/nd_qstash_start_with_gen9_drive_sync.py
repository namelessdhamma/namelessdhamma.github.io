import json, os, subprocess, sys, urllib.request, traceback

SYNC_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/f0a6dd0feac8bd3c1989ccc8cacb4769af144583/tmp/nd_drive_gen9_sync_v2.py"
RUNTIME_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/61bc11a0025e0c4b32dc555d9248ff87261dd7f8/tmp/nd_gateway_browserless_frontproxy_v10_memos_kernel_bootstrap.py"

try:
    subprocess.run(["apk","add","--no-cache","openssl"],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    sync_src=urllib.request.urlopen(SYNC_URL,timeout=30).read().decode("utf-8")
    ns={"__name__":"nd_drive_gen9_sync_v2"}
    exec(compile(sync_src,"nd_drive_gen9_sync_v2.py","exec"),ns,ns)
    ns["main"]()
except Exception as e:
    print("ND_GEN9_DRIVE_SYNC_WRAPPER_ERROR "+json.dumps({"error":str(e)[:1000]}),flush=True)
    traceback.print_exc()

src=urllib.request.urlopen(RUNTIME_URL,timeout=30).read().decode("utf-8")
needle="threading.Thread(target=drive_qualify_once,daemon=True).start()"
assert src.count(needle)==1,"unexpected_drive_qualification_invocation_count"
src=src.replace(needle,"# Drive startup qualification invocation disabled after Generation 8.1 adoption",1)
exec(compile(src,"nd_gateway_browserless_frontproxy_v10_memos_kernel_bootstrap.py","exec"))
