#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

MCP_URL = "https://mcp.browserless.io/mcp"
API_VERSION = "2022-11-28"

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "").strip()
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "").strip()
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "").strip()
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER", "").strip()
COMMAND = os.environ.get("COMMAND", "").strip().lower()
if COMMAND.startswith("[browserless] "):
    COMMAND = "/browserless " + COMMAND[len("[browserless] "):]
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


def create_profile_session(profile_name):
    url = (
        "https://production-sfo.browserless.io/profile?token="
        + urllib.parse.quote(BROWSERLESS_TOKEN, safe="")
        + "&timeout=120000"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"name": profile_name}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ND-Browserless-GitHub-Gateway/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(
            "Browserless profile API HTTP {}: {}".format(e.code, redact(body[:1200]))
        )


def verify_profile_direct(profile_name):
    from playwright.sync_api import sync_playwright

    ws = (
        "wss://production-sfo.browserless.io/chromium/playwright?token="
        + urllib.parse.quote(BROWSERLESS_TOKEN, safe="")
        + "&profile="
        + urllib.parse.quote(profile_name, safe="")
    )
    with sync_playwright() as p:
        browser = p.chromium.connect(ws, timeout=30000)
        try:
            contexts = browser.contexts
            context = contexts[0] if contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://github.com/", wait_until="domcontentloaded", timeout=30000)
            user = page.evaluate(
                "() => document.querySelector('meta[name=\\\"user-login\\\"]')?.content || ''"
            )
            return bool(user), str(user or ""), page.url
        finally:
            browser.close()


def command_start_github_auth(mcp):
    from playwright.sync_api import sync_playwright

    profile_name = "nd-github"
    session = create_profile_session(profile_name)
    connect = session.get("connect")
    if not connect:
        raise RuntimeError("Browserless /profile response did not include connect")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(connect, timeout=30000)
        try:
            if not browser.contexts:
                raise RuntimeError("Browserless profile session has no browser context")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                "https://github.com/login",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            cdp = context.new_cdp_session(page)
            live = cdp.send(
                "Browserless.liveURL",
                {
                    "timeout": 100000,
                    "interactable": True,
                    "quality": 70,
                    "type": "jpeg",
                    "resizable": True,
                },
            )
            live_url = live.get("liveURL")
            if not live_url:
                raise RuntimeError("Browserless.liveURL did not return a liveURL")

            comment(
                "ND Browserless Gateway - GitHub login window is live\n\n"
                + live_url
                + "\n\nOpen it immediately. This same Browserless profile-creation "
                "session is being monitored. Once GitHub reports the account as "
                "signed in, the gateway will save nd-github automatically."
            )

            deadline = time.time() + 96
            authenticated_user = ""
            while time.time() < deadline:
                try:
                    authenticated_user = page.evaluate(
                        "() => document.querySelector('meta[name=\\\"user-login\\\"]')?.content || ''"
                    )
                    if authenticated_user:
                        break
                except Exception:
                    pass
                time.sleep(2)

            if not authenticated_user:
                comment(
                    "ND Browserless Gateway - GitHub login: TIMEOUT\n\n"
                    "No authenticated GitHub state was detected before the Free-plan "
                    "session deadline. Start the flow again when ready."
                )
                raise RuntimeError("GitHub authentication was not detected before timeout")

            saved = cdp.send("Browserless.saveProfile", {"name": profile_name})
            if not saved.get("ok"):
                raise RuntimeError("Browserless.saveProfile failed: " + redact(saved))

        finally:
            browser.close()

    ok, user, url = verify_profile_direct(profile_name)
    state = "PASS" if ok else "FAIL"
    comment(
        "ND Browserless Gateway - GitHub qualification: {}\n\n"
        "- authenticated user detected: {}\n"
        "- Browserless.saveProfile(nd-github): PASS\n"
        "- fresh-session profile reuse: {}\n"
        "- fresh URL: {}\n".format(state, user or "(none)", state, url)
    )
    if not ok:
        raise RuntimeError("Profile saved but fresh-session reuse failed")

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
