#!/usr/bin/env python3
# «Прослушка» звуков без ушей: длительность, секунда пика, начало, пик dBFS, тембр (центроид). sfx_audit.py "glob" ["glob"...]
# Пик нужен для выравнивания: data-start = кадр события - peak.
import sys,subprocess,numpy as np,glob,os
for f in sorted(sum([glob.glob(p) for p in sys.argv[1:]],[])):
    raw=subprocess.run(['ffmpeg','-v','error','-i',f,'-ac','1','-ar','22050','-f','f32le','-'],capture_output=True).stdout
    x=np.frombuffer(raw,np.float32)
    if len(x)==0: print(f,'EMPTY'); continue
    hop=441; n=len(x)//hop; r=np.sqrt((x[:n*hop].reshape(n,hop)**2).mean(1)+1e-12); db=20*np.log10(r)
    pk=db.argmax()*hop/22050; peak=20*np.log10(np.abs(x).max()+1e-9)
    # onset: first frame within 20dB of peak
    on=np.argmax(db>db.max()-20)*hop/22050
    X=np.abs(np.fft.rfft(x[:min(len(x),22050*4)])); fr=np.fft.rfftfreq(min(len(x),22050*4),1/22050); cen=(X*fr).sum()/X.sum()
    print(f"{os.path.basename(f):38s} dur={len(x)/22050:6.2f} peak@{pk:5.2f}s onset@{on:5.2f}s peak={peak:6.1f}dBFS centroid={cen:6.0f}Hz")
