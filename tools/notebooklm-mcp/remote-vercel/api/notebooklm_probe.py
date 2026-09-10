import importlib.metadata
import json
from http.server import BaseHTTPRequestHandler

import grpc
import gpsoauth
from google.protobuf import __version__ as protobuf_version
from notebooklm import NotebookLMClient


def build_probe_payload() -> dict[str, object]:
    ctx = NotebookLMClient.from_storage(profile="default", backend="android")
    return {
        "ok": True,
        "probe": "notebooklm-android-runtime",
        "notebooklm_py": importlib.metadata.version("notebooklm-py"),
        "grpcio": grpc.__version__,
        "protobuf": protobuf_version,
        "gpsoauth_import": bool(gpsoauth),
        "android_context_constructed": ctx is not None,
        "auth_attempted": False,
        "contains_user_data": False,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(build_probe_payload()).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
