#!/usr/bin/env python3
import json, pathlib, subprocess, sys
from mido import MidiFile, MidiTrack, Message, MetaMessage, bpm2tempo

BPM=108; TPB=480; BAR=1920; SR=48000; TOTAL_BARS=110
SONG_SECONDS=TOTAL_BARS*4*60/BPM + 4.0
ROOT=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "/tmp/gg-rebuild-a")
ROOT.mkdir(parents=True,exist_ok=True)
SF=pathlib.Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")

intro=["Am","Am","F","F","C","G","Am","E"]
verse1=[
"Am","F","C","G","Am","E","Am","F","C","Dm","E","Am",
"Am","F","C","G","Dm","E","F","C","G","Dm","E","E"]
chorus=["F","C","G","Am","F","C","E","E"]
interlude=["Am","G","F","E"]
verse2=["Am","F","C","G","Dm","E","Am","F","C","Dm","E","Am"]
bridge=["Dm","Am","F","E","Dm","F","G","E","Am","F","Dm","E"]
instrumental=["Am","F","C","G","Am","F","Dm","E","Am","G","F","E"]
final=["Am","F","C","G","Dm","Am","F","C","G","Dm","E","Am"]
coda=["Am","F","E","Am","E","Am"]
outro=["Am","F","E","Am"]
chords=intro+verse1+chorus+interlude+verse2+chorus+bridge+instrumental+final+coda+outro
assert len(chords)==TOTAL_BARS,len(chords)

roots={"Am":33,"F":29,"C":36,"G":31,"Dm":38,"E":28}
triads={"Am":[57,60,64],"F":[53,57,60],"C":[60,64,67],"G":[55,59,62],"Dm":[50,53,57],"E":[52,56,59]}
guitar={"Am":[45,52,57],"F":[41,48,53],"C":[48,55,60],"G":[43,50,55],"Dm":[38,45,50],"E":[40,47,52]}
scale=[57,59,60,62,64,65,67,69,71,72,74,76]

def section(b):
    if b<8:return "intro"
    if b<32:return "verse1"
    if b<40:return "chorus1"
    if b<44:return "interlude"
    if b<56:return "verse2"
    if b<64:return "chorus2"
    if b<76:return "bridge"
    if b<88:return "instrumental"
    if b<100:return "final"
    if b<106:return "coda"
    return "outro"

def is_response_bar(b):
    s=section(b)
    if s=="verse1": return (b-8)%3==2
    if s=="verse2": return (b-44)%3==2
    if s=="bridge": return (b-64)%3==2
    if s=="final": return (b-88)%3==2
    if s=="coda": return (b-100)%3==2
    return False

def intensity(b):
    return {
        "intro":.34,"verse1":.53,"chorus1":.90,"interlude":.62,
        "verse2":.62,"chorus2":.96,"bridge":.76,"instrumental":1.0,
        "final":1.0,"coda":.38,"outro":.22}[section(b)]

def add(ev,tick,note,dur,vel=90,ch=0):
    ev += [
      (tick,0,Message("note_on",note=int(note),velocity=max(1,min(127,int(vel))),channel=ch,time=0)),
      (tick+max(1,int(dur)),1,Message("note_off",note=int(note),velocity=0,channel=ch,time=0))
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
        msg.time=max(0,int(tick-last)); tr.append(msg); last=tick
    path=ROOT/(name+".mid"); mid.save(path); return path

stems={}

# DRUMS — restrained under lyrics, explicit third-bar answers.
ev=[]
section_starts={0,8,32,40,44,56,64,76,88,100,106}
for b in range(TOTAL_BARS):
    st=b*BAR; it=intensity(b); resp=is_response_bar(b); s=section(b)
    # 8th-note hats with 3+3+2 emphasis
    for i in range(8):
        vel=30+int(28*it)+(10 if i in (0,3,6) else 0)
        if s=="coda": vel-=8
        add(ev,st+i*240,42,70,vel,9)
    # core groove
    for i in ([0,4] if not resp else [0,3,6]):
        add(ev,st+i*240,36,115,52+int(38*it),9)
    for i in ([2,6] if not resp else [2]):
        add(ev,st+i*240,38,110,50+int(42*it),9)
    if b in section_starts and b>0: add(ev,st,49,190,58+int(38*it),9)
    if resp:
        # conversational fill across last half of response bar
        for j,n in enumerate([45,47,48,47,43,41]):
            add(ev,st+720+j*180,n,140,62+5*j,9)
        add(ev,st+1740,49,160,88,9)
    elif s.startswith("chorus") or s=="final":
        add(ev,st+1200,46,100,62+int(20*it),9)
        add(ev,st+1680,51,100,58+int(20*it),9)
stems["drums"]=save("drums",None,ev,9)

# PERCUSSION — subtle frame-drum/tambourine identity, intentionally sparse under lyrics.
ev=[]
for b in range(TOTAL_BARS):
    st=b*BAR; it=intensity(b); resp=is_response_bar(b); s=section(b)
    mult=.55 if s in ("verse1","verse2","bridge") and not resp else 1.0
    if s=="coda": mult=.35
    for i in [0,3,6]:
        add(ev,st+i*240,54,80,(22+int(24*it))*mult,9)
    if resp or s in ("intro","instrumental"):
        for i,n in [(0,41),(3,43),(6,45)]:
            add(ev,st+i*240,n,140,28+int(28*it),9)
stems["percussion"]=save("percussion",None,ev,9)

# BASS — legato support under vocal, busier only in responses/choruses.
ev=[]
for b,chord in enumerate(chords):
    st=b*BAR; r=roots[chord]; it=intensity(b); resp=is_response_bar(b); s=section(b)
    if s=="coda":
        patt=[(0,r,1280)]
    elif resp:
        patt=[(0,r,450),(480,r+7,420),(960,r+12,360),(1440,r+7,300)]
    elif s.startswith("chorus") or s=="final":
        patt=[(0,r,600),(720,r+7,480),(1440,r+12,360)]
    else:
        patt=[(0,r,780),(960,r+7,660)]
    for t,n,d in patt: add(ev,st+t,n,d,52+int(34*it))
stems["bass"]=save("bass",33,ev)

# GUITAR LEFT — clean/held under voice, power response in open bars.
ev=[]
for b,chord in enumerate(chords):
    st=b*BAR; ns=guitar[chord]; it=intensity(b); resp=is_response_bar(b); s=section(b)
    if s in ("coda","outro"):
        for n in ns: add(ev,st,n,1500,34+int(20*it))
    elif resp or s=="instrumental":
        for off in [0,600,1200]:
            for n in ns:add(ev,st+off,n,390,50+int(36*it))
    elif s.startswith("chorus") or s=="final":
        for off in [0,960]:
            for n in ns:add(ev,st+off,n,700,48+int(34*it))
    else:
        for n in ns:add(ev,st,n,1480,34+int(24*it))
stems["guitar_left"]=save("guitar_left",30,ev)

# GUITAR RIGHT — arpeggio breathes around lyrics.
ev=[]
for b,chord in enumerate(chords):
    st=b*BAR; ns=triads[chord]; resp=is_response_bar(b); s=section(b); it=intensity(b)
    if resp:
        seq=[0,2,1,2,0,1]
        step=300
    elif s in ("coda","outro"):
        seq=[0,1,2,1]; step=420
    else:
        seq=[0,1,2,1,0,1]; step=300
    for i,idx in enumerate(seq):
        add(ev,st+i*step,ns[idx]+12,step-50,34+int(24*it)+(8 if resp else 0))
stems["guitar_right"]=save("guitar_right",27,ev)

# ACOUSTIC — dark-folk support in verses/coda only.
ev=[]
for b,chord in enumerate(chords):
    s=section(b)
    if s not in ("intro","verse1","verse2","bridge","coda","outro"):continue
    st=b*BAR; ns=triads[chord]; resp=is_response_bar(b)
    if resp:
        for off in [0,480,960,1440]:
            for n in ns:add(ev,st+off,n,300,34)
    else:
        for i,idx in enumerate([0,2,1,2]):
            add(ev,st+i*480,ns[idx],420,38 if i else 46)
stems["acoustic"]=save("acoustic",25,ev)

# ORGAN — enters on choruses and final, restrained on bridge.
ev=[]
for b,chord in enumerate(chords):
    s=section(b)
    if s not in ("chorus1","chorus2","bridge","final"):continue
    st=b*BAR
    level=34 if s=="bridge" else 46
    for n in triads[chord]:add(ev,st,n,1820,level)
stems["organ"]=save("organ",18,ev)

# STRINGS — long shadows; never compete with diction.
ev=[]
for b,chord in enumerate(chords):
    s=section(b)
    if s not in ("chorus1","chorus2","bridge","final","coda"):continue
    st=b*BAR
    level=26 if s=="coda" else 34 if s=="bridge" else 40
    for n in triads[chord][1:]:add(ev,st,n+12,1840,level)
stems["strings"]=save("strings",48,ev)

# LEAD GUITAR — actual reply voice in response bars + instrumental section.
ev=[]
replyA=[69,67,64,62,64,67]
replyB=[64,67,69,67,64,62]
for b in range(TOTAL_BARS):
    st=b*BAR; s=section(b); resp=is_response_bar(b)
    if resp:
        seq=replyA if (b//3)%2==0 else replyB
        for i,n in enumerate(seq):add(ev,st+i*300,n,240,54+5*i)
    elif s=="instrumental":
        seq=[64,67,69,72,69,67,64,62] if b<82 else [67,69,72,74,76,74,72,69]
        for i,n in enumerate(seq):add(ev,st+i*240,n,190,68+(10 if i in (0,3,6) else 0))
stems["lead_guitar"]=save("lead_guitar",29,ev)

# PIANO — only intro/coda/outro and tiny bridge punctuation.
ev=[]
for b,chord in enumerate(chords):
    s=section(b)
    if s not in ("intro","bridge","coda","outro"):continue
    st=b*BAR; ns=triads[chord]
    if s=="bridge" and not is_response_bar(b): continue
    for off,idx in [(0,0),(480,1),(960,2),(1440,1)]:
        add(ev,st+off,ns[idx]+12,380,34 if s=="bridge" else 40)
stems["piano"]=save("piano",0,ev)

# Editable combined MIDI
combined=MidiFile(ticks_per_beat=TPB)
meta=MidiTrack();combined.tracks.append(meta)
meta.append(MetaMessage("set_tempo",tempo=bpm2tempo(BPM),time=0))
meta.append(MetaMessage("time_signature",numerator=4,denominator=4,time=0))
for name,path in stems.items():
    src=MidiFile(path); tr=MidiTrack(); tr.append(MetaMessage("track_name",name=name,time=0))
    for msg in src.tracks[-1]:tr.append(msg.copy())
    combined.tracks.append(tr)
combined.save(ROOT/"NE_S_NIM_REBUILD_A_arrangement.mid")

filters={
"drums":"highpass=f=35,acompressor=threshold=-18dB:ratio=3.0:attack=5:release=95,equalizer=f=80:t=q:w=1:g=2,equalizer=f=4800:t=q:w=1:g=2,volume=0.92",
"percussion":"highpass=f=100,equalizer=f=6500:t=q:w=1:g=1.5,volume=0.40",
"bass":"highpass=f=28,lowpass=f=5500,acompressor=threshold=-20dB:ratio=3.5:attack=10:release=120,volume=0.86",
"guitar_left":"highpass=f=85,lowpass=f=10500,acompressor=threshold=-20dB:ratio=2.8:attack=8:release=110,volume=0.68",
"guitar_right":"highpass=f=100,lowpass=f=11500,acompressor=threshold=-20dB:ratio=2.4:attack=10:release=120,aecho=0.9:0.75:70:0.07,volume=0.54",
"acoustic":"highpass=f=95,lowpass=f=12500,aecho=0.9:0.75:90:0.05,volume=0.44",
"organ":"highpass=f=90,lowpass=f=9000,aecho=0.85:0.72:85|170:0.07|0.03,volume=0.32",
"strings":"highpass=f=120,lowpass=f=11000,aecho=0.85:0.70:110|220:0.08|0.035,volume=0.30",
"lead_guitar":"highpass=f=110,lowpass=f=11000,acompressor=threshold=-18dB:ratio=2.6:attack=8:release=100,aecho=0.88:0.72:110|220:0.10|0.04,volume=0.60",
"piano":"highpass=f=100,lowpass=f=12000,aecho=0.9:0.75:100:0.06,volume=0.32"}
proc=ROOT/"processed";proc.mkdir(exist_ok=True)
for name,midipath in stems.items():
    raw=ROOT/(name+"_raw.wav"); out=proc/(name+".wav")
    subprocess.run(["fluidsynth","-ni","-F",str(raw),"-r",str(SR),str(SF),str(midipath)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(raw),"-af",
                    filters[name]+f",atrim=duration={SONG_SECONDS:.3f},apad=pad_dur=1",
                    "-ar",str(SR),str(out)],check=True)
    raw.unlink(missing_ok=True)

manifest={
 "version":"REBUILD_A","bpm":BPM,"key":"A minor","bars":TOTAL_BARS,
 "duration_target":SONG_SECONDS,"stems":list(stems),
 "design":"3-bar long lines with ensemble response bars; 2-bar chorus lines"
}
(ROOT/"arrangement-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False))
