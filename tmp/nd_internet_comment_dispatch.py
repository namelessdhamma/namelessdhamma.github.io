import base64, json, os, subprocess, sys

PREFIX="/internet "
ALLOWED={"status","browserless","kernel","tinyfish","lightpanda","cloudflare","apify"}

def decode(command):
    if not command.startswith(PREFIX):
        raise ValueError("invalid_command_prefix")
    raw=command[len(PREFIX):].strip()
    if not raw:
        raise ValueError("missing_payload")
    raw += "=" * (-len(raw) % 4)
    payload=json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
    if not isinstance(payload,dict):
        raise ValueError("payload_must_be_object")
    provider=str(payload.get("provider","")).strip().lower()
    if provider not in ALLOWED:
        raise ValueError("unsupported_provider")
    tool=str(payload.get("tool","__tools__")).strip() or "__tools__"
    arguments=payload.get("arguments",{})
    if not isinstance(arguments,dict):
        raise ValueError("arguments_must_be_object")
    request_key=str(payload.get("request_key","")).strip()
    return provider,tool,arguments,request_key

def main():
    provider,tool,args,request_key=decode(os.environ.get("COMMAND",""))
    env=os.environ.copy()
    env["ND_PROVIDER"]=provider
    env["ND_TOOL"]=tool
    env["ND_ARGUMENTS_JSON"]=json.dumps(args,separators=(",",":"),ensure_ascii=False)
    env["ND_REQUEST_KEY"]=request_key
    if provider in {"status","browserless","kernel","tinyfish"}:
        cmd=["python3","tmp/nd_internet_mesh_gha_v1.py"]
    else:
        cmd=["node","tmp/nd_browser_reserve_gha_v2.mjs"]
    proc=subprocess.run(cmd,env=env)
    raise SystemExit(proc.returncode)

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        out={"ok":False,"error":str(exc)[:1200]}
        with open("nd-internet-failover-result.json","w",encoding="utf-8") as f:
            json.dump(out,f,ensure_ascii=False)
            f.write("\n")
        print(json.dumps(out,ensure_ascii=False),file=sys.stderr)
        raise
