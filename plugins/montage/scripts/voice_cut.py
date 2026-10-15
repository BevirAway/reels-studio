#!/usr/bin/env python3
"""Склеить голос по нарезке: voice_cut.py <cut.json> <src48k.wav> <out.wav> (микрофейды 8 мс на стыках)."""
import json, os, subprocess, sys
os.environ["PATH"] = os.path.expanduser("~/.studio/bin") + ":" + os.environ.get("PATH", "")
cut = json.load(open(sys.argv[1])); args, filt = [], []
for i, c in enumerate(cut["clips"]):
    args += ["-ss", f"{c['src_start']:.3f}", "-to", f"{c['src_end']:.3f}", "-i", sys.argv[2]]
    d = c["src_end"] - c["src_start"]; f = min(0.008, d / 3)
    filt.append(f"[{i}:a]aresample=48000,afade=t=in:d={f:.3f},afade=t=out:st={d - f:.3f}:d={f:.3f}[a{i}]")
n = len(cut["clips"])
filt.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[v]")
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args, "-filter_complex", ";".join(filt), "-map", "[v]", "-ac", "1",
                "-ar", "48000", sys.argv[3]], check=True)
