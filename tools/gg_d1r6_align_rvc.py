#!/usr/bin/env python3
import argparse,json,pathlib,math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, correlate, correlation_lags

def load(path):
    y,sr=sf.read(path,always_2d=False)
    if getattr(y,'ndim',1)>1: y=y.mean(axis=1)
    return np.asarray(y,dtype=np.float32),sr

def resample(y,src,dst):
    if src==dst:return y
    g=math.gcd(src,dst)
    return resample_poly(y,dst//g,src//g).astype(np.float32)

def envelope(y,sr,hz=100):
    hop=max(1,int(sr/hz)); n=(len(y)+hop-1)//hop
    pad=np.pad(y,(0,n*hop-len(y)))
    x=pad.reshape(n,hop)
    return np.sqrt(np.mean(x*x,axis=1)+1e-12)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--guide',required=True); ap.add_argument('--candidate',required=True)
    ap.add_argument('--output',required=True); ap.add_argument('--report',required=True)
    ap.add_argument('--max-lag',type=float,default=1.0)
    a=ap.parse_args()
    g,gsr=load(a.guide); c,csr=load(a.candidate); c=resample(c,csr,gsr); sr=gsr
    eg=envelope(g,sr); ec=envelope(c,sr)
    # Normalize envelopes and search only bounded lags.
    eg=(eg-eg.mean())/(eg.std()+1e-8); ec=(ec-ec.mean())/(ec.std()+1e-8)
    corr=correlate(ec,eg,mode='full',method='fft')
    lags=correlation_lags(len(ec),len(eg),mode='full')
    maxlag=int(a.max_lag*100)
    mask=np.abs(lags)<=maxlag
    idx=np.argmax(corr[mask]); lag=int(lags[mask][idx])
    # correlate(candidate, guide): positive lag => candidate is delayed and must be advanced.
    shift=int(round(lag*sr/100.0))
    if shift>0:
        aligned=c[shift:]
    elif shift<0:
        aligned=np.pad(c,(-shift,0))
    else:
        aligned=c
    if len(aligned)<len(g): aligned=np.pad(aligned,(0,len(g)-len(aligned)))
    aligned=aligned[:len(g)]
    # Bounded normalized correlation score at selected lag.
    score=float(corr[mask][idx]/max(1,len(eg)))
    peak=float(np.max(np.abs(aligned))) if len(aligned) else 0.0
    if peak>.99: aligned*=.99/peak
    sf.write(a.output,aligned,sr,subtype='PCM_24')
    report={'status':'PASS' if abs(lag)<=maxlag else 'REJECT',
            'lag_envelope_frames':lag,'lag_seconds':lag/100.0,
            'sample_shift_applied':shift,'correlation_score':score,
            'guide_duration':len(g)/sr,'candidate_duration_before':len(c)/sr,
            'candidate_duration_after':len(aligned)/sr,'sample_rate':sr}
    pathlib.Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status']=='PASS' else 2
if __name__=='__main__': raise SystemExit(main())
