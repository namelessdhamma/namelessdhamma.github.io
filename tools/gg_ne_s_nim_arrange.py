#!/usr/bin/env python3
import json, pathlib, subprocess, sys
from mido import MidiFile, MidiTrack, Message, MetaMessage, bpm2tempo

BPM=108; TPB=480; BAR=1920; SR=48000; TOTAL_BARS=88
SONG_SECONDS=TOTAL_BARS*4*60/BPM + 4.0
ROOT=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "/tmp/gg-song")
ROOT.mkdir(parents=True,exist_ok=True)
SF=pathlib.Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")

chords = (
["Am","Am","F","F","C","G","Am","E"] +
["Am","F","C","G","Am","F","Dm","E","Am","F","C","G","Dm","Am","E","E"] +
["F","C","G","Am","F","C","E","E"] +
["Am","G","F","E"] +
["Am","F","C","G","Dm","Am","E","E"] +
["F","C","G","Am","F","C","E","E"] +
["Dm","Am","F","E","Dm","F","G","E"] +
["Am","F","C","G","Am","F","Dm","E","Am","G","F","E"] +
["Am","F","C","G","Dm","Am","E","Am"] +
["Am","F","E","Am"] +
["Am","F","E","Am"]
)
assert len(chords)==TOTAL_BARS

roots={"Am":33,"F":29,"C":36,"G":31,"Dm":38,"E":28}
triads={"Am":[57,60,64],"F":[53,57,60],"C":[60,64,67],"G":[55,59,62],"Dm":[50,53,57],"E":[52,56,59]}
guitar={"Am":[45,52,57],"F":[41,48,53],"C":[48,55,60],"G":[43,50,55],"Dm":[38,45,50],"E":[40,47,52]}
scale=[57,59,60,62,64,65,67,69,71,72,74,76]

def sec(bar):
    if bar<8:return "intro"
    if bar<24:return "verse1"
    if bar<32:return "chorus1"
    if bar<36:return "post"
    if bar<44:return "verse2"
    if bar<52:return "chorus2"
    if bar<60:return "bridge"
    if bar<72:return "instrumental"
    if bar<80:return "final"
    if bar<84:return "coda"
    return "outro"

def intensity(bar):
    return {"intro":.38,"verse1":.58,"chorus1":.92,"post":.68,"verse2":.68,"chorus2":.96,
            "bridge":.82,"instrumental":1.0,"final":1.0,"coda":.48,"outro":.26}[sec(bar)]

def add(ev,tick,note,dur,vel=90,ch=0):
    ev += [(tick,0,Message("note_on",note=int(note),velocity=max(1,min(127,int(vel))),channel=ch,time=0)),
           (tick+max(1,int(dur)),1,Message("note_off",note=int(note),velocity=0,channel=ch,time=0))]

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
ev=[]; starts={0,8,24,36,44,52,60,72,80,84}; transitions={7,23,31,35,43,51,59,71,79,83,87}
for b in range(TOTAL_BARS):
    st=b*BAR; it=intensity(b)
    for i in range(8):
        add(ev,st+i*240,42,80,36+int(34*it)+(8 if i in (0,3,6) else 0),9)
    for i in [0,3,6]+([4] if it>.85 else []): add(ev,st+i*240,36,120,55+int(52*it),9)
    for i in [2,6]: add(ev,st+i*240,38,120,50+int(58*it),9)
    if b in starts and b>0:add(ev,st,49,220,62+int(45*it),9)
    if it>.8:
        add(ev,st+5*240,46,120,58+int(30*it),9)
        if b%2:add(ev,st+7*240,51,140,54+int(28*it),9)
    if b in transitions:
        for j,n in enumerate([45,47,43,41]): add(ev,st+4*240+j*240,n,170,70+8*j,9)
stems["drums"]=save("drums",None,ev,9)

ev=[]
for b in range(TOTAL_BARS):
    st=b*BAR; it=intensity(b); s=sec(b); base=22+int(24*it)
    for i in [0,3,6]: add(ev,st+i*240,54,90,base+(8 if i==6 else 0),9)
    if s in ("intro","bridge","instrumental","coda"):
        for i,n in [(0,41),(3,43),(6,45)]: add(ev,st+i*240,n,150,26+int(26*it),9)
    if s=="instrumental":
        for i in [1,2,4,5,7]: add(ev,st+i*240,70,70,24+int(18*it),9)
stems["percussion"]=save("percussion",None,ev,9)

ev=[]
for b,chord in enumerate(chords):
    st=b*BAR; r=roots[chord]; it=intensity(b)
    patt=[(0,r,620),(720,r+7,620),(1440,r+12,420)]
    if it>.85:patt += [(960,r+7,300),(1680,r+7,180)]
    for t,n,d in patt:add(ev,st+t,n,d,58+int(36*it))
stems["bass"]=save("bass",33,ev)

ev=[]
for b,chord in enumerate(chords):
    st=b*BAR; notes=guitar[chord]; it=intensity(b); s=sec(b)
    if s in ("intro","coda","outro") and b%2==0:
        offs=[(0,1500)]
    elif it<.75:
        offs=[(0,700),(960,700)]
    else:
        offs=[(0,430),(720,430),(1440,430)]
    for off,d in offs:
        for n in notes:add(ev,st+off,n,d,42+int(38*it))
stems["guitar_left"]=save("guitar_left",30,ev)

ev=[]
for b,chord in enumerate(chords):
    if sec(b)=="instrumental" and 64<=b<68: continue
    st=b*BAR; notes=triads[chord]; it=intensity(b); order=[0,1,2,1,2,1,0,1]
    for i,idx in enumerate(order):add(ev,st+i*240,notes[idx]+12,190,38+int(30*it)+(7 if i in (0,3,6) else 0))
stems["guitar_right"]=save("guitar_right",27,ev)

ev=[]
for b,chord in enumerate(chords):
    if sec(b) not in ("intro","verse1","verse2","coda","outro"):continue
    st=b*BAR; notes=triads[chord]
    for i,idx in enumerate([0,2,1,2,0,2,1,2]):add(ev,st+i*240,notes[idx],180,46 if i%3 else 56)
stems["acoustic"]=save("acoustic",25,ev)

ev=[]
for b,chord in enumerate(chords):
    if sec(b) not in ("chorus1","chorus2","bridge","final"):continue
    st=b*BAR
    for n in triads[chord]:add(ev,st,n,1820,38+int(22*intensity(b)))
stems["organ"]=save("organ",18,ev)

ev=[]
for b,chord in enumerate(chords):
    if sec(b) not in ("chorus1","chorus2","bridge","final","coda"):continue
    st=b*BAR
    for n in triads[chord][1:]:add(ev,st,n+12,1860,32+int(24*intensity(b)))
stems["strings"]=save("strings",48,ev)

ev=[]; motif=[0,2,4,5,4,2,1,0,2,4,7,5,4,2,1,0]
for b in range(60,72):
    st=b*BAR
    for i in range(8):
        deg=motif[((b-60)*2+i)%len(motif)]; note=scale[deg%len(scale)]
        if b>=68 and i in (3,6):note+=12
        add(ev,st+i*240,note,190,72+(10 if i in (0,3,6) else 0))
for b in range(32,36):
    st=b*BAR
    for i,n in enumerate([69,67,64,62,64,67]):add(ev,st+i*320,n,250,58+4*i)
stems["lead_guitar"]=save("lead_guitar",29,ev)

ev=[]
for b in range(80,88):
    st=b*BAR; ns=triads[chords[b]]
    for off,idx in [(0,0),(480,1),(960,2),(1440,1)]:add(ev,st+off,ns[idx]+12,400,42)
stems["piano"]=save("piano",0,ev)

combined=MidiFile(ticks_per_beat=TPB)
meta=MidiTrack(); combined.tracks.append(meta)
meta.append(MetaMessage("set_tempo",tempo=bpm2tempo(BPM),time=0)); meta.append(MetaMessage("time_signature",numerator=4,denominator=4,time=0))
for name,path in stems.items():
    src=MidiFile(path); tr=MidiTrack(); tr.append(MetaMessage("track_name",name=name,time=0))
    for msg in src.tracks[-1]:tr.append(msg.copy())
    combined.tracks.append(tr)
combined.save(ROOT/"NE_S_NIM_arrangement.mid")

filters={
"drums":"highpass=f=35,acompressor=threshold=-18dB:ratio=3.2:attack=5:release=90,equalizer=f=80:t=q:w=1:g=2,equalizer=f=4800:t=q:w=1:g=2,volume=0.92",
"percussion":"highpass=f=100,equalizer=f=6500:t=q:w=1:g=2,volume=0.46",
"bass":"highpass=f=28,lowpass=f=5500,acompressor=threshold=-20dB:ratio=3.8:attack=9:release=110,volume=0.88",
"guitar_left":"highpass=f=85,lowpass=f=10500,acompressor=threshold=-20dB:ratio=3:attack=8:release=110,volume=0.72",
"guitar_right":"highpass=f=100,lowpass=f=11500,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=120,aecho=0.9:0.75:70:0.08,volume=0.58",
"acoustic":"highpass=f=95,lowpass=f=12500,aecho=0.9:0.75:90:0.06,volume=0.50",
"organ":"highpass=f=90,lowpass=f=9000,aecho=0.85:0.72:85|170:0.08|0.035,volume=0.34",
"strings":"highpass=f=120,lowpass=f=11000,aecho=0.85:0.70:110|220:0.10|0.04,volume=0.34",
"lead_guitar":"highpass=f=110,lowpass=f=11000,acompressor=threshold=-18dB:ratio=2.8:attack=8:release=100,aecho=0.88:0.72:110|220:0.12|0.05,volume=0.62",
"piano":"highpass=f=100,lowpass=f=12000,aecho=0.9:0.75:100:0.07,volume=0.36"}
procdir=ROOT/"processed";procdir.mkdir(exist_ok=True)
for name,midipath in stems.items():
    raw=ROOT/(name+"_raw.wav");out=procdir/(name+".wav")
    subprocess.run(["fluidsynth","-ni","-F",str(raw),"-r",str(SR),str(SF),str(midipath)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(raw),"-af",filters[name]+f",atrim=duration={SONG_SECONDS:.3f},apad=pad_dur=1","-ar",str(SR),str(out)],check=True)
    raw.unlink(missing_ok=True)

manifest={"bpm":BPM,"key":"A minor","bars":TOTAL_BARS,"duration_target":SONG_SECONDS,"chords":chords,"stems":list(stems)}
(ROOT/"arrangement-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False))
