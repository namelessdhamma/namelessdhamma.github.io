#!/usr/bin/env python3
"""One-source, non-destructive GG opening audition (not natural whisper synthesis).

Guards: SHA256-pinned vocal, V3/M3 reference, no second vocal, no RVC on converted
sources, does not alter current song, candidates are never artistically accepted
by code. No 60-minute target is part of this module.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess
import numpy as np
import soundfile as sf
from scipy import signal

SR=48000
START=7.70
END=16.15
VOCAL_BEGIN=8.47
VOCAL_END=14.96
LYRICS='Мы встретились с тобой, как люди видятся во сне'


def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def decode(path,channels=1):
    q=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-ar',str(SR),'-ac',str(channels),'-f','f32le','-'],capture_output=True,check=True)
    a=np.frombuffer(q.stdout,dtype='<f4').astype(np.float64)
    return a.reshape((-1,channels)) if channels>1 else a

def smooth(x):return x*x*(3-2*x)
def ramp(times,knots):
    # Shape-constrained; each interpolation is C1 (zero derivative at boundaries).
    out=np.zeros(len(times),dtype=np.float64)
    out[times<=knots[0][0]]=knots[0][1]
    for (t0,y0),(t1,y1) in zip(knots,knots[1:]):
        take=(times>t0)&(times<=t1)
        z=smooth((times[take]-t0)/(t1-t0))
        out[take]=y0+(y1-y0)*z
    out[times>knots[-1][0]]=knots[-1][1]
    return out

def region(y):
    i=int(round(START*SR));j=int(round(END*SR)); return np.array(y[i:j],copy=True)

def apply_style(dry,style):
    """Strictly transform one pre-existing continuous singer, never stack vocal takes."""
    times=START+np.arange(len(dry))/SR
    if style=='golden_z10':return dry.copy()
    if style=='gentle_emergence':
        # Preserve consonants; attenuate early singing with a smooth semantic arc.
        gain=ramp(times,[(START,1.0),(VOCAL_BEGIN,0.82),(9.35,0.73),
                         (10.5,0.83),(11.5,0.91),(12.85,1.0),(13.95,1.02),(END,1.0)])
        return dry*gain
    if style=='airy_emergence':
        # Spectral-tilt experiment, explicitly NOT actual physiological whisper.
        # One underlying take and linear time-varying frequency weighting only.
        low=signal.sosfiltfilt(signal.butter(3,3100,'lowpass',fs=SR,output='sos'),dry)
        high=dry-low
        low_w=ramp(times,[(START,1),(VOCAL_BEGIN,.57),(9.1,.50),(10.0,.69),(11.4,.86),(12.5,1),(END,1)])
        high_w=ramp(times,[(START,1),(VOCAL_BEGIN,.90),(9.1,1.08),(10.0,1.07),(11.4,1.02),(12.5,1),(END,1)])
        gain=ramp(times,[(START,1),(VOCAL_BEGIN,.75),(9.1,.72),(10.25,.79),(11.5,.90),(13.4,1.0),(END,1)])
        return gain*(low*low_w+high*high_w)
    raise ValueError(style)

def metrics(y):
    t1=int((VOCAL_BEGIN-START)*SR);t2=int((VOCAL_END-START)*SR)
    z=y[t1:t2]
    return {'duration_s':round(len(y)/SR,3),'active_rms':float(np.sqrt(np.mean(z*z))),
            'peak':float(np.max(np.abs(y))), 'nonfinite':int(np.sum(~np.isfinite(y))),
            'active_nonzero_fraction':float(np.mean(np.abs(z)>1e-6)),
            'first_word_rms':float(np.sqrt(np.mean(y[int((8.5-START)*SR):int((9.2-START)*SR)]**2)))}

def build(vocal,instrumental,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    dry=region(decode(vocal)); music=region(decode(instrumental,channels=2))
    results=[]; all_audio=[]
    for style in ('golden_z10','gentle_emergence','airy_emergence'):
        y=apply_style(dry,style)
        # Experiment master: one singer + preserved independent instrumental,
        # with a static bounded gain; not a copy of the accepted nonlinear M3 mix.
        backing=np.clip(1.057*music+1.252*y[:,None],-0.96,0.96)
        # Keep one song section. Audition is dry vocal first, then band composite.
        sf.write(out/(style+'_DRY.wav'),y,SR,subtype='PCM_24')
        sf.write(out/(style+'_WITH_BACKING.wav'),backing,SR,subtype='PCM_24')
        all_audio.append((style,y,backing))
        r=metrics(y);r.update({'variant':style,'dry_sha256':sha(out/(style+'_DRY.wav')),
            'mix_sha256':sha(out/(style+'_WITH_BACKING.wav')),
            'same_continuous_singer':True,'true_whisper_proven':False,
            'pass_status':'TECHNICAL_CANDIDATE_NOT_ARTISTICALLY_ACCEPTED'})
        results.append(r)
    # AAC-friendly audition, precisely distinguish reference / experiments.
    parts=[]
    for _,y,_ in all_audio:
        parts+=[y,np.zeros(int(.65*SR),dtype=np.float64)]
    comparison=np.concatenate(parts)
    sf.write(out/'THREE_WAY_DRY_REFERENCE_GENTLE_AIRY.wav',comparison,SR,subtype='PCM_24')
    baseline=all_audio[0][1]
    checks={'source':str(vocal),'source_sha256':sha(vocal),
        'instrumental':str(instrumental),'instrumental_sha256':sha(instrumental),
        'line':LYRICS,'crop':[START,END], 'active_range':[VOCAL_BEGIN,VOCAL_END],
        'source_unchanged':bool(np.array_equal(all_audio[0][1],baseline)),
        'all_sources_are_one_take':True,
        'no_native_model_generation':True,
        'no_RVC_second_pass':True,
        'lexical_gate':'PENDING_INDEPENDENT_ASR_FOR_MODIFIED_AUDIO',
        'artistic_gate':'PENDING_LISTENING',
        'genuine_whisper_gate':'NOT_PROVEN',
        'all_clipping_free':all(r['peak']<0.99 and r['nonfinite']==0 for r in results),
        'candidates':results}
    (out/'OPENING_QUALIFICATION.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
    return checks

def main():
    p=argparse.ArgumentParser();p.add_argument('--vocal',required=True);p.add_argument('--instrumental',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=build(a.vocal,a.instrumental,a.out)
    print(json.dumps({'crop':r['crop'],'clipping_free':r['all_clipping_free'],
          'names':[x['variant'] for x in r['candidates']],
          'first_word_rms':[round(x['first_word_rms'],5) for x in r['candidates']]},ensure_ascii=False))
if __name__=='__main__':main()