#!/usr/bin/env python3
"""Апскейл кадров Real-ESRGAN (spandrel, MPS).
usage: ~/.studio/bin/tpy upscale.py <in.mp4|in.png> <out.mp4|out.png> [--ss A --to B] [--out-w 1080] [--model шлях.pth]
Видео: декод ffmpeg -> модель x4 -> масштаб до --out-w (по ширине) -> x264 crf 16, без звука."""
import os, sys, argparse, subprocess, numpy as np, torch, time
os.environ["PATH"] = os.path.expanduser("~/.studio/bin") + ":" + os.environ.get("PATH", "")
from spandrel import ModelLoader
ap = argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--model", default=os.path.expanduser("~/.studio/models/realesr-general-x4v3.pth"))
ap.add_argument("--ss"); ap.add_argument("--to"); ap.add_argument("--out-w", type=int, default=1080)
a = ap.parse_args()
dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
m = ModelLoader().load_from_file(a.model).to(dev).eval()
if m.model.__class__.__name__ != "SRVGGNetCompact": m = m.half() if False else m
def run(img):  # HxWx3 uint8
    t = torch.from_numpy(img).to(dev).permute(2,0,1).unsqueeze(0).float()/255
    with torch.no_grad(): y = m(t)
    return (y.clamp(0,1)[0].permute(1,2,0).cpu().numpy()*255+.5).astype(np.uint8)
if a.inp.endswith(".png"):
    from PIL import Image
    t0=time.time(); y = run(np.array(Image.open(a.inp).convert("RGB"))); print("s/frame", time.time()-t0)
    Image.fromarray(y).save(a.out); sys.exit()
w,h = map(int, subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0",a.inp],capture_output=True,text=True).stdout.strip().split(","))
inargs = (["-ss",a.ss] if a.ss else []) + (["-to",a.to] if a.to else [])
dec = subprocess.Popen(["ffmpeg","-nostdin","-v","error",*inargs,"-i",a.inp,"-f","rawvideo","-pix_fmt","rgb24","-"],stdout=subprocess.PIPE)
ow = a.out_w; oh = round(h*4*ow/(w*4)/2)*2
enc = subprocess.Popen(["ffmpeg","-nostdin","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{w*4}x{h*4}","-r","30","-i","-",
    "-vf",f"scale={ow}:{oh}:flags=lanczos","-c:v","libx264","-crf","16","-preset","medium","-pix_fmt","yuv420p",a.out],stdin=subprocess.PIPE)
n=0; t0=time.time()
while True:
    buf = dec.stdout.read(w*h*3)
    if len(buf) < w*h*3: break
    enc.stdin.write(run(np.frombuffer(buf,np.uint8).reshape(h,w,3)).tobytes()); n+=1
    if n%150==0: print(n, f"{(time.time()-t0)/n:.2f}s/f", flush=True)
enc.stdin.close(); enc.wait(); print("frames", n, "time", round(time.time()-t0))
