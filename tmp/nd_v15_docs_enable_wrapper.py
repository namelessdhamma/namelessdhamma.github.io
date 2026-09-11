import urllib.request

BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/3f877a9845d0654a2f1e54850ebf25410296fd8f/tmp/nd_v13_qualification_launcher.py"
src=urllib.request.urlopen(BASE,timeout=30).read().decode("utf-8")
src=src.replace(
    "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js",
    "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1bb27fa0c61e24d373cb170c2edea61e5d3f3cbd/tmp/nd_safe_tool_broker_v14_enable_docs_front.js",
    1,
)
src=src.replace("        time.sleep(2)","        time.sleep(15)",1)
src=src.replace("ND_V13_QUALIFICATION_LAUNCHER_READY","ND_V15_DOCS_ENABLE_QUALIFICATION_LAUNCHER_READY",1)
print("ND_V15_WRAPPER_READY",flush=True)
exec(compile(src,"nd_v15_docs_enable_qualification_launcher.py","exec"))
