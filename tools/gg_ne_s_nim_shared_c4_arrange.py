#!/usr/bin/env python3
import json, pathlib, subprocess, sys, math
from mido import MidiFile, MidiTrack, Message, MetaMessage, bpm2tempo

SCORE_PATH=pathlib.Path(sys.argv[1])
ROOT=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "/tmp/gg-c4")
score=json.loads(SCORE_PATH.read_text())
BPM=score["bpm"]; TPB=score["ticks_per_beat"]; BAR=TPB*4; SR=48000; BARS=score["bars"]
DURATION=BARS*4*60/BPM+4.0
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

def add(ev,tick,note,dur,vel=90,ch=0):
    ev += [
      (int(tick),0,Message("note_on",note=int(note),velocity=max(1,min(127,int(vel))),channel=ch,time=0)),
      (int(tick+max(1,dur)),1,Message("note_off",note=int(note),velocity=0,channel=ch,time=0))
    ]

def save(name,program,events,channel=0):
    mid=MidiFile(ticks_per_beat=TPB)
    meta=MidiTrack(); mid.tracks.append(meta)
    meta.append(MetaMessage("track_name",name=name,time=0))
    meta.append(MetaMessage("set_tempo",tempo=bpm2tempo(BPM),time=0))
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
    slot=3*BAR if ph["section"]=="verse" else 2*BAR
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

# Drums: coherent groove, accents derived from the exact vocal stress map.
ev=[]
for b in range(BARS):
    st=b*BAR
    vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    chorus=16<=b<28
    for i in range(8):
        t=st+i*(TPB//2)
        v=40+(9 if i in (0,3,6) else 0)+(4 if chorus else 0)
        add(ev,t,42,70,v,9)
    for beat in [0,2]:
        add(ev,st+beat*TPB,36,120,72+(8 if chorus else 0),9)
    for beat in [1,3]:
        add(ev,st+beat*TPB,38,120,74+(10 if chorus else 0),9)
    # fast bright answer, but never a constant fill under words
    if not vocal_bar or b in response_bars:
        for j,n in enumerate([45,47,48,47]):
            add(ev,st+2*TPB+j*(TPB//2),n,115,62+5*j,9)
# exact lyric-stress support and subtle frame-drum/tambourine signal
for t in stress_ticks:
    add(ev,t,54,80,48,9)
    if (t//BAR)%3==2 or 16<=t//BAR<24: add(ev,t,45,110,42,9)
stems["drums"]=save("drums",None,ev,9)

# Bass: chord roots/fifths plus small rhythmic emphasis near stressed lyric anchors.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; r=roots[ch]; vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    patt=[(0,r,700),(2*TPB,r+7,650)] if vocal_bar else [(0,r,420),(TPB,r+7,360),(2*TPB,r+12,360),(3*TPB,r+7,300)]
    for off,n,d in patt:add(ev,st+off,n,d,62 if vocal_bar else 72)
for t in stress_ticks:
    b=min(BARS-1,t//BAR); r=roots[chords[b]]
    add(ev,t,r+12,150,68)
stems["bass"]=save("bass",33,ev)

# Guitar left: harmonic body. Long voicings under voice, rhythmic rock answers in gaps.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; ns=voiced_chord(ch,b); vocal_bar=any(a < st+BAR and z > st for a,z in active_intervals)
    if vocal_bar:
        for off in (0,960):
            for j,n in enumerate(ns):
                add(ev,st+off,n,760,38+(10 if j==len(ns)-1 else 0))
    else:
        for off in (0,720,1440):
            for n in ns:add(ev,st+off,n,380,58)
stems["guitar_left"]=save("guitar_left",30,ev)

# Guitar right: sparse arpeggio locked to chord and 3+3+2 pulse.
ev=[]
for b,ch in enumerate(chords):
    st=b*BAR; ns=voiced_chord(ch,b)
    seq=[0,min(1,len(ns)-1),min(2,len(ns)-1),min(1,len(ns)-1),0,min(2,len(ns)-1)]
    offs=[0,360,720,1080,1440,1680]
    for i,(off,idx) in enumerate(zip(offs,seq)):
        if in_vocal(st+off) and i in (2,4): continue
        note=ns[idx]
        add(ev,st+off,note,230,38 if in_vocal(st+off) else 50)
stems["guitar_right"]=save("guitar_right",27,ev)

# Acoustic: human dark-folk layer, almost absent in chorus.
ev=[]
for b,ch in enumerate(chords):
    if 16<=b<28: continue
    st=b*BAR; ns=chord_tones[ch][:3]
    for i,idx in enumerate([0,2,1,2]):
        add(ev,st+i*TPB,ns[idx],380,32 if in_vocal(st+i*TPB) else 44)
stems["acoustic"]=save("acoustic",25,ev)

# Organ and strings: chorus lift only.
ev=[]
for b in range(16,28):
    st=b*BAR
    for j,n in enumerate(voiced_chord(chords[b],b)):add(ev,st,n,1800,30+(8 if j==2 else 0))
stems["organ"]=save("organ",18,ev)
ev=[]
for b in range(16,28):
    st=b*BAR
    for n in voiced_chord(chords[b],b)[1:]:add(ev,st,n+12,1820,27)
stems["strings"]=save("strings",48,ev)

# Lead guitar: echoes the last vocal motif after every phrase. This is direct melodic inheritance.
ev=[]
for pi,ph in enumerate(phrases):
    if pi % 2 == 0:
        continue
    response_start=max(ph["end"]+120,ph["slot_end"]-900)
    response_end=ph["slot_end"]-60
    if response_end<=response_start: continue
    src=ph["all_pitches"][-4:]
    if not src: continue
    # keep within guitar register and preserve intervals
    notes=[]
    for n in src:
        while n<60:n+=12
        while n>76:n-=12
        notes.append(n)
    step=max(150,(response_end-response_start)//len(notes))
    for i,n in enumerate(notes):
        add(ev,response_start+i*step,n,min(step-30,300),60+4*i)
stems["lead_guitar"]=save("lead_guitar",29,ev)

# Piano: intro and closing answer only.
ev=[]
for b in list(range(0,4))+list(range(28,32)):
    st=b*BAR; ns=chord_tones[chords[b]]
    for off,idx in [(0,0),(TPB,1),(2*TPB,min(2,len(ns)-1)),(3*TPB,1)]:
        add(ev,st+off,ns[idx]+12,360,36)
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
combined.save(ROOT/"NE_S_NIM_C4_arrangement.mid")

filters={
"drums":"highpass=f=35,acompressor=threshold=-18dB:ratio=3.0:attack=5:release=90,equalizer=f=80:t=q:w=1:g=2,equalizer=f=5200:t=q:w=1:g=2,volume=0.88",
"bass":"highpass=f=28,lowpass=f=4200,acompressor=threshold=-20dB:ratio=3.4:attack=10:release=120,volume=0.78",
"guitar_left":"highpass=f=90,lowpass=f=9500,equalizer=f=1800:t=q:w=1.2:g=-4,equalizer=f=2800:t=q:w=1.0:g=-3,volume=0.48",
"guitar_right":"highpass=f=110,lowpass=f=10500,equalizer=f=1700:t=q:w=1.2:g=-4,aecho=0.9:0.75:75:0.05,volume=0.42",
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
                f"amix=inputs={n}:duration=longest:normalize=0,acompressor=threshold=-12dB:ratio=2.0:attack=12:release=160,alimiter=limit=0.90[out]",
                "-map","[out]","-ar",str(SR),"-c:a","pcm_s24le",str(ROOT/"instrumental.wav")],check=True)
subprocess.run(["ffmpeg","-y","-v","error","-i",str(ROOT/"instrumental.wav"),
                "-codec:a","libmp3lame","-b:a","320k",str(ROOT/"instrumental.mp3")],check=True)

diag={"duration_target":DURATION,"stress_ticks":stress_ticks,
      "active_intervals":active_intervals,
      "phrases":[{"id":p["id"],"start":p["bar"]*BAR+p["offset"],"end":p["end"],"slot_end":p["slot_end"]} for p in phrases],
      "stems":list(stems)}
(ROOT/"composition-map.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2))
print(json.dumps(diag,ensure_ascii=False))
