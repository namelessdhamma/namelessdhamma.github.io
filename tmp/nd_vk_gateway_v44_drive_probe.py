import importlib.util, json, urllib.request
print("ND_V44_DRIVE_PROBE", json.dumps({
    "google_auth": importlib.util.find_spec("google.auth") is not None,
    "google_api_client": importlib.util.find_spec("googleapiclient") is not None,
    "cryptography": importlib.util.find_spec("cryptography") is not None,
}), flush=True)
BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/82c69760bda4b0e11911e155391cc0098f5e8708/tmp/nd_vk_gateway_v43b_strong_pool.py"
src=urllib.request.urlopen(BASE,timeout=30).read().decode("utf-8")
exec(compile(src,"nd_vk_gateway_v44_drive_probe_loader.py","exec"))
