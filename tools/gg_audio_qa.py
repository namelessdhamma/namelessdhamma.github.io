#!/usr/bin/env python3
import argparse, json, numpy as np, librosa, pathlib, sys, math

def load(path, sr=22050):
    y,_=librosa.load(path,sr=sr,mono=True)
    return y

def nearest_fraction(src,tgt,limit):
    if len(src)==0 or len(tgt)==0:return 0.0
    hits=0
    for t in src:
        j=np.searchsorted(tgt,t); d=[]
        if j<len(tgt):d.append(abs(tgt[j]-t))
        if j>0:d.append(abs(tgt[j-1]-t))
        if d and min(d)<=limit:hits+=1
    return hits/len(src)

def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x,dtype=float)**2)+1e-12)) if len(x) else 0.0

def db_ratio(a,b):
    return 20*np.log10((a+1e-9)/(b+1e-9))

def tempo_converter(score):
    tpb=score['ticks_per_beat']; bar=tpb*4
    tmap=sorted(score.get('tempo_map') or [{'bar':0,'bpm':score['bpm']}],key=lambda x:x['bar'])
    pts=[(int(p['bar'])*bar,float(p['bpm'])) for p in tmap]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        total+=(tick-last)*60.0/(bpm*tpb)
        return total
    return sec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--vocal',required=True); ap.add_argument('--instrumental',required=True)
    ap.add_argument('--drums',required=True); ap.add_argument('--riff',required=True)
    ap.add_argument('--score',required=True); ap.add_argument('--bpm',type=float,required=True)
    ap.add_argument('--out',required=True)
    args=ap.parse_args()
    sr=22050; hop=512
    yv=load(args.vocal,sr); yi=load(args.instrumental,sr); yd=load(args.drums,sr); yr=load(args.riff,sr)

    f0,_,_=librosa.pyin(yv,fmin=librosa.note_to_hz('C3'),fmax=librosa.note_to_hz('G5'),
                        sr=sr,frame_length=2048,hop_length=hop)
    chroma=librosa.feature.chroma_cqt(y=yi,sr=sr,hop_length=hop)
    n=min(len(f0),chroma.shape[1]); midi=librosa.hz_to_midi(f0[:n]); pcs=np.mod(np.round(midi),12)
    valid=np.isfinite(f0[:n]); supports=[]; top3=[]
    for idx in np.where(valid)[0]:
        c=chroma[:,idx]
        if c.max()<=0:continue
        pc=int(pcs[idx]); supports.append(float(c[pc]/c.max())); top3.append(pc in np.argsort(c)[::-1][:3])

    def ots(y):
        env=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop)
        f=librosa.onset.onset_detect(onset_envelope=env,sr=sr,hop_length=hop,units='frames')
        return librosa.frames_to_time(f,sr=sr,hop_length=hop)
    tv=ots(yv); td=ots(yd); drum_150=nearest_fraction(tv,td,.150)
    beat=60.0/args.bpm; eighth=beat/2; ph=np.mod(tv,eighth); ph=np.minimum(ph,eighth-ph)
    eighth_100=float(np.mean(ph<=.100)) if len(ph) else 0.0

    nfft=2048
    Sv=np.abs(librosa.stft(yv,n_fft=nfft,hop_length=hop)); Si=np.abs(librosa.stft(yi,n_fft=nfft,hop_length=hop)); Sr=np.abs(librosa.stft(yr,n_fft=nfft,hop_length=hop))
    freq=librosa.fft_frequencies(sr=sr,n_fft=nfft); band=(freq>=300)&(freq<=4000)
    nf=min(Sv.shape[1],Si.shape[1],Sr.shape[1])
    Ev=np.sqrt(np.mean(Sv[band,:nf]**2,axis=0))+1e-9
    Ei=np.sqrt(np.mean(Si[band,:nf]**2,axis=0))+1e-9
    Er=np.sqrt(np.mean(Sr[band,:nf]**2,axis=0))+1e-9
    rv=librosa.feature.rms(y=yv,frame_length=2048,hop_length=hop)[0][:nf]
    vdb=librosa.amplitude_to_db(rv+1e-8,ref=np.max); active=vdb>-35
    ratio=20*np.log10(Ei/Ev); rratio=20*np.log10(Er/Ev)
    mask_over_0=float(np.mean(ratio[active]>0)) if np.any(active) else 1.0
    mask_over_6=float(np.mean(ratio[active]>6)) if np.any(active) else 1.0
    inst_med=float(np.median(ratio[active])) if np.any(active) else -120.0
    riff_med=float(np.median(rratio[active])) if np.any(active) else -120.0

    score=json.loads(pathlib.Path(args.score).read_text()); tick_to_sec=tempo_converter(score); tpb=score['ticks_per_beat']; BAR=tpb*4
    first_ids={'v1l1','c1l1','v2l1','c2l1','brl1','finl1','codal1'}
    onset_rows=[]
    for phr in score['phrases']:
        if phr['id'] not in first_ids: continue
        st=tick_to_sec(phr['bar']*BAR+phr['offset'])
        a=yv[int(st*sr):int((st+.15)*sr)]; b=yv[int((st+.20)*sr):int((st+.70)*sr)]
        delta=float(db_ratio(rms(a),rms(b))); onset_rows.append({'id':phr['id'],'attack_vs_body_db':delta})
    vfs_med=float(np.median([x['attack_vs_body_db'] for x in onset_rows])) if onset_rows else 99.0

    metrics={
      'vocal_instrument_top3_pitch_support':float(np.mean(top3)) if top3 else 0.0,
      'vocal_instrument_pitch_support_median':float(np.median(supports)) if supports else 0.0,
      'vocal_onset_within_150ms_of_drum':drum_150,
      'vocal_onset_within_100ms_of_eighth_grid':eighth_100,
      'instrument_over_vocal_300_4000hz_fraction':mask_over_0,
      'instrument_over_vocal_plus6db_fraction':mask_over_6,
      'instrument_to_vocal_midband_median_db':inst_med,
      'riff_to_vocal_midband_median_db':riff_med,
      'vfs_section_start_attack_vs_body_median_db':vfs_med,
      'vfs_section_start_rows':onset_rows,
      'vocal_onsets':int(len(tv))
    }
    thresholds={
      'vocal_instrument_top3_pitch_support':0.55,
      'vocal_onset_within_150ms_of_drum':0.72,
      'instrument_over_vocal_300_4000hz_fraction_max':0.22,
      'instrument_over_vocal_plus6db_fraction_max':0.10,
      'instrument_to_vocal_midband_median_db_min':-16.0,
      'riff_to_vocal_midband_median_db_min':-22.0,
      'vfs_section_start_attack_vs_body_median_db_max':-2.0
    }
    failures=[]
    if metrics['vocal_instrument_top3_pitch_support']<.55: failures.append('harmonic_coupling')
    if metrics['vocal_onset_within_150ms_of_drum']<.72: failures.append('drum_onset_coupling')
    if mask_over_0>.22: failures.append('midband_masking')
    if mask_over_6>.10: failures.append('severe_midband_masking')
    if inst_med<-16.0: failures.append('instrument_buried_under_vocal')
    if riff_med<-22.0: failures.append('riff_buried_under_vocal')
    if vfs_med>-2.0: failures.append('voice_from_silence_attack_missing')
    result={'status':'PASS' if not failures else 'REJECT','metrics':metrics,'thresholds':thresholds,'failures':failures}
    pathlib.Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if not failures else 2

if __name__=='__main__': sys.exit(main())
