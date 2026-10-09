#!/usr/bin/env python3
"""One source-phoneme replacement for sung /dʲa/ in 'видятся' with the original clean score guide.
Never mistake technical tests for artistic approval; one singer stem / musical master protected.
"""
from pathlib import Path
import json, hashlib, subprocess
import numpy as np
import soundfile as sf
from scipy import signal, ndimage
from build_phrase_repair import ROOT, OUT, SR, LOCK, sha, decode, START, END
from assemble_full_song import full_decode, write_mp3

# Determined by canonical D1_FULL_V3 score and acoustic inspection of the vowel.
ONSET, OFFSET = 13.055, 13.325
ATTACK, RELEASE = 0.068, 0.062
LOCK_GUIDE='ea3f0798db4e60927e307467997ea00856bf807d7959a952aa66281182fbc14e'

def shift_audio(y, lag):
    if lag == 0: return y
    if lag > 0: return np.pad(y[:-lag],(lag,0))
    return np.pad(y[-lag:],(0,-lag))

def donor_vowel(v, g):
    """Donor's actual waveshape and phoneme are retained, but broad timbre and volume align.
    This is not another spectral-only injection into original V3 phase (v0.10 B/C).
    """
    assert v.shape==g.shape and len(v)>100000
    nfft=2048;hop=256
    _,t,V=signal.stft(v,fs=SR,nperseg=nfft,noverlap=nfft-hop)
    _,_,G=signal.stft(g,fs=SR,nperseg=nfft,noverlap=nfft-hop)
    timeline=t+START
    center=(timeline>13.115)&(timeline<13.250)
    assert center.sum()>10
    v_m=np.median(np.abs(V[:,center]),axis=1)
    g_m=np.median(np.abs(G[:,center]),axis=1)
    # Match only broad speaker spectral envelope; preserve donor vowel shape & phoneme.
    ratio=ndimage.gaussian_filter1d(np.log(np.maximum(v_m,1.e-7))-np.log(np.maximum(g_m,1.e-7)),sigma=13)
    ratio=np.exp(np.clip(ratio*0.32,-0.45,0.45))
    ratio[0]=1.0
    Y=G*ratio[:,None]
    _,yd=signal.istft(Y,fs=SR,nperseg=nfft,noverlap=nfft-hop)
    yd=yd[:len(v)]
    # Align periodic phases around the vocal vowel's center.
    mid=round((13.18-START)*SR)
    N=round(0.045*SR)
    va=v[mid-N:mid+N];gb=yd[mid-N:mid+N]
    candidates=np.arange(-70,71)
    cov=[]
    for lag in candidates:
        y=shift_audio(yd,int(lag))
        d=y[mid-N:mid+N]
        cov.append(float(np.dot(d,va)/(np.linalg.norm(d)*np.linalg.norm(va)+1e-12)))
    lag=int(candidates[np.argmax(cov)])
    yd=shift_audio(yd,lag)
    region=slice(round((13.09-START)*SR),round((13.28-START)*SR))
    vr=float(np.sqrt(np.mean(v[region]**2)))
    dr=float(np.sqrt(np.mean(yd[region]**2)))
    gain=float(np.clip(vr/max(dr,1e-8),0.7,3.0))
    yd*=gain
    return yd,{'phase_alignment_samples':lag,'phase_correlation':max(cov),'rms_gain':gain}

def patch_intro(v,g):
    vd,info=donor_vowel(v,g)
    timeline=START+np.arange(len(v))/SR
    lin=np.clip((timeline-ONSET)/ATTACK,0,1)
    lout=np.clip((OFFSET-timeline)/RELEASE,0,1)
    smooth=lambda a:a*a*(3-2*a)
    weight=0.83*smooth(lin)*smooth(lout)
    y=v*(1-weight)+vd*weight
    diff=np.where(np.abs(y-v)>1e-6)[0]
    assert len(diff)>2000
    assert timeline[diff.min()]>=ONSET and timeline[diff.max()]<=OFFSET
    # The waveform has no sharp stitching discontinuity; old singer restored at edges.
    edge_samples=[round((ONSET-START)*SR),round((OFFSET-START)*SR)]
    jumps=[float(abs(y[i]-y[i-1])) for i in edge_samples]
    base=float(np.quantile(np.abs(np.diff(v)),0.999))
    assert max(jumps)<base,('donor glitch at boundary',jumps,base)
    return y,{'donor':info,'window':[ONSET,OFFSET],'fade':[ATTACK,RELEASE], 'max_donor_weight':0.83,'edge_jumps':jumps,'baseline_p999_jump':base,'change_rms':float(np.sqrt(np.mean((y-v)**2)))}

def main():
    for k,v in LOCK.items():assert sha(ROOT/k)==v,k
    assert sha(ROOT/'D1_CLEAN_GUIDE_FULL.wav')==LOCK_GUIDE
    v=decode('VOCAL_REPAIRED_V3.mp3')[:,0].astype('float64')
    g=decode('D1_CLEAN_GUIDE_FULL.wav')[:,0].astype('float64')
    new,info=patch_intro(v,g)
    orig=full_decode(ROOT/'M3_REVIEW_V3.mp3',2)
    a=round(START*SR);N=len(new)
    delta=new-v
    mask=(START+np.arange(N)/SR>=ONSET)&(START+np.arange(N)/SR<=OFFSET)
    delta[~mask]=0.0
    assert np.array_equal(delta[~mask],np.zeros((~mask).sum()))
    edited=orig.copy()
    edited[a:a+N,0]+=1.252*delta
    edited[a:a+N,1]+=1.252*delta
    assert np.array_equal(edited[:a+round((ONSET-START)*SR)],orig[:a+round((ONSET-START)*SR)])
    assert np.array_equal(edited[a+round((OFFSET-START)*SR):],orig[a+round((OFFSET-START)*SR):])
    assert np.max(np.abs(edited)) <= np.max(np.abs(orig)) + 1e-5
    dst=OUT/'GG_NEZRIMY_FULL_M3_REAL_DYA_SOURCE_DONOR_D_REVIEW.wav'
    sf.write(dst,edited,SR,subtype='FLOAT')
    write_mp3(dst,dst.with_suffix('.mp3'))
    # 9sec direct comparison from exactly same absolute song timeline
    a0=round(7.5*SR);a1=round(16.5*SR)
    for label,x in [('GOLDEN_M3',orig),('D_REAL_DYA',edited)]:
      w=OUT/f'INTRO_{label}.wav'
      sf.write(w,x[a0:a1],SR,subtype='PCM_24')
      write_mp3(w,w.with_suffix('.mp3'))
    # A -- pause -- D -- pause -- A, 3x9s. Both use SAME M3 original master.
    sl=np.zeros(round(.7*SR),dtype=np.float32)
    ab=np.concatenate([orig[a0:a1].astype('float32'),np.column_stack([sl,sl]),edited[a0:a1].astype('float32'),np.column_stack([sl,sl]),orig[a0:a1].astype('float32')])
    abfile=OUT/'GG_FIRST_LINE_GOLDEN_VS_REAL_DYA_DONOR.mp3'
    sf.write(abfile.with_suffix('.wav'),ab,SR,subtype='PCM_24')
    write_mp3(abfile.with_suffix('.wav'),abfile)
    qa={'status':'REVIEW_ONLY_NOT_APPROVED','route':'V3 permanent vocalist / actual D1 guide phoneme waveform blended in word видятся','difference_from_previous':'Original donor source phase + broad timbre matching rather than donor magnitude on V3 phase','whisper':'DEFERRED','full_song_seconds':len(orig)/SR,'source_sha256':{k:sha(ROOT/k) for k in list(LOCK)+['D1_CLEAN_GUIDE_FULL.wav']},'preservation':'Other than one exact vowel patch, float32 original M3 unchanged','technical':info,'candidate_mp3':dst.with_suffix('.mp3').name,'candidate_sha256':sha(dst.with_suffix('.mp3')),'limitation':'Donor may sound like a different singing timbre or electronic splice; ONLY user review can decide. Strict phonetic recognition does not guarantee vowel morphology.'}
    (OUT/'V12_DYA_DONOR_MANIFEST.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2))
    print(json.dumps({'status':qa['status'],'patch':qa['technical'],'mp3':str(dst.with_suffix('.mp3')),'sha':qa['candidate_sha256']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()