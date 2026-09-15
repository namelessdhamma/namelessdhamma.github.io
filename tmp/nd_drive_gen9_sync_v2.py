import base64, datetime, json, os, subprocess, tempfile, time, urllib.parse, urllib.request, urllib.error

DOC_ID = "1N_cYTm6zXXQXKTBAaPGq_eBt28tzhTB5HahCF8W-ZLc"
MARKER = "[ND_TRUE_MEMORY_PLUGIN_ROUTE_POLICY_GEN9_CURRENT]"
RESULT_PATH = "true-memory/qualification/drive-gen9-sync-result.json"
BLOCK = r"""

[ND_TRUE_MEMORY_PLUGIN_ROUTE_POLICY_GEN9_CURRENT]
Generation 9 Plugin & Provider Route Policy — CURRENT / BINDING

Global order:
R0 Direct provider/native MCP -> R1 independent direct backup -> R2 GitHub control -> R3 Railway existing-runtime control -> R4 authenticated browser control -> R5 Make/n8n last resort -> R6 human gate.

Binding:
NO_TOOL_SURFACE != NO_CAPABILITY
NO_CONNECTOR != NO_PROVIDER
ROUTE_FAILURE != PROVIDER_FAILURE
USER_APPROVAL_GATED_ROUTE != CAPABILITY_UNAVAILABLE
RAW_FILE_DOWNLOAD_GATED != GITHUB_CONTROL_GATED
Select routes by required semantics, not visible tool surface. Prefer autonomous routes over approval-gated equivalents. Fail over automatically. Do not request a new chat because one route failed. Writes require readback. Reuse existing services. Human interruption only after autonomous routes are exhausted.

GitHub:
Native/first-party = primary when healthy.
GitHub Direct = qualified backup / NO-DOWNLOAD MODE.
GitHub via Railway nd-qstash-control-v2 + ND_GITHUB_PAT = FULL_CONTROL_BY_SCOPE.
Kernel nd-github-admin = browser fallback.
GitSync = vault continuity only.

Railway:
Railway Direct = primary direct control.
GitHub Actions + ND_RAILWAY_RECOVERY_TOKEN = qualified independent health/restart/redeploy recovery.
Kernel nd-railway-admin = browser fallback.

Canonical authority:
true-memory/protocols/plugin-route-policy-generation-9.md
true-memory/bootstrap/plugin-route-policy-current.json
commit 5bc74c413015c16c4d2ad58794981cf81456eb00
[/ND_TRUE_MEMORY_PLUGIN_ROUTE_POLICY_GEN9_CURRENT]
"""

def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def get_google_token():
    email=(os.environ.get("ND_GOOGLE_CLIENT_EMAIL") or "").strip()
    key_b64=(os.environ.get("ND_GOOGLE_PRIVATE_KEY_B64") or "").strip()
    if not email or not key_b64:
        raise RuntimeError("google_service_account_env_missing")
    key=base64.b64decode(key_b64)
    now=int(time.time())
    header={"alg":"RS256","typ":"JWT"}
    claims={
        "iss":email,
        "scope":"https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/drive",
        "aud":"https://oauth2.googleapis.com/token",
        "iat":now,
        "exp":now+3600
    }
    signing=(b64u(json.dumps(header,separators=(",",":")).encode())+"."+b64u(json.dumps(claims,separators=(",",":")).encode())).encode()
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(key); key_path=f.name
    try:
        p=subprocess.run(["openssl","dgst","-sha256","-sign",key_path],input=signing,capture_output=True,check=True)
    finally:
        try: os.unlink(key_path)
        except Exception: pass
    assertion=signing.decode()+"."+b64u(p.stdout)
    data=urllib.parse.urlencode({
        "grant_type":"urn:ietf:params:oauth-type:jwt-bearer",
        "assertion":assertion
    }).encode()
    # RFC grant type typo guard: use exact value below.
    data=urllib.parse.urlencode({
        "grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":assertion
    }).encode()
    req=urllib.request.Request("https://oauth2.googleapis.com/token",data=data,method="POST",headers={"Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req,timeout=60) as r:
        obj=json.loads(r.read().decode())
    tok=obj.get("access_token")
    if not tok: raise RuntimeError("google_access_token_missing")
    return tok

def request_json(url, token, method="GET", payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    headers={"Authorization":"Bearer "+token,"Accept":"application/json"}
    if data is not None: headers["Content-Type"]="application/json"
    req=urllib.request.Request(url,data=data,method=method,headers=headers)
    with urllib.request.urlopen(req,timeout=90) as r:
        raw=r.read().decode()
        return json.loads(raw) if raw else {}

def doc_text(obj):
    out=[]
    for item in (obj.get("body") or {}).get("content") or []:
        para=(item.get("paragraph") or {}) if isinstance(item,dict) else {}
        for el in para.get("elements") or []:
            tr=(el.get("textRun") or {}) if isinstance(el,dict) else {}
            out.append(str(tr.get("content") or ""))
    return "".join(out)

def github_write_result(result):
    pat=(os.environ.get("ND_GITHUB_PAT") or "").strip()
    if not pat:
        raise RuntimeError("ND_GITHUB_PAT_missing")
    owner="namelessdhamma"; repo="nameless-dhamma-vault"; branch="main"
    api="https://api.github.com/repos/%s/%s/contents/%s"%(owner,repo,RESULT_PATH)
    headers={
        "Authorization":"Bearer "+pat,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "Content-Type":"application/json",
        "User-Agent":"ND-Drive-Gen9-Sync/2.0"
    }
    sha=None
    try:
        req=urllib.request.Request(api+"?ref="+branch,headers=headers,method="GET")
        with urllib.request.urlopen(req,timeout=60) as r:
            sha=json.loads(r.read().decode()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code!=404: raise
    content=(json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode()
    body={
        "message":"Record Google Drive Generation 9 sync readback",
        "content":base64.b64encode(content).decode(),
        "branch":branch
    }
    if sha: body["sha"]=sha
    req=urllib.request.Request(api,data=json.dumps(body).encode(),headers=headers,method="PUT")
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.status

def main():
    tok=get_google_token()
    url="https://docs.googleapis.com/v1/documents/"+DOC_ID
    before=request_json(url,tok)
    rev=before.get("revisionId")
    txt=doc_text(before)
    changed=False
    if MARKER not in txt:
        end_index=1
        for item in (before.get("body") or {}).get("content") or []:
            if isinstance(item,dict) and item.get("endIndex"):
                end_index=max(end_index,int(item["endIndex"]))
        payload={
            "requests":[{"insertText":{"location":{"index":max(1,end_index-1)},"text":BLOCK}}],
            "writeControl":{"requiredRevisionId":rev}
        }
        request_json(url+":batchUpdate",tok,"POST",payload)
        changed=True
    after=request_json(url,tok)
    ok=MARKER in doc_text(after)
    result={
        "ok":ok,
        "changed":changed,
        "document_id":DOC_ID,
        "before_revision":rev,
        "after_revision":after.get("revisionId"),
        "marker_present":ok,
        "canonical_commit":"5bc74c413015c16c4d2ad58794981cf81456eb00",
        "generated_at":datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    gh_status=github_write_result(result)
    result["github_result_status"]=gh_status
    print("ND_GEN9_DRIVE_SYNC "+json.dumps(result),flush=True)
    if not ok or gh_status not in (200,201): raise SystemExit(2)

if __name__=="__main__":
    main()
