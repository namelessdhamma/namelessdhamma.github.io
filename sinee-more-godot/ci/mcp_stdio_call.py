#!/usr/bin/env python3
import argparse, json, subprocess, sys

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--server", required=True)
    p.add_argument("--tool", required=True)
    p.add_argument("--args", default="{}")
    p.add_argument("--out", required=True)
    ns=p.parse_args()
    args=json.loads(ns.args)
    messages=[
        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"nd-godot-cloud","version":"1"}}},
        {"jsonrpc":"2.0","method":"notifications/initialized"},
        {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":ns.tool,"arguments":args}},
    ]
    payload="".join(json.dumps(x,separators=(",",":"))+"\n" for x in messages)
    proc=subprocess.run(["node",ns.server],input=payload,text=True,capture_output=True,timeout=300)
    responses=[]
    for line in proc.stdout.splitlines():
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    target=next((x for x in responses if x.get("id")==2),None)
    result={
        "tool":ns.tool,
        "arguments":args,
        "server_exit_code":proc.returncode,
        "response":target,
        "stderr":proc.stderr[-20000:],
    }
    with open(ns.out,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
    if target is None or "error" in target:
        return 2
    if isinstance(target.get("result"),dict) and target["result"].get("isError"):
        return 3
    return 0

if __name__=="__main__":
    sys.exit(main())
