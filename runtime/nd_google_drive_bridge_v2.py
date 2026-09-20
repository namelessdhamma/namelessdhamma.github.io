import base64, json, os, threading, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from google.oauth2 import service_account
from google.auth.transport.requests import Request

PORT=int(os.environ.get("PORT","3000"))
BRIDGE_KEY=os.environ.get("ND_DRIVE_BRIDGE_TOKEN","").strip()
WRITE_IDS={x.strip() for x in (os.environ.get("ND_DRIVE_MCP_WRITABLE_FILE_IDS","")+","+os.environ.get("ND_DRIVE_WRITABLE_FILE_IDS","")+","+os.environ.get("ND_DRIVE_QUALIFICATION_FILE_ID","")).split(",") if x.strip()}
SCOPES=["https://www.googleapis.com/auth/drive","https://www.googleapis.com/auth/documents"]
_lock=threading.Lock()
_creds=None

def credential_info():
    email=os.environ.get("ND_GOOGLE_CLIENT_EMAIL","").strip()
    raw_b64=os.environ.get("ND_GOOGLE_PRIVATE_KEY_B64","").strip()
    if not raw_b64:
        raise RuntimeError("ND_GOOGLE_PRIVATE_KEY_B64 missing")
    raw=base64.b64decode(raw_b64).decode("utf-8")
    try:
        obj=json.loads(raw)
        email=obj.get("client_email") or email
        key=obj.get("private_key","")
    except Exception:
        key=raw
    key=key.replace("\\n","\n")
    if not email or "BEGIN PRIVATE KEY" not in key:
        raise RuntimeError("service account material incomplete")
    return {"type":"service_account","project_id":"nd-drive-bridge","private_key_id":"runtime","private_key":key,
            "client_email":email,"client_id":"runtime","auth_uri":"https://accounts.google.com/o/oauth2/auth",
            "token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url":""}

def creds():
    global _creds
    with _lock:
        if _creds is None:
            _creds=service_account.Credentials.from_service_account_info(credential_info(),scopes=SCOPES)
        if not _creds.valid or _creds.expired or not _creds.token:
            _creds.refresh(Request())
        return _creds

def req_json(url,method="GET",body=None):
    c=creds()
    headers={"Authorization":"Bearer "+c.token,"Accept":"application/json","User-Agent":"ND-Google-Drive-Bridge/2.0"}
    data=None
    if body is not None:
        data=json.dumps(body,ensure_ascii=False).encode("utf-8")
        headers["Content-Type"]="application/json"
    r=urllib.request.Request(url,data=data,method=method,headers=headers)
    try:
        with urllib.request.urlopen(r,timeout=90) as resp:
            txt=resp.read().decode("utf-8","replace")
            return json.loads(txt) if txt else {}
    except HTTPError as e:
        txt=e.read().decode("utf-8","replace")
        raise RuntimeError("HTTP_%s:%s"%(e.code,txt[:1000]))

def drive_meta(fid):
    fields="id,name,mimeType,modifiedTime,version,trashed,md5Checksum,sha1Checksum,sha256Checksum,parents"
    return req_json("https://www.googleapis.com/drive/v3/files/%s?supportsAllDrives=true&fields=%s"%(urllib.parse.quote(fid),urllib.parse.quote(fields)))

def docs_get(fid):
    return req_json("https://docs.googleapis.com/v1/documents/%s?includeTabsContent=true"%urllib.parse.quote(fid))

def collect_structural(elements,out):
    for el in elements or []:
        p=el.get("paragraph")
        if p:
            for pe in p.get("elements",[]):
                tr=pe.get("textRun")
                if tr and tr.get("content"): out.append(tr["content"])
        t=el.get("table")
        if t:
            for row in t.get("tableRows",[]):
                for cell in row.get("tableCells",[]): collect_structural(cell.get("content",[]),out)
        toc=el.get("tableOfContents")
        if toc: collect_structural(toc.get("content",[]),out)

def doc_text(doc):
    out=[]
    if doc.get("tabs"):
        def walk(tab):
            dc=(tab.get("documentTab") or {})
            collect_structural((dc.get("body") or {}).get("content",[]),out)
            for child in tab.get("childTabs") or []: walk(child)
        for t in doc.get("tabs") or []: walk(t)
    else:
        collect_structural((doc.get("body") or {}).get("content",[]),out)
    return "".join(out)

def docs_read(fid):
    d=docs_get(fid)
    return {"document_id":fid,"title":d.get("title"),"revision_id":d.get("revisionId"),"text":doc_text(d)}

def batch(fid,requests,expected=None):
    body={"requests":requests}
    if expected: body["writeControl"]={"requiredRevisionId":expected}
    return req_json("https://docs.googleapis.com/v1/documents/%s:batchUpdate"%urllib.parse.quote(fid),"POST",body)

def ensure_write(fid):
    if fid not in WRITE_IDS: raise RuntimeError("tool_denied:file_not_in_writable_allowlist")

def invoke(tool,args):
    if tool=="bridge_identity":
        return {"client_email":credential_info()["client_email"],"write_allowlist_count":len(WRITE_IDS),"bridge_version":"2.0"}
    if tool in ("drive_get_metadata","drive_get_currentness_token"):
        fid=str(args.get("file_id") or args.get("document_id") or "")
        if not fid: raise RuntimeError("file_id required")
        m=drive_meta(fid)
        out={"file_id":fid,"name":m.get("name"),"mime_type":m.get("mimeType"),"drive_version":m.get("version"),
             "modified_time":m.get("modifiedTime"),"trashed":m.get("trashed",False),"md5":m.get("md5Checksum"),
             "sha1":m.get("sha1Checksum"),"sha256":m.get("sha256Checksum")}
        if m.get("mimeType")=="application/vnd.google-apps.document":
            out["docs_revision_id"]=docs_get(fid).get("revisionId")
        return out
    if tool=="docs_read":
        fid=str(args.get("document_id") or "")
        if not fid: raise RuntimeError("document_id required")
        return docs_read(fid)
    if tool=="docs_append":
        fid=str(args.get("document_id") or ""); text=str(args.get("text") or "")
        ensure_write(fid)
        before=docs_read(fid); exp=args.get("expected_revision_id") or before.get("revision_id")
        r=batch(fid,[{"insertText":{"endOfSegmentLocation":{},"text":text}}],exp)
        after=docs_read(fid)
        return {"document_id":fid,"before_revision_id":before.get("revision_id"),"after_revision_id":after.get("revision_id"),"write_control":r.get("writeControl"),"text_length":len(after.get("text") or "")}
    if tool=="docs_replace_exact":
        fid=str(args.get("document_id") or ""); old=str(args.get("old_text") or ""); new=str(args.get("new_text") or "")
        ensure_write(fid)
        before=docs_read(fid); text=before.get("text") or ""
        count=text.count(old)
        if count!=1: raise RuntimeError("exact_match_count_%d"%count)
        exp=args.get("expected_revision_id") or before.get("revision_id")
        r=batch(fid,[{"replaceAllText":{"containsText":{"text":old,"matchCase":True},"replaceText":new}}],exp)
        after=docs_read(fid)
        return {"document_id":fid,"occurrences_changed":((r.get("replies") or [{}])[0].get("replaceAllText") or {}).get("occurrencesChanged"),"before_revision_id":before.get("revision_id"),"after_revision_id":after.get("revision_id"),"write_control":r.get("writeControl")}
    raise RuntimeError("tool_denied:"+tool)

class H(BaseHTTPRequestHandler):
    server_version="NDDriveBridge/2.0"
    def log_message(self,fmt,*args): print("HTTP "+(fmt%args),flush=True)
    def sendj(self,status,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith("/health"):
            try:
                c=creds()
                self.sendj(200,{"ok":True,"service":"nd-google-drive-bridge","version":"2.0","auth":bool(c.token)})
            except Exception as e: self.sendj(503,{"ok":False,"error":str(e)[:500]})
        else: self.sendj(404,{"ok":False})
    def do_POST(self):
        if self.path!="/drive/invoke": return self.sendj(404,{"ok":False})
        if not BRIDGE_KEY or self.headers.get("X-ND-Bridge-Key","")!=BRIDGE_KEY: return self.sendj(401,{"ok":False,"error":"unauthorized"})
        try:
            n=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(n) or b"{}")
            result=invoke(str(payload.get("tool") or ""),payload.get("args") or {})
            self.sendj(200,{"ok":True,"result":result})
        except Exception as e:
            msg=str(e)
            status=409 if "HTTP_409" in msg or "revision" in msg.lower() and "mismatch" in msg.lower() else 400
            self.sendj(status,{"ok":False,"error":msg[:1200]})

if __name__=="__main__":
    print(json.dumps({"event":"ND_GOOGLE_DRIVE_BRIDGE_START","port":PORT,"version":"2.0","write_allowlist_count":len(WRITE_IDS)}),flush=True)
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
