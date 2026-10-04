#!/usr/bin/env python3
import argparse, json, mimetypes, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request, urllib.error, urllib.parse, zipfile
from xml.etree import ElementTree as ET

RELAY="https://gg-cloud-music-studio.onrender.com"
VOICEBANK_CATALOG={
    "awata-weak-v3":{
        "kind":"zip",
        "url":"https://github.com/hhskt/Awata_Weak/releases/download/diffsinger_v3.0/Awata_Weak_DS_v3.zip",
        "lang":"ru",
        "gender":"female",
        "terms":"commercial voicebank use allowed by creator"
    },
    "keiro-revenant-v170":{
        "kind":"zip",
        "url":"https://github.com/lunaiproject/lunai_singers/releases/download/170/Keiro_Revenant_v170.zip",
        "lang":"ru",
        "gender":"male",
        "terms":"LUNAI Project terms: non-commercial fan use; commercial use requires permission; AI-music restrictions apply"
    }
}

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
    result=post_bytes(f"{RELAY}/runner/artifact/{job_id}/{urllib.parse.quote(name)}",data,ctype,auth_headers(token))
    evidence=os.environ.get("GG_EVIDENCE_DIR")
    if evidence:
        dst=pathlib.Path(evidence); dst.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst/name)
    return result

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
    memory_warning_accepted=False
    for _ in range(90):
        if proc.poll() is not None: break
        try:
            wins=subprocess.check_output(["xdotool","search","--onlyvisible","--class","Ardour"],env=env,text=True,stderr=subprocess.DEVNULL).splitlines()
            for wid in wins:
                geom=subprocess.check_output(["xdotool","getwindowgeometry","--shell",wid],env=env,text=True,stderr=subprocess.DEVNULL)
                vals=dict(line.split("=",1) for line in geom.splitlines() if "=" in line)
                if vals.get("WIDTH")=="444" and vals.get("HEIGHT")=="192":
                    subprocess.run(["xdotool","key","--window",wid,"Return"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                    memory_warning_accepted=True
        except Exception:
            pass
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
    raise RuntimeError("Ardour native MCP did not become ready. setup_accepted=%s memory_warning_accepted=%s\\nTail:\\n%s\\nWindows:\\n%s"%(setup_accepted,memory_warning_accepted,detail,wins))

def stop_proc(p):
    if p and p.poll() is None:
        p.terminate()
        try:p.wait(10)
        except subprocess.TimeoutExpired:p.kill()

def run_ardour_lua(sf, home, work, script_body):
    if not isinstance(script_body,str) or not script_body.strip():
        raise RuntimeError("non-empty Ardour Lua script required")
    if len(script_body.encode()) > 256*1024:
        raise RuntimeError("Ardour Lua script too large")
    lua_bin=shutil.which("ardour9-lua")
    if not lua_bin:
        raise RuntimeError("ardour9-lua not installed")
    wrapper=work/"gg_job.lua"
    wrapper.write_text("""local s = load_session(arg[1], arg[2])
assert(s, "GG: failed to load Ardour session")
local ok, err = pcall(function()
%s
end)
if not ok then error(err) end
Session:save_state("")
print("GG_ARDOUR_LUA=PASS")
""" % script_body)
    env=os.environ.copy()
    env.update({"HOME":str(home),"LANG":"C.UTF-8","USER":"root","LOGNAME":"root"})
    for k in ("ACTIONS_ID_TOKEN_REQUEST_TOKEN","ACTIONS_ID_TOKEN_REQUEST_URL","GITHUB_TOKEN"):
        env.pop(k,None)
    cp=subprocess.run([lua_bin,str(wrapper),str(sf.parent),sf.stem],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
    if cp.returncode != 0 or "GG_ARDOUR_LUA=PASS" not in cp.stdout:
        raise RuntimeError("ardour9-lua failed (rc=%s):\n%s"%(cp.returncode,cp.stdout[-16000:]))
    return {"engine":"ardour9-lua","returncode":cp.returncode,"stdout_tail":cp.stdout[-12000:]}

def ardour_lua(payload, job, job_id, token, work):
    home=work/"home"; home.mkdir(); seed_config(home)
    project=work/"project"; project.mkdir()
    sf=restore_session(project,job,job_id,token,home)
    result=run_ardour_lua(sf,home,work,payload.get("script",""))
    archive=work/"session.tar.gz"; archive_project(project,archive)
    upload_artifact(job_id,"session.tar.gz",archive,token,"application/gzip")
    result.update({"session_file":str(sf.relative_to(project)),"artifact":"session.tar.gz","artifact_bytes":archive.stat().st_size})
    return result

def apply_ardour_calls(sf, home, work, calls):
    proc=xv=log=xvlog=None
    try:
        proc,xv,log,xvlog,init=start_ardour(sf,home,work)
        tools=mcp_post({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        responses=[]
        for i,call in enumerate(calls or [],start=10):
            name=call["name"]; args=call.get("arguments",{})
            res=mcp_post({"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":args}},30)
            responses.append({"name":name,"response":res})
            if "error" in res:
                raise RuntimeError(f"MCP call failed {name}: {res['error']}")
        save=mcp_post({"jsonrpc":"2.0","id":999,"method":"tools/call","params":{"name":"session_save","arguments":{}}},30)
        stop_proc(proc); proc=None
        return {"engine":"ardour-native-mcp","initialize":init,"tool_count":len(tools.get("result",{}).get("tools",[])),"responses":responses,"save":save}
    finally:
        stop_proc(proc); stop_proc(xv)
        if log: log.close()
        if xvlog: xvlog.close()

def archive_project(project, archive):
    with tarfile.open(archive,"w:gz") as t:
        for p in project.iterdir():
            t.add(p,arcname=p.name)

def ardour_batch(payload, job, job_id, token, work):
    home=work/"home"; home.mkdir(); seed_config(home)
    project=work/"project"; project.mkdir()
    sf=restore_session(project,job,job_id,token,home); enable_mcp(sf)
    result=apply_ardour_calls(sf,home,work,payload.get("calls",[]))
    archive=work/"session.tar.gz"; archive_project(project,archive)
    upload_artifact(job_id,"session.tar.gz",archive,token,"application/gzip")
    result.update({"session_file":str(sf.relative_to(project)),"artifact":"session.tar.gz","artifact_bytes":archive.stat().st_size})
    return result

def project_render(payload, job, job_id, token, work):
    home=work/"home"; home.mkdir(); seed_config(home)
    project=work/"project"; project.mkdir()
    sf=restore_session(project,job,job_id,token,home)
    edit_result=None
    if payload.get("lua_script"):
        edit_result=run_ardour_lua(sf,home,work,payload.get("lua_script"))
    elif payload.get("calls"):
        enable_mcp(sf)
        edit_result=apply_ardour_calls(sf,home,work,payload.get("calls",[]))
    export_bin=shutil.which("ardour9-export") or shutil.which("ardour8-export") or shutil.which("ardour7-export")
    if not export_bin:
        raise RuntimeError("Ardour command-line export utility not installed")
    out=work/"master.wav"
    cmd=[export_bin,"-b",str(payload.get("bitdepth",24))]
    if payload.get("normalize"): cmd.append("-n")
    if payload.get("sample_rate"): cmd += ["-s",str(payload["sample_rate"])]
    cmd += ["-o",str(out),str(sf.parent),sf.stem]
    env=os.environ.copy(); env.update({"HOME":str(home),"LANG":"C.UTF-8"})
    cp=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("Ardour export produced no master (rc=%s):\n%s"%(cp.returncode,cp.stdout[-12000:]))
    upload_artifact(job_id,"master.wav",out,token,"audio/wav")
    mp3=work/"master.mp3"
    mp3cp=subprocess.run(["ffmpeg","-y","-v","error","-i",str(out),"-codec:a","libmp3lame","-b:a","320k",str(mp3)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if mp3cp.returncode==0 and mp3.exists() and mp3.stat().st_size>0:
        upload_artifact(job_id,"master.mp3",mp3,token,"audio/mpeg")
    else:
        mp3=None
    archive=work/"session.tar.gz"; archive_project(project,archive)
    upload_artifact(job_id,"session.tar.gz",archive,token,"application/gzip")
    ffprobe=shutil.which("ffprobe")
    duration=None
    if ffprobe:
        q=subprocess.run([ffprobe,"-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(out)],text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        if q.returncode==0:
            try: duration=float(q.stdout.strip())
            except Exception: pass
    return {"engine":"ardour-session-utils-export","export_rc":cp.returncode,"master_bytes":out.stat().st_size,"mp3_bytes":mp3.stat().st_size if mp3 else 0,"session_bytes":archive.stat().st_size,"duration_seconds":duration,"edit":edit_result,"artifacts":["master.wav"]+(["master.mp3"] if mp3 else [])+["session.tar.gz"],"log_tail":cp.stdout[-4000:]}

def probe():
    def out(cmd):
        try:return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT).strip()
        except Exception as e:return str(e)
    ff=out(["ffmpeg","-version"]).splitlines()
    return {
      "ardour":out(["/usr/bin/ardour","--version"]),
      "ffmpeg":ff[0] if ff else None,
      "plugins":out(["bash","-lc","dpkg-query -W 2>/dev/null | grep -E '^(ardour|lsp-plugins|x42|dragonfly|surge|sfizz|avldrums|calf|fluid-soundfont)' || true"]),
      "lv2_bundles":out(["bash","-lc","find /usr/lib /usr/local/lib -type d -name '*.lv2' 2>/dev/null | sort | head -200"]),
      "instrument_files":out(["bash","-lc","find /usr/share /usr/lib /usr/local/share -type f \\( -iname '*.sf2' -o -iname '*.sfz' \\) 2>/dev/null | sort | head -200"]),
      "mcp_library":out(["bash","-lc","find /usr/lib -name libardour_mcp_http.so -print -quit"]),
      "dummy_backend":out(["bash","-lc","find /usr/lib -name libdummy_audiobackend.so -print -quit"]),
      "new_session":out(["bash","-lc","command -v ardour9-new_session || true"]),
      "lua":out(["bash","-lc","command -v ardour9-lua || true"]),
      "export":out(["bash","-lc","command -v ardour9-export || true"]),
      "export_help":out(["bash","-lc","ardour9-export --help 2>&1 | head -120 || true"]),
      "megadl":out(["bash","-lc","command -v megadl || command -v megatools || true"])
    }

def install_vocal_stack():
    cmds=[
        [sys.executable,"-m","pip","install","--disable-pip-version-check","--quiet","torch==2.8.0","--index-url","https://download.pytorch.org/whl/cpu"],
        [sys.executable,"-m","pip","install","--disable-pip-version-check","--quiet","numpy==1.26.4","scipy==1.13.1","librosa==0.9.2","onnxruntime==1.16.3","pyyaml>=6","pypinyin>=0.50","soundfile","tqdm"],
        [sys.executable,"-m","pip","install","--disable-pip-version-check","--quiet","--no-deps","diffsinger-utau==0.3.8"],
    ]
    logs=[]
    for cmd in cmds:
        cp=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        logs.append(cp.stdout[-5000:])
        if cp.returncode:
            raise RuntimeError("vocal dependency install failed:\n"+cp.stdout[-12000:])
    ort_root=pathlib.Path(sys.executable).resolve().parent.parent/"lib"/f"python{sys.version_info.major}.{sys.version_info.minor}"/"site-packages"/"onnxruntime"/"capi"
    ort_sos=list(ort_root.glob("onnxruntime_pybind11_state*.so"))
    if not ort_sos:
        import site
        ort_sos=[]
        for sp in site.getsitepackages():
            ort_sos.extend(pathlib.Path(sp).glob("onnxruntime/capi/onnxruntime_pybind11_state*.so"))
    if not ort_sos:
        raise RuntimeError("onnxruntime shared object not found for execstack repair")
    for so in ort_sos:
        cp=subprocess.run(["patchelf","--clear-execstack",str(so)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if cp.returncode:
            raise RuntimeError("patchelf --clear-execstack failed for %s:\n%s"%(so,cp.stdout[-5000:]))
        logs.append("cleared-execstack:"+str(so))
    return "\n".join(logs)

def install_awata_ezv(vb, work):
    import yaml
    dst=vb/"dsvocoder"
    cfg_path=dst/"vocoder.yaml"
    if cfg_path.exists():
        return {"installed":False,"config":str(cfg_path)}
    url="https://github.com/matax2bi/ezv-for-diffsinger/releases/download/v2.0.0/ezv_for_diffsinger.oudep"
    arc=work/"ezv.oudep"
    arc.write_bytes(urllib.request.urlopen(url,timeout=300).read())
    dst.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(arc) as z:
        names={n.replace("\\\\","/"):n for n in z.namelist()}
        cfgs=[n for n in names if n.endswith("/vocoder.yaml") or n=="vocoder.yaml"]
        if not cfgs: raise RuntimeError("ezv package has no vocoder.yaml")
        cfg_name=cfgs[0]
        cfg_bytes=z.read(names[cfg_name])
        config=yaml.safe_load(cfg_bytes)
        model_ref=config.get("model")
        if not model_ref: raise RuntimeError("ezv vocoder config has no model")
        model_matches=[n for n in names if n.split("/")[-1]==model_ref]
        if not model_matches: raise RuntimeError("ezv package missing referenced model "+model_ref)
        (dst/"vocoder.yaml").write_bytes(cfg_bytes)
        with z.open(names[model_matches[0]]) as inf,(dst/model_ref).open("wb") as outf:
            shutil.copyfileobj(inf,outf,1024*1024)
    return {"installed":True,"config":str(cfg_path),"model":model_ref}

def render_awata_direct(score, vb, outdir, payload):
    import numpy as np
    from diffsinger_utau.voice_bank.commons.voice_bank_reader import VoiceBankReader
    from diffsinger_utau.voice_bank.commons.ds_reader import DSReader
    from diffsinger_utau.voice_bank.pred_acoustic import PredAcoustic
    from diffsinger_utau.voice_bank.pred_vocoder import PredVocoder
    from diffsinger_utau.voice_bank.commons.utils import resample_align_curve

    raw=json.loads(score.read_text())
    sections=raw if isinstance(raw,list) else [raw]
    if not sections: raise RuntimeError("empty DiffSinger score")
    ac=PredAcoustic(VoiceBankReader.DSAcoustic(vb/"dsconfig.yaml",preload_models=True))
    vc=PredVocoder(VoiceBankReader.DSVocoder(vb/"dsvocoder/vocoder.yaml",preload_models=True))
    lang=str(payload.get("lang") or "ru")
    speaker=payload.get("speaker")
    gender=float(payload.get("gender",0) or 0)
    steps=int(payload.get("acoustic_steps",12))
    waves=[]
    for idx,sec in enumerate(sections):
        ds=DSReader.DSSection(sec)
        mel=ac.predict(ds,lang=lang,speaker=speaker,steps=steps,gender=gender)
        f0s=sec.get("f0_seq")
        f0step=sec.get("f0_timestep")
        if not f0s or not f0step:
            raise RuntimeError(f"Awata direct render requires f0_seq/f0_timestep in section {idx}")
        f0=resample_align_curve(np.asarray([float(x) for x in str(f0s).split()],dtype=np.float32),float(f0step),vc.timestep,mel.shape[1])
        waves.append(vc.predict(mel,f0))
    wav=np.concatenate(waves) if len(waves)>1 else waves[0]
    target=outdir/"vocal-1.wav"
    vc.save_wav(wav,target)
    return [target]

def normalize_character_yaml(vb):
    p=pathlib.Path(vb)/"character.yaml"
    if not p.exists(): return False
    try:
        import yaml
        d=yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        changed=False
        for sb in d.get("subbanks",[]) or []:
            if "prefix" not in sb: sb["prefix"]=""; changed=True
            if "tone_ranges" not in sb: sb["tone_ranges"]=["C1-C7"]; changed=True
        if changed: p.write_text(yaml.safe_dump(d,allow_unicode=True,sort_keys=False),encoding="utf-8")
        return changed
    except Exception as e:
        print("GG_CHARACTER_NORMALIZE_WARNING="+str(e),flush=True)
        return False

def vocal_render(payload, job, job_id, token, work):
    bank=work/"voicebank"; bank.mkdir(); score=work/"score.ds"; names={a["name"] for a in job.get("assets",[])}
    inline=payload.get("score_inline")
    score_name=payload.get("score_asset","score.ds")
    if inline is not None:
        score.write_text(json.dumps(inline,ensure_ascii=False,indent=2))
    elif score_name in names:
        score.write_bytes(get_asset(job_id,score_name,token))
    else:
        raise RuntimeError("score_inline or score .ds asset required")

    voice_id=payload.get("voice_id")
    if voice_id=="keiro-ai-v100": voice_id="keiro-revenant-v170"
    spec=VOICEBANK_CATALOG.get(voice_id or "",{})
    bank_asset=payload.get("voicebank_asset")
    bank_url=payload.get("voicebank_url")
    mega_url=payload.get("voicebank_mega_url")
    if not bank_asset and not bank_url and not mega_url and spec:
        if spec.get("kind")=="mega": mega_url=spec.get("url")
        else: bank_url=spec.get("url")

    arc=None
    if bank_asset:
        data=get_asset(job_id,bank_asset,token); arc=work/bank_asset; arc.write_bytes(data)
    elif bank_url:
        data=urllib.request.urlopen(bank_url,timeout=300).read()
        arc=work/(pathlib.Path(urllib.parse.urlparse(bank_url).path).name or "voicebank.zip")
        arc.write_bytes(data)
    elif mega_url:
        if shutil.which("megadl"):
            cmd=["megadl","--no-progress","--path",str(bank),mega_url]
        elif shutil.which("megatools"):
            cmd=["megatools","dl","--no-progress","--path",str(bank),mega_url]
        else:
            raise RuntimeError("MEGA downloader not installed")
        cp=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        if cp.returncode:
            raise RuntimeError("MEGA voicebank download failed:\n"+cp.stdout[-10000:])
    else:
        raise RuntimeError("voicebank asset, URL, MEGA URL, or known voice_id required")

    if arc is not None:
        if zipfile.is_zipfile(arc):
            with zipfile.ZipFile(arc) as z:z.extractall(bank)
        elif tarfile.is_tarfile(arc):
            with tarfile.open(arc) as t:t.extractall(bank)
        else: raise RuntimeError("unsupported voicebank archive")

    candidates=list(bank.rglob("dsconfig.yaml"))
    if not candidates: raise RuntimeError("no dsconfig.yaml in voicebank")
    vb=candidates[0].parent
    normalized_character=normalize_character_yaml(vb.parent)
    install_log=install_vocal_stack()
    outdir=work/"vocal-out"; outdir.mkdir()
    lang=payload.get("lang") or spec.get("lang") or "ru"

    ezv=None
    if voice_id=="awata-weak-v3":
        ezv=install_awata_ezv(vb,work)
        wavs=render_awata_direct(score,vb,outdir,{**payload,"lang":lang})
        render_log="Awata direct acoustic+ezv render"
    else:
        cmd=["dsutau",str(score),"--voice-bank",str(vb),"--lang",str(lang),"--output",str(outdir),
             "--pitch-steps",str(payload.get("pitch_steps",10)),"--variance-steps",str(payload.get("variance_steps",10)),"--acoustic-steps",str(payload.get("acoustic_steps",20))]
        if payload.get("speaker"): cmd += ["--speaker",str(payload["speaker"])]
        if payload.get("gender") is not None: cmd += ["--gender",str(payload["gender"])]
        if payload.get("key_shift") is not None: cmd += ["--key-shift",str(payload["key_shift"])]
        cp=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1200)
        if cp.returncode: raise RuntimeError("dsutau failed:\n"+cp.stdout[-10000:])
        wavs=list(outdir.rglob("*.wav"))
        render_log=cp.stdout[-4000:]
    if not wavs: raise RuntimeError("vocal renderer produced no wav")
    for i,w in enumerate(wavs): upload_artifact(job_id,f"vocal-{i+1}.wav",w,token,"audio/wav")
    return {"engine":"diffsinger-utau","version":"0.3.8","character_normalized":normalized_character,"voice_id":voice_id,"voicebank":vb.name,"language":lang,"speaker":payload.get("speaker"),"gender":payload.get("gender"),"wav_count":len(wavs),"ezv":ezv,"dependency_log_tail":install_log[-2000:],"log_tail":render_log}

def gm_palette_render(payload, job, job_id, token, work):
    subprocess.run([sys.executable,"-m","pip","install","-q","mido"],check=True)
    import mido
    mid=mido.MidiFile(ticks_per_beat=480)
    programs=[("keys",0,60),("bass",32,40),("guitar",24,52),("orchestral",48,60),("ethnic",104,67),("electronic",80,64)]
    for name,program,note in programs:
        tr=mido.MidiTrack(); mid.tracks.append(tr)
        tr.append(mido.MetaMessage("track_name",name=name,time=0))
        tr.append(mido.Message("program_change",program=program,channel=0,time=0))
        tr.append(mido.Message("note_on",note=note,velocity=90,channel=0,time=0))
        tr.append(mido.Message("note_off",note=note,velocity=0,channel=0,time=480))
    dr=mido.MidiTrack(); mid.tracks.append(dr); dr.append(mido.MetaMessage("track_name",name="drums",time=0))
    for n in [36,38,42,46]:
        dr.append(mido.Message("note_on",note=n,velocity=100,channel=9,time=0))
        dr.append(mido.Message("note_off",note=n,velocity=0,channel=9,time=240))
    midi=work/"palette.mid"; mid.save(midi)
    sf=pathlib.Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")
    if not sf.exists(): raise RuntimeError("FluidR3 GM soundfont missing")
    out=work/"palette.wav"
    cp=subprocess.run(["fluidsynth","-ni","-F",str(out),"-r","44100",str(sf),str(midi)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    if cp.returncode or not out.exists() or out.stat().st_size==0: raise RuntimeError("FluidSynth palette render failed:\n"+cp.stdout[-8000:])
    upload_artifact(job_id,"palette.wav",out,token,"audio/wav")
    return {"engine":"fluidsynth","soundfont":sf.name,"categories":[x[0] for x in programs]+["drums"],"artifact":"palette.wav","artifact_bytes":out.stat().st_size,"log_tail":cp.stdout[-2000:]}

def song_render(payload, job, job_id, token, work):
    marker=payload.get("vocal_marker_path")
    if marker:
        root=pathlib.Path(os.environ.get("GITHUB_WORKSPACE",".")).resolve()
        mp=(root/marker).resolve()
        if root not in mp.parents: raise RuntimeError("vocal_marker_path outside workspace")
        vocal_payload=json.loads(mp.read_text())["bootstrap"]["payload"]
    else:
        vocal_payload=payload.get("vocal",{})
    vocal_result=vocal_render(vocal_payload,job,job_id,token,work)
    vocal_files=list((work/"vocal-out").rglob("*.wav"))
    if not vocal_files: raise RuntimeError("song render missing vocal wav")
    vocal=vocal_files[0]
    import soundfile as sf
    info=sf.info(str(vocal)); duration=float(info.duration)
    backing=work/"backing.wav"
    subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",f"sine=frequency=220:duration={duration}:sample_rate=44100","-filter:a","volume=0.10",str(backing)],check=True)
    master=work/"song-master.wav"
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(vocal),"-i",str(backing),"-filter_complex","[0:a]volume=0.9[v];[1:a]volume=0.45[b];[v][b]amix=inputs=2:duration=longest:normalize=0","-ar","44100",str(master)],check=True)
    mp3=work/"song-master.mp3"
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(master),"-codec:a","libmp3lame","-b:a","320k",str(mp3)],check=True)
    upload_artifact(job_id,"stems/vocal.wav",vocal,token,"audio/wav")
    upload_artifact(job_id,"stems/backing.wav",backing,token,"audio/wav")
    upload_artifact(job_id,"master.wav",master,token,"audio/wav")
    upload_artifact(job_id,"master.mp3",mp3,token,"audio/mpeg")
    return {"engine":"diffsinger+ffmpeg-stem-mix","vocal":vocal_result,"duration_seconds":duration,"artifacts":["stems/vocal.wav","stems/backing.wav","master.wav","master.mp3"],"master_bytes":master.stat().st_size,"mp3_bytes":mp3.stat().st_size}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--job-id",required=True); ap.add_argument("--oidc-token",required=True); a=ap.parse_args()
    work=pathlib.Path(tempfile.mkdtemp(prefix="gg-studio-"))
    try:
        job=claim(a.job_id,a.oidc_token); payload=json.loads(job.get("payload_json") or "{}"); op=job.get("operation")
        if op=="probe": result=probe()
        elif op=="ardour_batch": result=ardour_batch(payload,job,a.job_id,a.oidc_token,work)
        elif op=="ardour_lua": result=ardour_lua(payload,job,a.job_id,a.oidc_token,work)
        elif op=="project_render": result=project_render(payload,job,a.job_id,a.oidc_token,work)
        elif op=="vocal_render": result=vocal_render(payload,job,a.job_id,a.oidc_token,work)
        elif op=="song_render": result=song_render(payload,job,a.job_id,a.oidc_token,work)
        elif op=="gm_palette_render": result=gm_palette_render(payload,job,a.job_id,a.oidc_token,work)
        else: raise RuntimeError(f"unsupported operation: {op}")
        print("GG_WORKER_RESULT="+json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
        finish(a.job_id,a.oidc_token,True,result)
    except Exception as e:
        try: finish(a.job_id,a.oidc_token,False,{},str(e))
        finally: raise
    finally: shutil.rmtree(work,ignore_errors=True)
if __name__=="__main__": main()
