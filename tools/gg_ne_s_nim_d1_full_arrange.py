#!/usr/bin/env python3
import json, pathlib, subprocess, sys, math
from mido import MidiFile, MidiTrack, Message, MetaMessage, bpm2tempo

SCORE_PATH=pathlib.Path(sys.argv[1])
ROOT=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "/tmp/gg-d1-full")
score=json.loads(SCORE_PATH.read_text())
BPM=score["bpm"]; TPB=score["ticks_per_beat"]; BAR=TPB*4; SR=48000; BARS=score["bars"]
TEMPO_MAP=sorted(score.get("tempo_map") or [{"bar":0,"bpm":BPM}], key=lambda x:int(x["bar"]))
if int(TEMPO_MAP[0]["bar"]) != 0:
    TEMPO_MAP.insert(0,{"bar":0,"bpm":BPM})
def bpm_for_bar(bar):
    cur=float(TEMPO_MAP[0]["bpm"])
    for p in TEMPO_MAP:
        if int(p["bar"])<=bar: cur=float(p["bpm"])
        else: break
    return cur
DURATION=sum(4*60.0/bpm_for_bar(b) for b in range(BARS))+4.0
ROOT.mkdir(parents=True,exist_ok=True)
SF=pathlib.Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")

chord_tones={
 "Am":[57,60,64],"Am7":[57,60,64,67],"Fmaj7":[53,57,60,64],"C/E":[52,55,60,64],"E7":[52,56,59,62],
 "C":[48,52,55,60],"G/B":[47,50,55,59],"Dm":[50,53,57,62],"Dm7":[50,53,57,60],"Am/C":[48,52,57,60],
 "F":[53,57,60],"G":[55,59,62],"Esus4":[52,57,59,62]
}
roots={"Am":33,"Am7":33,"Fmaj7":29,"C/E":28,"E7":28,"C":36,"G/B":35,"Dm":38,"Dm7":38,"Am/C":36,"F":29,"G":31,"Esus4":28}
chords=score["chords"]
assert len(chords)==BARS

form=score.get("form",{})
def section_range(name):
    a,b=form[name]
    return range(int(a),int(b)+1)
def in_section(bar,name):
    a,b=form[name]
    return int(a) <= bar <= int(b)
def in_any_section(bar,names):
    return any(in_section(bar,n) for n in names)

CHORUS_BARS=set(section_range("chorus_I")) | set(section_range("chorus_II"))
BRIDGE_BARS=set(section_range("bridge"))
DEV_BARS=set(section_range("instrumental_development"))
FINAL_BARS=set(section_range("final"))
CODA_BARS=set(section_range("coda"))
OUTRO_BARS=set(section_range("outro"))
INTRO_BARS=set(section_range("intro"))

def add(ev,tick,note,dur,vel=90,ch=0):
    ev += [
      (int(tick),0,Message("note_on",note=int(note),velocity=max(1,min(127,int(vel))),channel=ch,time=0)),
      (int(tick+max(1,dur)),1,Message("note_off",note=int(note),velocity=0,channel=ch,time=0))
    ]

def save(name,program,events,channel=0):
    mid=MidiFile(ticks_per_beat=TPB)
    meta=MidiTrack(); mid.tracks.append(meta)
    meta.append(MetaMessage("track_name",name=name,time=0))
    last_tempo_tick=0
    for idx,p in enumerate(TEMPO_MAP):
        tick=int(p["bar"])*BAR
        meta.append(MetaMessage("set_tempo",tempo=bpm2tempo(float(p["bpm"])),time=tick-last_tempo_tick))
        last_tempo_tick=tick
    meta.append(MetaMessage("time_signature",numerator=4,denominator=4,time=0))
    tr=MidiTrack(); mid.tracks.append(tr)
    if program is not None: tr.append(Message("program_change",program=program,channel=channel,time=0))
    last=0
    for tick,pri,msg in sorted(events,key=lambda x:(x[0],x[1])):
        msg.time=max(0,tick-last); tr.append(msg); last=tick
    path=ROOT/(name+".mid"); mid.save(path); return path

def phrase_timeline(ph):
    p=ph["bar"]*BAR+ph["offset"]; out=[]; stress_ticks=[]
    all_pitches=[]
    for w in ph["words"]:
        for i,(pitch,dur) in enumerate(zip(w["pitches"],w["durations"])):
            out.append((p,pitch,dur,w["text"],i,w["stress"]))
            all_pitches.append(pitch)
            if i==w["stress"]: stress_ticks.append(p)
            p+=dur
        p+=w["rest"]
    return out,stress_ticks,p,all_pitches

phrases=[]
for ph in score["phrases"]:
    tl,acc,end,pitches=phrase_timeline(ph)
    slot=3*BAR
    phrases.append({**ph,"timeline":tl,"stress_ticks":acc,"end":end,
                    "slot_end":ph["bar"]*BAR+slot,"all_pitches":pitches})
active_intervals=[(ph["bar"]*BAR+ph["offset"],ph["end"]) for ph in phrases]
stress_ticks=sorted(t for ph in phrases for t in ph["stress_ticks"])

# C3: derive response bars and dominant vocal pitch class per bar from the same score.
response_bars={max(0, int(ph["slot_end"]//BAR)-1) for ph in phrases}
bar_vocal_targets={}
for ph in phrases:
    for tick,pitch,dur,word,si,stress in ph["timeline"]:
        b=min(BARS-1,max(0,int((tick+dur/2)//BAR)))
        weight=dur*(1.8 if si==stress else 1.0)
        bar_vocal_targets.setdefault(b,[]).append((weight,pitch))
for b,items in list(bar_vocal_targets.items()):
    by_pc={}
    for weight,pitch in items:
        pc=pitch%12
        by_pc[pc]=by_pc.get(pc,0)+weight
    target_pc=max(by_pc,key=by_pc.get)
    # choose the actual sung note nearest low-mid guitar register
    candidates=[p for _,p in items if p%12==target_pc]
    bar_vocal_targets[b]=min(candidates,key=lambda p:abs(p-64))

def voiced_chord(chord,b):
    ns=list(chord_tones[chord])
    target=bar_vocal_targets.get(b)
    if target is None:
        return ns[:3]
    pc=target%12
    low=[n for n in ns if n%12!=pc]
    # retain two harmonic supports plus the vocal pitch class as the top voice
    low=sorted(low)[:2]
    n=target-12
    while n<48:n+=12
    while n>60:n-=12
    return sorted(low+[n])

def in_vocal(t):
    return any(a<=t<=b for a,b in active_intervals)
def near_stress(t,window=90):
    return any(abs(t-s)<=window for s in stress_ticks)

stems={}

# Drums: GG D1R5 — section-specific groove, explicit accents and breathing space.
ev=[]
for b in range(BARS):
    st=b*BAR
    vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    chorus=b in CHORUS_BARS
    bridge=b in BRIDGE_BARS
    final=b in FINAL_BARS
    coda=b in CODA_BARS
    intro=b in INTRO_BARS
    transition=in_section(b,"transition")
    # Hats carry different identities instead of one metronomic grid.
    if intro or coda:
        hat_steps=(0,4)
        hat_base=34
    elif bridge:
        hat_steps=(0,3,6)
        hat_base=38
    elif chorus or final:
        hat_steps=tuple(range(8))
        hat_base=43
    elif b in DEV_BARS:
        hat_steps=tuple(range(8))
        hat_base=46
    else:
        hat_steps=(0,2,3,6)
        hat_base=39
    for i in hat_steps:
        t=st+i*(TPB//2)
        accent=10 if i in (0,3,6) else 0
        add(ev,t,42,70,hat_base+accent,9)
    # Kick/snare pattern changes by section.
    kicks=(0,2) if not (chorus or final) else (0,1.5,2,3.5)
    if bridge: kicks=(0,2.5)
    if coda: kicks=(0,)
    for beat in kicks:
        add(ev,st+int(beat*TPB),36,120,72+(10 if chorus or final else 0),9)
    snares=(1,3)
    if bridge: snares=(2,)
    if coda: snares=(2,)
    for beat in snares:
        add(ev,st+int(beat*TPB),38,120,74+(12 if chorus or final else 0),9)
    # Clear transition/final accents and tom punctuation.
    if b in {27,39,43,55,67,79,95,107,113,119}:
        add(ev,st+3*TPB,49,180,86,9)
        add(ev,st+3*TPB+TPB//2,50,150,92,9)
    if transition and b%2==1:
        add(ev,st+3*TPB,45,180,68,9)
    # Phrase answers only after the vocal tail.
    if not vocal_bar or b in response_bars:
        overlaps=[z for a,z in active_intervals if a < st+BAR and z > st]
        vocal_end=max(overlaps) if overlaps else st
        fill_start=max(st+2*TPB, vocal_end+120)
        fill_end=st+BAR-120
        available=fill_end-fill_start
        if available >= 360:
            notes=[45,47,48,50]
            step=max(90,available//len(notes))
            for j,n in enumerate(notes):
                add(ev,fill_start+j*step,n,min(125,step-20),60+7*j,9)
    if b in DEV_BARS:
        phase=(b-min(DEV_BARS))%4
        toms=[45,47,48,50] if phase<2 else [50,48,47,45]
        for j,n in enumerate(toms):
            add(ev,st+j*(TPB//2),n,150,72+4*j,9)
        for off in (0,3*(TPB//2),6*(TPB//2)):
            add(ev,st+off,36,120,84,9)
for t in stress_ticks:
    add(ev,t,54,80,54,9)
    if (t//BAR)%3==2 or (t//BAR) in CHORUS_BARS or (t//BAR) in FINAL_BARS:
        add(ev,t,45,110,48,9)
stems["drums"]=save("drums",None,ev,9)

# Bass:# Bass: chord roots/fifths plus small rhythmic emphasis near stressed lyric anchors.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; r=roots[ch]; vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    if vocal_bar:
        patt=[(0,r,700),(2*TPB,r+7,650)]
        vel=62
    elif b in DEV_BARS:
        patt=[(0,r,320),(TPB//2,r+7,280),(TPB,r+12,320),(3*TPB//2,r+7,280),
              (2*TPB,r,320),(5*TPB//2,r+7,280),(3*TPB,r+12,320),(7*TPB//2,r+7,260)]
        vel=76
    else:
        patt=[(0,r,420),(TPB,r+7,360),(2*TPB,r+12,360),(3*TPB,r+7,300)]
        vel=72
    for off,n,d in patt:add(ev,st+off,n,d,vel)
for t in stress_ticks:
    b=min(BARS-1,t//BAR); r=roots[chords[b]]
    add(ev,t,r+12,150,68)
stems["bass"]=save("bass",33,ev)

# Dedicated low-mid GG riff: remains audible under voice without occupying the vocal formant band.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; r=roots[ch]+12
    vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    if b in CHORUS_BARS or b in FINAL_BARS:
        offs=(0,360,720,1080,1440,1680); ints=(0,7,12,7,3,7); vel=67
    elif b in BRIDGE_BARS:
        offs=(0,960,1440); ints=(0,7,3); vel=55
    elif b in DEV_BARS:
        offs=tuple(i*(TPB//2) for i in range(8)); ints=(0,7,12,7,3,7,12,7); vel=72
    elif b in CODA_BARS or b in OUTRO_BARS:
        offs=(0,960); ints=(0,7); vel=42
    else:
        offs=(0,720,1440); ints=(0,7,3); vel=58
    for i,off in enumerate(offs):
        # At vocal entrance leave a small pocket, then let the riff answer inside the bar.
        if vocal_bar and off < 240: continue
        n=r+ints[i%len(ints)]
        while n>62: n-=12
        add(ev,st+off,n,230 if b not in BRIDGE_BARS else 430,vel)
stems["riff"]=save("riff",29,ev)

# Guitar left: harmonic body. Long voicings under voice, rhythmic rock answers in gaps.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; ns=voiced_chord(ch,b); vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    if vocal_bar:
        base_vel=42 if b not in CHORUS_BARS else 48
        for off in (0,960):
            for j,n in enumerate(ns):
                add(ev,st+off,n,760,base_vel+(8 if j==len(ns)-1 else 0))
    elif b in DEV_BARS:
        for off in (0,480,960,1440):
            for n in ns:add(ev,st+off,n,300,62)
    else:
        for off in (0,720,1440):
            for n in ns:add(ev,st+off,n,380,56)
stems["guitar_left"]=save("guitar_left",30,ev)

# Guitar right: sparse arpeggio locked to chord and 3+3+2 pulse.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; ns=voiced_chord(ch,b)
    seq=[0,min(1,len(ns)-1),min(2,len(ns)-1),min(1,len(ns)-1),0,min(2,len(ns)-1)]
    offs=[0,360,720,1080,1440,1680]
    for i,(off,idx) in enumerate(zip(offs,seq)):
        if in_vocal(st+off) and i in (4,): continue
        note=ns[idx]
        vel=44 if in_vocal(st+off) else (58 if b in DEV_BARS else 50)
        add(ev,st+off,note,230,vel)
stems["guitar_right"]=save("guitar_right",27,ev)

# Acoustic: human dark-folk layer, almost absent in chorus.
ev=[]
for b,ch in enumerate(chords):
    if b in CHORUS_BARS or b in DEV_BARS: continue
    st=b*BAR; ns=chord_tones[ch][:3]
    for i,idx in enumerate([0,2,1,2]):
        add(ev,st+i*TPB,ns[idx],380,30 if in_vocal(st+i*TPB) else (36 if b in FINAL_BARS or b in CODA_BARS else 42))
stems["acoustic"]=save("acoustic",25,ev)

# Organ and strings: Shadow role. Lift choruses/bridge/final, then withdraw in coda.
ev=[]
for b in sorted(CHORUS_BARS | BRIDGE_BARS | FINAL_BARS):
    st=b*BAR
    vel=32 if b in CHORUS_BARS else 27 if b in BRIDGE_BARS else 29
    for j,n in enumerate(voiced_chord(chords[b],b)):
        add(ev,st,n,1800,vel+(6 if j==2 else 0))
stems["organ"]=save("organ",18,ev)

ev=[]
for b in sorted(CHORUS_BARS | BRIDGE_BARS | FINAL_BARS):
    st=b*BAR
    vel=25 if b in CHORUS_BARS else 22 if b in BRIDGE_BARS else 24
    for n in voiced_chord(chords[b],b)[1:]:
        add(ev,st,n+12,1820,vel)
stems["strings"]=save("strings",48,ev)

# Lead guitar: echoes the last vocal motif after every phrase. This is direct melodic inheritance.
ev=[]
section_counts={}
for ph in phrases:
    sec=ph["section"]
    idx=section_counts.get(sec,0)
    section_counts[sec]=idx+1
    # Avoid constant call-and-response density outside the chorus.
    if sec in ("verse","bridge","final") and idx%2==0:
        continue
    response_start=max(ph["end"]+120,ph["slot_end"]-900)
    response_end=ph["slot_end"]-60
    if response_end<=response_start: continue
    src=ph["all_pitches"][-4:]
    if not src: continue
    notes=[]
    for n in src:
        while n<60:n+=12
        while n>76:n-=12
        notes.append(n)
    step=max(150,(response_end-response_start)//len(notes))
    for i,n in enumerate(notes):
        add(ev,response_start+i*step,n,min(step-30,300),56+4*i)
stems["lead_guitar"]=save("lead_guitar",29,ev)

# Piano: intro and closing answer only.
ev=[]
for b in sorted(INTRO_BARS | CODA_BARS | OUTRO_BARS):
    st=b*BAR; ns=chord_tones[chords[b]]
    for off,idx in [(0,0),(TPB,1),(2*TPB,min(2,len(ns)-1)),(3*TPB,1)]:
        add(ev,st+off,ns[idx]+12,360,34 if b in INTRO_BARS else 28)
stems["piano"]=save("piano",0,ev)

# editable combined MIDI
combined=MidiFile(ticks_per_beat=TPB)
meta=MidiTrack();combined.tracks.append(meta)
meta.append(MetaMessage("set_tempo",tempo=bpm2tempo(BPM),time=0))
meta.append(MetaMessage("time_signature",numerator=4,denominator=4,time=0))
for name,path in stems.items():
    src=MidiFile(path); tr=MidiTrack(); tr.append(MetaMessage("track_name",name=name,time=0))
    for msg in src.tracks[-1]: tr.append(msg.copy())
    combined.tracks.append(tr)
combined.save(ROOT/"NE_S_NIM_D1_FULL_arrangement.mid")

filters={
"drums":"highpass=f=35,acompressor=threshold=-18dB:ratio=3.0:attack=5:release=90,equalizer=f=80:t=q:w=1:g=2,equalizer=f=5200:t=q:w=1:g=2,volume=0.88",
"bass":"highpass=f=28,lowpass=f=4200,acompressor=threshold=-20dB:ratio=3.4:attack=10:release=120,volume=0.78",
"riff":"highpass=f=85,lowpass=f=6200,equalizer=f=1900:t=q:w=1.0:g=-5,equalizer=f=3200:t=q:w=1.2:g=-2,acompressor=threshold=-20dB:ratio=1.5:attack=8:release=90,volume=0.78",
"guitar_left":"highpass=f=90,lowpass=f=9500,equalizer=f=1900:t=q:w=1.2:g=-3,equalizer=f=3000:t=q:w=1.0:g=-2,volume=0.56",
"guitar_right":"highpass=f=110,lowpass=f=10500,equalizer=f=1900:t=q:w=1.2:g=-3,aecho=0.9:0.75:75:0.05,volume=0.50",
"acoustic":"highpass=f=110,lowpass=f=11000,equalizer=f=2200:t=q:w=1:g=-3,volume=0.32",
"organ":"highpass=f=120,lowpass=f=7600,equalizer=f=1800:t=q:w=1:g=-5,volume=0.25",
"strings":"highpass=f=160,lowpass=f=9000,equalizer=f=2300:t=q:w=1:g=-4,volume=0.23",
"lead_guitar":"highpass=f=130,lowpass=f=10000,equalizer=f=1800:t=q:w=1:g=-3,aecho=0.88:0.72:105:0.08,volume=0.50",
"piano":"highpass=f=120,lowpass=f=10500,equalizer=f=2000:t=q:w=1:g=-3,volume=0.28"}

proc=ROOT/"processed";proc.mkdir(exist_ok=True)
for name,midipath in stems.items():
    raw=ROOT/(name+"_raw.wav"); out=proc/(name+".wav")
    subprocess.run(["fluidsynth","-ni","-F",str(raw),"-r",str(SR),str(SF),str(midipath)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(raw),"-af",
                    filters[name]+f",atrim=duration={DURATION:.3f},apad=pad_dur=1",
                    "-ar",str(SR),str(out)],check=True)
    raw.unlink(missing_ok=True)

# Master instrumental at a conservative level; vocal space is intentional.
inputs=[]
for p in sorted(proc.glob("*.wav")): inputs += ["-i",str(p)]
n=len(list(proc.glob("*.wav")))
subprocess.run(["ffmpeg","-y","-v","error",*inputs,"-filter_complex",
                f"amix=inputs={n}:duration=longest:normalize=0,acompressor=threshold=-9dB:ratio=1.35:attack=18:release=180,alimiter=limit=0.92[out]",
                "-map","[out]","-ar",str(SR),"-c:a","pcm_s24le",str(ROOT/"instrumental.wav")],check=True)
subprocess.run(["ffmpeg","-y","-v","error","-i",str(ROOT/"instrumental.wav"),
                "-codec:a","libmp3lame","-b:a","320k",str(ROOT/"instrumental.mp3")],check=True)

diag={"duration_target":DURATION,"tempo_map":TEMPO_MAP,"stress_ticks":stress_ticks,
      "active_intervals":active_intervals,
      "phrases":[{"id":p["id"],"start":p["bar"]*BAR+p["offset"],"end":p["end"],"slot_end":p["slot_end"]} for p in phrases],
      "stems":list(stems)}
(ROOT/"composition-map.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2))
print(json.dumps(diag,ensure_ascii=False))