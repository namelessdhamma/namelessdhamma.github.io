import json
import os
import subprocess
import threading
import time
import urllib.request
from urllib.error import HTTPError

FRONT="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6b89d7d316d3abe8908509402a08e75d065a628d/tmp/nd_safe_tool_broker_v11_front.js"
GATEWAY="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/4bd76056902e914708ff7513352c53d1d4f765a3/tmp/nd_vk_gateway_v42_father_handoff.py"
DOC="1N_cYTm6zXXQXKTBAaPGq_eBt28tzhTB5HahCF8W-ZLc"
MARKER="\n[ND_DRIVE_QUALIFICATION_20260911_1820_ICT]\n"
STALE_MARKER="\n[ND_DRIVE_STALE_WRITE_SHOULD_NOT_PERSIST_20260911]\n"

subprocess.run(["apk","add","--no-cache","nodejs"],check=True,stdout=subprocess.DEVNULL)
urllib.request.urlretrieve(FRONT,"/tmp/nd-drive-front.mjs")
front_env=dict(os.environ)
front_env["PORT"]=os.environ.get("PORT","3000")
front=subprocess.Popen(["node","/tmp/nd-drive-front.mjs"],env=front_env)
time.sleep(4)
if front.poll() is not None:
    raise RuntimeError("ND Drive front exited during startup")

def invoke(tool,args):
    token=os.environ.get("ND_DRIVE_BRIDGE_TOKEN","")
    if len(token)<24:
        raise RuntimeError("bridge token unavailable")
    data=json.dumps({"tool":tool,"args":args},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(
        "http://127.0.0.1:3000/drive/invoke",
        data=data,
        method="POST",
        headers={
            "Content-Type":"application/json",
            "Accept":"application/json",
            "X-ND-Bridge-Key":token,
            "User-Agent":"nd-drive-qualification/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            payload=json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        body=e.read().decode("utf-8","replace")
        raise RuntimeError("HTTP %s: %s"%(e.code,body[:500])) from e
    if not payload.get("ok"):
        raise RuntimeError("invalid bridge response")
    return payload.get("result") or {}

def qualify():
    unexpected=False
    stale_error=None
    try:
        time.sleep(2)
        before_token=invoke("drive_get_currentness_token",{"file_id":DOC})
        before_doc=invoke("docs_read",{"document_id":DOC})
        before_rev=before_doc.get("revision_id")
        append=invoke("docs_append",{"document_id":DOC,"text":MARKER,"expected_revision_id":before_rev})
        after_doc=invoke("docs_read",{"document_id":DOC})
        after_token=invoke("drive_get_currentness_token",{"file_id":DOC})
        stale_rejected=False
        try:
            invoke("docs_append",{"document_id":DOC,"text":STALE_MARKER,"expected_revision_id":before_rev})
            unexpected=True
        except Exception as e:
            stale_error=str(e)[:500]
            stale_rejected="REVISION_MISMATCH" in stale_error
        d=invoke("docs_read",{"document_id":DOC})
        if unexpected and STALE_MARKER in d.get("text",""):
            invoke("docs_replace_exact",{"document_id":DOC,"old_text":STALE_MARKER,"new_text":"","expected_revision_id":d.get("revision_id")})
            d=invoke("docs_read",{"document_id":DOC})
        cleanup=invoke("docs_replace_exact",{"document_id":DOC,"old_text":MARKER,"new_text":"","expected_revision_id":d.get("revision_id")})
        final_doc=invoke("docs_read",{"document_id":DOC})
        final_token=invoke("drive_get_currentness_token",{"file_id":DOC})
        start=invoke("drive_changes_start_token",{})
        changes=invoke("drive_changes_list",{"page_token":start.get("start_page_token"),"page_size":10})
        passed=(
            MARKER in after_doc.get("text","")
            and append.get("after_revision_id")!=before_rev
            and stale_rejected
            and not unexpected
            and MARKER not in final_doc.get("text","")
            and STALE_MARKER not in final_doc.get("text","")
        )
        print("ND_DRIVE_QUALIFICATION",json.dumps({
            "ok":passed,
            "title":before_doc.get("title"),
            "text_chars_before":len(before_doc.get("text","")),
            "before":{
                "drive_version":before_token.get("drive_version"),
                "modified_time":before_token.get("modified_time"),
                "revision_id":before_rev,
            },
            "append":{
                "after_revision_id":append.get("after_revision_id"),
                "marker_readback":MARKER in after_doc.get("text",""),
                "drive_version":after_token.get("drive_version"),
                "modified_time":after_token.get("modified_time"),
            },
            "stale_guard":{"rejected":stale_rejected,"error":stale_error,"unexpected_write":unexpected},
            "cleanup":{
                "after_revision_id":cleanup.get("after_revision_id"),
                "marker_absent":MARKER not in final_doc.get("text","") and STALE_MARKER not in final_doc.get("text",""),
            },
            "final":{
                "drive_version":final_token.get("drive_version"),
                "modified_time":final_token.get("modified_time"),
                "revision_id":final_doc.get("revision_id"),
            },
            "changes":{
                "start_token_present":bool(start.get("start_page_token")),
                "new_start_token_present":bool(changes.get("newStartPageToken")),
                "returned":len(changes.get("changes") or []),
            },
            "authority_mutated":False,
        },ensure_ascii=False),flush=True)
    except Exception as e:
        print("ND_DRIVE_QUALIFICATION",json.dumps({"ok":False,"error":str(e)[:700],"authority_mutated":False},ensure_ascii=False),flush=True)
        try:
            d=invoke("docs_read",{"document_id":DOC})
            if STALE_MARKER in d.get("text",""):
                invoke("docs_replace_exact",{"document_id":DOC,"old_text":STALE_MARKER,"new_text":"","expected_revision_id":d.get("revision_id")})
                d=invoke("docs_read",{"document_id":DOC})
            if MARKER in d.get("text",""):
                invoke("docs_replace_exact",{"document_id":DOC,"old_text":MARKER,"new_text":"","expected_revision_id":d.get("revision_id")})
        except Exception as clean:
            print("ND_DRIVE_QUALIFICATION_CLEANUP",str(clean)[:500],flush=True)

threading.Thread(target=qualify,daemon=True).start()

os.environ["PORT"]="3001"
src=urllib.request.urlopen(GATEWAY,timeout=30).read().decode("utf-8")
print("ND_V13_QUALIFICATION_LAUNCHER_READY",flush=True)
exec(compile(src,"nd_vk_gateway_v42_father_handoff.py","exec"))
