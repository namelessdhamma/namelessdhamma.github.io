#!/usr/bin/env python3
import argparse, json, mimetypes, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request, urllib.error, urllib.parse, zipfile
from xml.etree import ElementTree as ET

RELAY="https://gg-cloud-music-studio.onrender.com"
SEED_URL="https://raw.githubusercontent.com/Ardour/ardour/aeaed7b9359a135569e58e7cb126051bfa0d61a0/libs/ardour/test/profiling/sessions/0tracks/0tracks.ardour"

def http_json(url, method="GET", data=None, headers=None, timeout=60):
    body = None if data is None else json.dumps(data).encode()
    h={"accept":"application/json", **(headers or {})}
    if body is not None: h["content-type"]="application/json"
    req=urllib.request.Request(url,data=body,headers=h,method=method)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        return json.loads(raw.decode()) if raw else {}

def http_bytes(url, headers=None, timeout=120):
    req=urllib.request.Request(url,headers=headers or {},method="GET")
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(), r.headers.get_content_type()

def post_bytes(url, data, content_type, headers=None, timeout=180):
    h={"content-type":content_type, **(headers or {})}
    req=urllib.request.Request(url,data=data,headers=h,method="POST")
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        return json.loads(raw.decode()) if raw else {}

def auth_headers(token): return {"authorization":f"Bearer {token}"}
def claim(job_id, token): return http_json(f"{RELAY}/runner/claim/{job_id}",headers=auth_headers(token))
def get_asset(job_id,name,token): return http_bytes(f"{RELAY}/runner/asset/{job_id}/{urllib.parse.quote(name)}",headers=auth_headers(token))[0]

def upload_artifact(job_id,name,path,token,mime=None):
    p=pathlib.Path(path); data=p.read_bytes()
    ctype=mime or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return post_bytes(f"{RELAY}/runner/artifact/{job_id}/{urllib.parse.quote(name)}",data,ctype,auth_headers(token))

def finish(job_id, token, ok, result, error=None):
    return http_json(f"{RELAY}/runner/result/{job_id}","POST",{"ok":bool(ok),"result_json":json.dumps(result,ensure_ascii=False),"error":error},auth_headers(token))

def seed_config(home):
    cfg=home/".config/ardour9/config"; cfg.parent.mkdir(parents=True,exist_ok=True); (cfg.parent/".a9").touch()
    cfg.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Ardour><Config>
<Option name="try-autostart-engine" value="1"/>
<Option name="hide-dummy-backend" value="0"/>
<Option name="discover-plugins-on-start" value="0"/>
<Option name="ask-replace-instrument" value="0"/>
<Option name="ask-setup-instrument" value="0"/>
</Config><Metadata/><Extra><AudioMIDISetup><EngineStates>
<State backend="None (Dummy)" driver="Normal Speed" device="Silence" input-device="" output-device=""
 sample-rate="48000" buffer-size="1024" n-periods="0" input-latency="0" output-latency="0"
 lm-input="" lm-output="" active="1" use-buffered-io="0" midi-option="No MIDI I/O" lru="1"><MIDIDevices/></State>
</EngineStates></AudioMIDISetup></Extra></Ardour>""")
    return cfg

def make_seed(root, home):
    sd=root/"GGCloud"
    if sd.exists(): shutil.rmtree(sd)
    env=os.environ.copy(); env.update({"HOME":str(home),"LANG":"C.UTF-8"})
    cp=subprocess.run(["/usr/bin/ardour9-new_session","-s","48000","-m","2",str(sd),"GGCloud"],
                      env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    sf=sd/"GGCloud.ardour"
    if not sf.exists() or sf.stat().st_size == 0:
        raise RuntimeError("ardour9-new_session did not materialize session:\n"+cp.stdout[-12000:])
    try: ET.parse(sf)
    except Exception as e: raise RuntimeError(f"invalid generated Ardour session: {e}") from e
    return sf

def restore_session(root, job, job_id, token, home):
    names={a["name"] for a in job.get("assets",[])}
    for cand in ("session.tar.gz","session.tgz"):
        if cand in names:
            arc=root/cand; arc.write_bytes(get_asset(job_id,cand,token))
            with tarfile.open(arc,"r:gz") as t: t.extractall(root)
            fs=list(root.rglob("*.ardour"))
            if not fs: raise RuntimeError("session archive contains no .ardour")
            return fs[0]
    return make_seed(root,home)

def enable_mcp(sf):
    tree=ET.parse(sf); root=tree.getroot(); cps=root.find("ControlProtocols")
    if cps is None: cps=ET.SubElement(root,"ControlProtocols")
    target=next((x for x in cps.findall("Protocol") if x.get("name")=="MCP HTTP Server (Experimental)"),None)
    if target is None: target=ET.SubElement(cps,"Protocol")
    target.attrib.update({"name":"MCP HTTP Server (Experimental)","active":"yes","port":"4820","debug-level":"1","config":""})
    tree.write(sf,encoding="UTF-8",xml_declaration=True)

def mcp_post(obj, timeout=10):
    req=urllib.request.Request("http://127.0.0.1:4820/mcp",data=json.dumps(obj).encode(),headers={"content-type":"application/json","accept":"application/json, text/event-stream"},method="POST")
    with urllib.request.urlopen(req,timeout=timeout) as r: raw=r.read().decode()
    if raw.lstrip().startswith("data:"):
        raw=[x[5:].strip() for x in raw.splitlines() if x.startswith("data:")][-1]
    return json.loads(raw) if raw else {}

def start_ardour(sf, home, work):
    env=os.environ.copy(); env.update({"HOME":str(home),"DISPLAY":":99","LANG":"C.UTF-8","USER":"root","LOGNAME":"root","ARDOUR_TRY_AUTOSTART_ENGINE":"1"})
    xvlog=open(work/"xvfb.log","wb"); xv=subprocess.Popen(["Xvfb",":99","-screen","0","1280x800x24"],stdout=xvlog,stderr=subprocess.STDOUT,env=env); time.sleep(1)
    log=open(work/"ardour.log","wb"); proc=subprocess.Popen(["dbus-run-session","--","/usr/bin/ardour","-a","-n","-P",str(sf)],stdout=log,stderr=subprocess.STDOUT,env=env)
    setup_accepted=False
    for _ in range(90):
        if proc.poll() is not None: break
        if not setup_accepted:
            try:
                wins=subprocess.check_output(["xdotool","search","--onlyvisible","--name","Audio/MIDI Setup"],env=env,text=True,stderr=subprocess.DEVNULL).splitlines()
                if wins:
                    subprocess.run(["xdotool","key","--window",wins[0],"Return"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                    setup_accepted=True
            except Exception:
                pass
        try:
            init=mcp_post({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"gg-cloud-worker","version":"1"}}},2)
            if init.get("result",{}).get("serverInfo",{}).get("name")=="ardour-mcp-http": return proc,xv,log,xvlog,init
        except Exception: pass
        time.sleep(1)
    log.flush(); detail=(work/"ardour.log").read_text(errors="replace")[-12000:]
    try:
        wins=subprocess.check_output(["xwininfo","-root","-tree"],env=env,text=True,stderr=subprocess.STDOUT)[-12000:]
    except Exception as e:
        wins=str(e)
    for p in (proc,xv):
        if p.poll() is None: p.terminate()
    raise RuntimeError("Ardour native MCP did not become ready. setup_accepted=%s\nTail:\n%s\nWindows:\n%s"%(setup_accepted,detail,wins))

def stop_proc(p):
    if p and p.poll() is None:
        p.terminate()
        try:p.wait(10)
        except subprocess.TimeoutExpired:p.kill()

def ardour_batch(payload, job, job_id, token, work):
    home=work/"home"; home.mkdir(); seed_config(home)
    project=work/"project"; project.mkdir(); sf=restore_session(project,job,job_id,token,home); enable_mcp(sf)
    proc=xv=log=xvlog=None
    try:
        proc,xv,log,xvlog,init=start_ardour(sf,home,work)
        tools=mcp_post({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        responses=[]
        for i,call in enumerate(payload.get("calls",[]),start=10):
            name=call["name"]; args=call.get("arguments",{})
            res=mcp_post({"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":args}},30)
            responses.append({"name":name,"response":res})
            if "error" in res: raise RuntimeError(f"MCP call failed {name}: {res['error']}")
        save=mcp_post({"jsonrpc":"2.0","id":999,"method":"tools/call","params":{"name":"session_save","arguments":{}}},30)
        stop_proc(proc); proc=None
        archive=work/"session.tar.gz"
        with tarfile.open(archive,"w:gz") as t:
            for p in project.iterdir(): t.add(p,arcname=p.name)
        upload_artifact(job_id,"session.tar.gz",archive,token,"application/gzip")
        return {"engine":"ardour-native-mcp","initialize":init,"tool_count":len(tools.get("result",{}).get("tools",[])),"responses":responses,"save":save,"session_file":str(sf.relative_to(project))}
    finally:
        stop_proc(proc); stop_proc(xv)
        if log: log.close()
        if xvlog: xvlog.close()

def probe():
    def out(cmd):
        try:return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT).strip()
        except Exception as e:return str(e)
    ff=out(["ffmpeg","-version"]).splitlines()
    return {"ardour":out(["/usr/bin/ardour","--version"]),"ffmpeg":ff[0] if ff else None,
      "plugins":out(["bash","-lc","dpkg-query -W 2>/dev/null | grep -E '^(ardour|lsp-plugins|x42|dragonfly|surge|sfizz|avldrums|calf|fluid-soundfont)' || true"]),
      "mcp_library":out(["bash","-lc","find /usr/lib -name libardour_mcp_http.so -print -quit"]),
      "dummy_backend":out(["bash","-lc","find /usr/lib -name libdummy_audiobackend.so -print -quit"])}

def vocal_render(payload, job, job_id, token, work):
    bank=work/"voicebank"; bank.mkdir(); score=work/"score.ds"; names={a["name"] for a in job.get("assets",[])}
    score_name=payload.get("score_asset","score.ds")
    if score_name not in names: raise RuntimeError("score .ds asset missing")
    score.write_bytes(get_asset(job_id,score_name,token))
    bank_asset=payload.get("voicebank_asset"); bank_url=payload.get("voicebank_url")
    if bank_asset:
        data=get_asset(job_id,bank_asset,token); arc=work/bank_asset; arc.write_bytes(data)
    elif bank_url:
        data=urllib.request.urlopen(bank_url,timeout=180).read(); arc=work/(pathlib.Path(urllib.parse.urlparse(bank_url).path).name or "voicebank.zip"); arc.write_bytes(data)
    else: raise RuntimeError("voicebank asset or URL required")
    if zipfile.is_zipfile(arc):
        with zipfile.ZipFile(arc) as z:z.extractall(bank)
    elif tarfile.is_tarfile(arc):
        with tarfile.open(arc) as t:t.extractall(bank)
    else: raise RuntimeError("unsupported voicebank archive")
    candidates=list(bank.rglob("dsconfig.yaml"))
    if not candidates: raise RuntimeError("no dsconfig.yaml in voicebank")
    vb=candidates[0].parent
    cp=subprocess.run([sys.executable,"-m","pip","install","--break-system-packages","diffsinger-utau==0.3.8"],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if cp.returncode: raise RuntimeError("install diffsinger-utau failed:\n"+cp.stdout[-10000:])
    outdir=work/"vocal-out"; outdir.mkdir()
    cmd=["dsutau",str(score),"--voice-bank",str(vb),"--lang",str(payload.get("lang","ru")),"--output",str(outdir),
         "--pitch-steps",str(payload.get("pitch_steps",10)),"--variance-steps",str(payload.get("variance_steps",10)),"--acoustic-steps",str(payload.get("acoustic_steps",20))]
    if payload.get("speaker"): cmd += ["--speaker",str(payload["speaker"])]
    if payload.get("gender") is not None: cmd += ["--gender",str(payload["gender"])]
    cp=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if cp.returncode: raise RuntimeError("dsutau failed:\n"+cp.stdout[-10000:])
    wavs=list(outdir.rglob("*.wav"))
    if not wavs: raise RuntimeError("dsutau produced no wav")
    for i,w in enumerate(wavs): upload_artifact(job_id,f"vocal-{i+1}.wav",w,token,"audio/wav")
    return {"engine":"diffsinger-utau","version":"0.3.8","voicebank":vb.name,"wav_count":len(wavs),"log_tail":cp.stdout[-4000:]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--job-id",required=True); ap.add_argument("--oidc-token",required=True); a=ap.parse_args()
    work=pathlib.Path(tempfile.mkdtemp(prefix="gg-studio-"))
    try:
        job=claim(a.job_id,a.oidc_token); payload=json.loads(job.get("payload_json") or "{}"); op=job.get("operation")
        if op=="probe": result=probe()
        elif op=="ardour_batch": result=ardour_batch(payload,job,a.job_id,a.oidc_token,work)
        elif op=="vocal_render": result=vocal_render(payload,job,a.job_id,a.oidc_token,work)
        else: raise RuntimeError(f"unsupported operation: {op}")
        finish(a.job_id,a.oidc_token,True,result)
    except Exception as e:
        try: finish(a.job_id,a.oidc_token,False,{},str(e))
        finally: raise
    finally: shutil.rmtree(work,ignore_errors=True)
if __name__=="__main__": main()
