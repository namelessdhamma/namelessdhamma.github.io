import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8080"))
STATE = {
    "service": "ND Browserless Railway Relay",
    "version": "1.0.0",
    "configured": bool(os.environ.get("BROWSERLESS_API_TOKEN", "").strip()),
    "status": "ready",
}

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/health":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(STATE).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

HTTPServer(("0.0.0.0", PORT), H).serve_forever()
