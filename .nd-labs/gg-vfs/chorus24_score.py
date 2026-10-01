"""Phoneme-only, 24-note rehearsal score; original song text stays private."""
import math
NOTES = [('G3', 0.375, ['ru/j', 'ru/a']),
 ('A3', 0.5, ['ru/g', 'ru/ax']),
 ('B3', 0.4375, ['ru/v', 'ru/ax']),
 ('D4', 0.65625, ['ru/ry', 'ru/i', 'ru/l']),
 ('B3', 0.46875, ['ru/ny', 'ru/e']),
 ('A3', 0.5625, ['ru/s', 'ru/ny', 'ru/i', 'ru/m']),
 ('G3', 0.375, ['ru/j', 'ru/a']),
 ('A3', 0.5, ['ru/g', 'ru/ax']),
 ('B3', 0.4375, ['ru/v', 'ru/ax']),
 ('D4', 0.65625, ['ru/ry', 'ru/i', 'ru/l']),
 ('C4', 0.46875, ['ru/s', 'ru/s', 'ru/ax']),
 ('B3', 0.5625, ['ru/b', 'ru/o', 'ru/j']),
 ('A3', 0.375, ['ru/a']),
 ('B3', 0.5, ['ru/o', 'ru/n']),
 ('A3', 0.4375, ['ru/v', 'ru/m', 'ru/ax']),
 ('C4', 0.65625, ['ru/i', 'ru/h']),
 ('D4', 0.46875, ['ru/s', 'ru/l', 'ru/o']),
 ('B3', 0.5625, ['ru/v', 'ru/a', 'ru/h']),
 ('B3', 0.375, ['ru/i', 'ru/s']),
 ('C4', 0.5, ['ru/k', 'ru/a', 'ru/l']),
 ('D4', 0.4375, ['ru/ly', 'ru/i', 'ru/sh']),
 ('C4', 0.65625, ['ru/g', 'ru/ax']),
 ('B3', 0.46875, ['ru/l', 'ru/o', 'ru/s']),
 ('G3', 0.5625, ['ru/s', 'ru/v', 'ru/o', 'ru/j'])]
def make():
    tick=512/44100
    phones=[];nums=[];durs=[];f0=[]
    elapsed=0.0
    for pitch,duration,group in NOTES:
        phones.extend(group);nums.append(len(group))
        fractions={1:[1],2:[.15,.85],3:[.12,.76,.12],4:[.12,.12,.64,.12]}[len(group)]
        durs.extend(duration*x for x in fractions)
        midi=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'].index(pitch[:-1])+12*(int(pitch[-1])+1)
        hz=440*2**((midi-69)/12)
        nframes=round((elapsed+duration)/tick)-round(elapsed/tick)
        elapsed+=duration
        for frame in range(nframes):
            t=frame*tick
            approach=-.12*math.exp(-t/.09)
            vib=.025*math.sin(2*math.pi*4.7*(t-.17))*min(1,max(0,(t-.17)/.13))
            f0.append(hz*2**((approach+vib)/12))
    assert len(phones)==sum(nums)==len(durs)
    ds={'offset':0.0,'text':'GG VFS chorus 24-note phoneme rehearsal',
        'ph_seq':' '.join(phones),'ph_num':' '.join(map(str,nums)),
        'ph_dur':' '.join(f'{x:.6f}' for x in durs),
        'note_seq':' '.join(p for p,_,_ in NOTES),
        'note_dur':' '.join(str(d) for _,d,_ in NOTES),
        'note_slur':' '.join(['0']*len(NOTES)),
        'f0_seq':' '.join(f'{x:.3f}' for x in f0),
        'f0_timestep':str(tick)}
    assert len(NOTES)==24 and abs(sum(durs)-12)<1e-5
    return ds,f0
