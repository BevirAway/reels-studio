#!/usr/bin/env python3
"""Нарезка отрезка без пауз + слова с таймингами клипа (для hyperframes).

usage: cutlist.py <audio.wav> <audio.json(whisper words)> <out.json> START-END[!] [START-END ...]
  суффикс ! — кусок целиком, без вырезки пауз (тихая/смазанная речь)
  --min-gap 0.25   паузы длиннее (с) вырезаются
  --pad 0.09       запас тишины вокруг речи (с)
  --thresh -36dB   порог тишины silencedetect

Выход JSON:
  clips: [{src_start, src_end, out_start, dur}]  -> <video data-media-start=src_start-chunk_start data-start=out_start data-duration=dur>
  words: [{w, src, t, end}]                       -> t/end — секунды клипа (для субтитров по словам)
  duration: итоговая длина
Тайминги слов Whisper растягиваются на паузы — поэтому границы кусков берутся по тишине (silencedetect),
а слова только переносятся в новое время. Перед монтажом прогнать tools/splice_check.sh по тем же кускам.
"""
import json, re, subprocess, sys, argparse

ap = argparse.ArgumentParser()
ap.add_argument("audio"); ap.add_argument("words"); ap.add_argument("out"); ap.add_argument("ranges", nargs="+")
ap.add_argument("--min-gap", type=float, default=0.25); ap.add_argument("--pad", type=float, default=0.09)
ap.add_argument("--thresh", default="-36dB")
a = ap.parse_args()

d = json.load(open(a.words)); W = [w for s in d["segments"] for w in s.get("words", [])]
clips, words, t, used = [], [], 0.0, set()
for r in a.ranges:
    whole = r.endswith("!")  # "A-B!" = кусок целиком, паузы внутри не резать (тихая речь, риск съесть слово)
    s0, e0 = map(float, r.rstrip("!").split("-"))
    err = "" if whole else subprocess.run(["ffmpeg", "-nostdin", "-ss", str(s0), "-to", str(e0), "-i", a.audio, "-af",
                          f"silencedetect=n={a.thresh}:d={a.min_gap}", "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [s0 + float(x) for x in re.findall(r"silence_start: ([\d.\-e]+)", err)]
    en = [s0 + float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    sil = list(zip(st, en))
    keep, cur = [], s0
    for ss, se in sil:
        if se - ss < a.min_gap: continue
        cs, ce = max(s0, ss + a.pad), min(e0, se - a.pad)
        if cs > cur: keep.append((cur, cs))
        cur = max(cur, ce)
    if cur < e0: keep.append((cur, e0))
    for ks, ke in keep:
        if ke - ks < 0.05: continue
        clips.append(dict(src_start=round(ks, 3), src_end=round(ke, 3), out_start=round(t, 3), dur=round(ke - ks, 3)))
        for i, w in enumerate(W):
            if i in used: continue
            if w["end"] > ks + 0.03 and w["start"] < ke - 0.03:
                used.add(i)
                ws, we = max(w["start"], ks), min(w["end"], ke)
                words.append(dict(w=w["word"].strip(), src=round(w["start"], 2), t=round(t + ws - ks, 3), end=round(t + we - ks, 3)))
        t += ke - ks
json.dump(dict(ranges=a.ranges, duration=round(t, 3), clips=clips, words=words), open(a.out, "w"), indent=1, ensure_ascii=False)
print(f"{a.out}: {len(clips)} кусков, {len(words)} слов, итог {t:.2f} с")
