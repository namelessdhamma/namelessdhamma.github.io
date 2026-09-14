#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

MCP_URL = "https://mcp.browserless.io/mcp"
API_VERSION = "2022-11-28"

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "").strip()
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "").strip()
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "").strip()
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER", "").strip()
COMMAND = os.environ.get("COMMAND", "").strip().lower()
ACTOR = os.environ.get("ACTOR", "").strip()


def redact(value):
    value = str(value)
    if BROWSERLESS_TOKEN:
        value = value.replace(BROWSERLESS_TOKEN, "[REDACTED]")
    if GITHUB_TOKEN:
        value = value.replace(GITHUB_TOKEN, "[REDACTED]")
    return value


def github_request(method, path, body=None):
    url = "https://api.github.com" + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "ND-Browserless-GitHub-Gateway/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
        return json.loads(raw) if raw else {}


def comment(text):
    if not (GITHUB_TOKEN and REPOSITORY and ISSUE_NUMBER):
        print(redact(text))
        return
    github_request(
        "POST",
        "/repos/{}/issues/{}/comments".format(REPOSITORY, ISSUE_NUMBER),
        {"body": text[:65000]},
    )


def parse_sse(raw):
    payloads = []
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("data: "):
            try:
                payloads.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    if not payloads:
        raise RuntimeError("Browserless MCP returned no parsable SSE data")
    return payloads[-1]


class BrowserlessMCP:
    def __init__(self, token):
        self.token = token
        self.session_id = None

    def post(self, payload, use_session=False):
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "ND-Browserless-GitHub-Gateway/1.0",
        }
        if use_session:
            if not self.session_id:
                raise RuntimeError("MCP session is not initialized")
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = "2025-06-18"
        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                if not use_session:
                    self.session_id = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
                if not raw:
                    return {}
                return parse_sse(raw)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError("Browserless MCP HTTP {}: {}".format(e.code, redact(body[:1200])))

    def initialize(self):
        self.post({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "ND Browserless GitHub Gateway",
                    "version": "1.0",
                },
            },
        })
        if not self.session_id:
            raise RuntimeError("Browserless MCP did not return Mcp-Session-Id")
        self.post({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }, use_session=True)

    def call(self, name, arguments=None):
        msg = self.post({
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1000000000,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }, use_session=True)
        result = msg.get("result") or {}
        if result.get("isError"):
            raise RuntimeError(content_text(result) or json.dumps(result))
        return result


def content_text(result):
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict):
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(parts)


def extract_session_id(text):
    patterns = [
        r"sessionId\s*[:=]\s*[\"']?([A-Za-z0-9._:-]+)",
        r"\"sessionId\"\s*:\s*\"([^\"]+)\"",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).rstrip(".,")
    return None


def extract_live_url(text):
    urls = re.findall(r"https://[^\s<>\"')]+", text)
    for url in urls:
        if "github.com" not in url:
            return url.rstrip(".,")
    return urls[0].rstrip(".,") if urls else None


def signed_in_from_text(text):
    compact = re.sub(r"\s+", "", text).lower()
    return (
        "\"signedin\":true" in compact
        or "signedin:true" in compact
        or "\"user\":\"namelessdhamma\"" in compact
        or "user:namelessdhamma" in compact
    )


def agent(mcp, **kwargs):
    kwargs.setdefault("rationale", "Running browser check")
    return mcp.call("browserless_agent", kwargs)


def close_agent(mcp, session_id, profile=None):
    if not session_id:
        return
    args = {
        "method": "close",
        "sessionId": session_id,
        "rationale": "Closing browser session",
    }
    if profile:
        args["profile"] = profile
    try:
        agent(mcp, **args)
    except Exception:
        pass


def verify_profile(mcp, profile="nd-github"):
    first = agent(
        mcp,
        profile=profile,
        method="goto",
        params={"url": "https://github.com/", "waitUntil": "domcontentloaded"},
        rationale="Opening saved GitHub profile",
    )
    t1 = content_text(first)
    sid = extract_session_id(t1)
    if not sid:
        raise RuntimeError("No Browserless sessionId in profile response: " + t1[:800])
    try:
        second = agent(
            mcp,
            profile=profile,
            sessionId=sid,
            method="evaluate",
            params={
                "content": "(() => ({ href: location.href, title: document.title, user: document.querySelector('meta[name=\\\"user-login\\\"]')?.content || '', signedIn: Boolean(document.querySelector('meta[name=\\\"user-login\\\"]')?.content) }))()"
            },
            rationale="Checking saved GitHub login",
        )
        text = content_text(second)
        return signed_in_from_text(text), text
    finally:
        close_agent(mcp, sid, profile=profile)


def command_profiles(mcp):
    result = mcp.call("browserless_profiles", {"limit": 20, "offset": 0})
    comment("ND Browserless Gateway - profiles\n\n" + content_text(result)[:5000])


def command_verify(mcp):
    ok, evidence = verify_profile(mcp)
    state = "PASS" if ok else "FAIL"
    comment("ND Browserless Gateway - fresh-session GitHub profile: {}\n\n{}".format(state, evidence[:5000]))
    if not ok:
        raise RuntimeError("Saved profile did not start authenticated")


def command_start_github_auth(mcp):
    try:
        mcp.call("browserless_skill", {"site": "github.com"})
        mcp.call("browserless_skill", {"id": "autonomous-login"})
    except Exception:
        pass

    opened = agent(
        mcp,
        createProfile={"name": "nd-github"},
        method="goto",
        params={"url": "https://github.com/login", "waitUntil": "domcontentloaded"},
        rationale="Opening GitHub login",
    )
    opened_text = content_text(opened)
    sid = extract_session_id(opened_text)
    if not sid:
        raise RuntimeError("Browserless did not return a profile sessionId: " + opened_text[:1000])

    live = agent(
        mcp,
        sessionId=sid,
        method="liveURL",
        params={"timeout": 100000, "interactable": True},
        rationale="Sharing live GitHub login",
    )
    live_text = content_text(live)
    live_url = extract_live_url(live_text)
    if not live_url:
        close_agent(mcp, sid)
        raise RuntimeError("Browserless did not return a liveURL: " + live_text[:1000])

    comment(
        "ND Browserless Gateway - GitHub login window is live\n\n"
        + live_url
        + "\n\nOpen it immediately. The gateway is monitoring the same Browserless session and will save nd-github automatically when GitHub reports the account is signed in."
    )

    deadline = time.time() + 95
    authenticated = False
    evidence = ""
    while time.time() < deadline:
        time.sleep(4)
        try:
            check = agent(
                mcp,
                sessionId=sid,
                method="evaluate",
                params={
                    "content": "(() => ({ href: location.href, title: document.title, user: document.querySelector('meta[name=\\\"user-login\\\"]')?.content || '', signedIn: Boolean(document.querySelector('meta[name=\\\"user-login\\\"]')?.content) }))()"
                },
                rationale="Monitoring GitHub login",
            )
            evidence = content_text(check)
            if signed_in_from_text(evidence):
                authenticated = True
                break
        except Exception as e:
            evidence = redact(e)
            time.sleep(2)

    if not authenticated:
        close_agent(mcp, sid)
        comment(
            "ND Browserless Gateway - GitHub login: TIMEOUT\n\n"
            "The live window ended before an authenticated GitHub state was detected. Run /browserless start-github-auth again when ready."
        )
        raise RuntimeError("GitHub authentication was not detected before timeout")

    saved = agent(
        mcp,
        sessionId=sid,
        method="saveProfile",
        params={"name": "nd-github"},
        rationale="Saving GitHub profile",
    )
    saved_text = content_text(saved)
    close_agent(mcp, sid)

    ok, fresh_evidence = verify_profile(mcp, "nd-github")
    state = "PASS" if ok else "FAIL"
    comment(
        "ND Browserless Gateway - GitHub qualification: {}\n\n"
        "- human login detected in the live Browserless session\n"
        "- saveProfile(nd-github) executed\n"
        "- fresh-session profile reuse: {}\n\n"
        "Fresh-session evidence:\n{}\n\nSave response:\n{}".format(
            state, state, fresh_evidence[:4000], saved_text[:2000]
        )
    )
    if not ok:
        raise RuntimeError("Profile was saved but fresh-session reuse failed")


def main():
    if ACTOR != "namelessdhamma":
        print("Ignoring command from non-owner actor")
        return 0
    if not BROWSERLESS_TOKEN:
        comment(
            "ND Browserless Gateway - configuration required\n\n"
            "Repository secret BROWSERLESS_API_TOKEN is not configured. No Browserless request was attempted."
        )
        return 2
    if not GITHUB_TOKEN:
        raise RuntimeError("GH_TOKEN is missing")

    mcp = BrowserlessMCP(BROWSERLESS_TOKEN)
    mcp.initialize()

    if COMMAND == "/browserless profiles":
        command_profiles(mcp)
    elif COMMAND == "/browserless verify-github-profile":
        command_verify(mcp)
    elif COMMAND == "/browserless start-github-auth":
        command_start_github_auth(mcp)
    else:
        comment(
            "ND Browserless Gateway - unknown command\n\n"
            "Supported commands:\n"
            "- /browserless profiles\n"
            "- /browserless start-github-auth\n"
            "- /browserless verify-github-profile"
        )
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        message = redact(e)
        try:
            comment("ND Browserless Gateway - ERROR\n\n" + message[:5000])
        except Exception:
            pass
        print(message, file=sys.stderr)
        sys.exit(1)
