#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import pathlib
import urllib.request

VENDOR_ROOT = pathlib.Path(os.environ.get("ND_VK_VENDOR_ROOT", "/app/vendor")).resolve()
GATEWAY_PIN = "4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"
PREFIX = "ndvendor://namelessdhamma.github.io/"
_original_urlopen = urllib.request.urlopen


class VendorResponse(io.BytesIO):
    def __init__(self, body: bytes, url: str):
        super().__init__(body)
        self.url = url
        self.status = 200
        self.headers = {"content-type": "text/plain; charset=utf-8"}

    def getcode(self):
        return 200


def _local_path(url: str) -> pathlib.Path | None:
    if not url.startswith(PREFIX):
        return None
    rel = url[len(PREFIX):]
    head, sep, _ = rel.partition("/")
    if not sep or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise RuntimeError(f"invalid ndvendor URL: {url}")
    target = (VENDOR_ROOT / rel).resolve()
    if VENDOR_ROOT not in target.parents:
        raise RuntimeError(f"ndvendor path escape denied: {url}")
    return target


def ndvendor_urlopen(url, *args, **kwargs):
    raw = getattr(url, "full_url", url)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    raw = str(raw)
    local = _local_path(raw)
    if local is None:
        return _original_urlopen(url, *args, **kwargs)
    return VendorResponse(local.read_bytes(), raw)


urllib.request.urlopen = ndvendor_urlopen
os.environ["PORT"] = os.environ.get("ND_VK_INNER_PORT", "3001")
source_path = VENDOR_ROOT / GATEWAY_PIN
source = source_path.read_text(encoding="utf-8")
print("ND_VK_GATEWAY_LOCAL_VENDOR_BOOT", {"pin": GATEWAY_PIN}, flush=True)
exec(compile(source, str(source_path), "exec"), {"__name__": "__main__", "__file__": str(source_path)})
