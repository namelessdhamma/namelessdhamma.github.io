import io
import urllib.request

V42 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"
V13 = "https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/9ebbfe3c8dbeb9a57f23e63c34527d5e3afd46fc/tmp/nd_vk_gateway_v13_nd_readonly.py"

OLD = "paths=['00 СЕЙЧАС.md','01 ТЕМЫ.md','02 РЕШЕНИЯ.md','03 ИЗМЕНЕНИЯ.md']"
NEW = "paths=['00 ตอนนี้ — Now.md','01 แผนที่ — Maps.md','02 หัวข้อ — Topics.md','03 การเปลี่ยนแปลง — Changes.md']"

_original_urlopen = urllib.request.urlopen


def _patched_urlopen(req, *args, **kwargs):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if url == V13:
        with _original_urlopen(req, *args, **kwargs) as response:
            raw = response.read().decode("utf-8")
        if OLD not in raw:
            raise RuntimeError("V54 vault fallback marker not found")
        raw = raw.replace(OLD, NEW, 1)
        print("ND_V54_VAULT_PATHS_PATCHED", flush=True)
        return io.BytesIO(raw.encode("utf-8"))
    return _original_urlopen(req, *args, **kwargs)


urllib.request.urlopen = _patched_urlopen
try:
    source = _original_urlopen(V42, timeout=30).read().decode("utf-8")
    print("ND_V54_VAULT_PATHS_LOADER_READY", flush=True)
    exec(compile(source, "nd_vk_gateway_v54_vault_paths.py", "exec"))
finally:
    urllib.request.urlopen = _original_urlopen
