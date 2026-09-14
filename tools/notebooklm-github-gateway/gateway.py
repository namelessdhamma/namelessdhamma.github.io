from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

PREFIX = "/notebooklm "
VERCEL_URL = "https://nd-notebooklm-oauth-mcp.vercel.app/doctor/github"

def _decode_command(command: str) -> dict:
    if not command.startswith(PREFIX):
        raise ValueError("invalid_command_prefix")
    encoded = command[len(PREFIX):].strip()
    if not encoded:
        raise ValueError("missing_payload")
    encoded += "=" * (-len(encoded) % 4)
    raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload_must_be_object")
    return payload

def _call_vercel(payload: dict, oidc_token: str) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        VERCEL_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {oidc_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "nd-notebooklm-github-gateway/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"ok": False, "error": f"upstream_http_{exc.code}"}
        return exc.code, parsed

def _comment(issue_number: str, repo: str, gh_token: str, payload: dict) -> None:
    text = "ND NotebookLM Gateway\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2)[:60000] + "\n```"
    body = json.dumps({"body": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nd-notebooklm-github-gateway/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30):
        pass

def main() -> None:
    command = os.environ["COMMAND"]
    oidc_token = os.environ["OIDC_TOKEN"]
    gh_token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    issue_number = os.environ["ISSUE_NUMBER"]
    try:
        payload = _decode_command(command)
        status, result = _call_vercel(payload, oidc_token)
        envelope = {"http_status": status, "response": result}
    except Exception as exc:
        envelope = {"http_status": 0, "response": {"ok": False, "error": str(exc)[:1000]}}
    _comment(issue_number, repo, gh_token, envelope)

if __name__ == "__main__":
    main()
