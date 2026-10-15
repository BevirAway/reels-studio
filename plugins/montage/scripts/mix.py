#!/usr/bin/env python3
"""Звук рілса: mix.py <папка проєкту hyperframes> <voice.wav> [SFX_DB] [MUSIC_DB]  (правила — references/guide.md §5).
Голос — voice.py (−13 LUFS). Эффекты и музыка из <вариант>/work/audio_tags.html (пишет build.py) — раздельными
стемами: эффекты медианой −16…−20 дБ к голосу, музыка ≈ −26 дБ под голосом; общий фон приглушается голосом на −4…−6 дБ.
Итог → <вариант>/assets/mix.wav, лимитер 0.76 (true peak ≈ −2 dBFS)."""
import json, os, re, subprocess, sys
os.environ["PATH"] = os.path.expanduser("~/.studio/bin") + ":" + os.environ.get("PATH", "")
from pathlib import Path
V = Path(sys.argv[1]).resolve(); VOICE = Path(sys.argv[2]).resolve()
SFX_DB = float(sys.argv[3]) if len(sys.argv) > 3 else 20; MUSIC_DB = float(sys.argv[4]) if len(sys.argv) > 4 else 0
D = float(re.search(r'data-composition-id="main"[^>]*data-duration="([\d.]+)"', (V / "index.html").read_text()).group(1))
W = V / "work"


def ff(args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y"] + args, check=True, cwd=V)


tags = re.findall(r"<audio ([^>]*)></audio>", (W / "audio_tags.html").read_text())
attr = lambda t, k: (re.search(k + r'="([^"]*)"', t) or [None, None])[1]


def stem(tags, out):
    if not tags:
        ff(["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", str(D), out]); return
    args, filt = [], []
    for i, t in enumerate(tags):
        src, st, du = attr(t, "src"), float(attr(t, "data-start")), float(attr(t, "data-duration"))
        ms, vol = float(attr(t, "data-media-start") or 0), float(attr(t, "data-volume") or 1)
        env = ""
        am = re.search(r"data-automation='([^']*)'", t)
        if am:
            pts = json.loads(am.group(1))["lanes"][0]["points"]
            # огибающая громкости по точкам (t — от начала звука), линейно
            expr = f"{pts[-1]['v']}"
            for a, b in reversed(list(zip(pts, pts[1:]))):
                expr = (f"if(lt(t,{b['t']}),{a['v']}+({b['v']}-{a['v']})*(t-{a['t']})/{max(1e-3, b['t'] - a['t'])},{expr})")
            env = f",volume='{expr}':eval=frame"
        args += ["-i", src]
        d_ms = int(st * 1000)
        filt.append(f"[{i}:a]atrim=start={ms}:duration={du},asetpts=PTS-STARTPTS,aresample=48000,"
                    f"aformat=channel_layouts=stereo,volume={vol}{env},adelay={d_ms}|{d_ms}[s{i}]")
    k = len(tags)
    filt.append("".join(f"[s{i}]" for i in range(k)) + f"amix=inputs={k}:normalize=0:duration=longest,apad=whole_dur={D},atrim=0:{D}[bg]")
    ff(args + ["-filter_complex", ";".join(filt), "-map", "[bg]", "-ar", "48000", out])


is_mus = lambda t: 'id="mus' in t
stem([t for t in tags if not is_mus(t)], "work/sfx_raw.wav")
stem([t for t in tags if is_mus(t)], "work/music_raw.wav")
ff(["-i", str(VOICE), "-af", f"apad=whole_dur={D},atrim=0:{D}", "-ac", "2", "-ar", "48000", "work/voice.wav"])
duck = "sidechaincompress=threshold=0.1:ratio=2:attack=8:release=250:knee=4"
ff(["-i", "work/sfx_raw.wav", "-i", "work/music_raw.wav", "-i", "work/voice.wav", "-filter_complex",
    f"[0:a]volume={SFX_DB}dB,alimiter=limit=0.2:attack=1:release=80:level=disabled[s];[1:a]volume={MUSIC_DB}dB[m];"
    f"[s][m]amix=inputs=2:normalize=0[b];[2:a]asplit=2[sc][vv];[b][sc]{duck}[bgd];[vv]anullsink", "-map", "[bgd]", "work/bg_ducked.wav"])
ff(["-i", "work/sfx_raw.wav", "-i", "work/voice.wav", "-filter_complex",
    f"[0:a]volume={SFX_DB}dB,alimiter=limit=0.2:attack=1:release=80:level=disabled[s];[1:a]asplit=2[sc][vv];[s][sc]{duck}[o];[vv]anullsink",
    "-map", "[o]", "work/sfx_ducked.wav"])
(V / "assets").mkdir(exist_ok=True)
ff(["-i", "work/voice.wav", "-i", "work/bg_ducked.wav", "-filter_complex",
    "[0:a][1:a]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.76:attack=3:release=60:level=disabled[m]",
    "-map", "[m]", "-ar", "48000", "-t", str(D), "assets/mix.wav"])


def meas(f):
    o = subprocess.run(["ffmpeg", "-nostdin", "-i", f, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, cwd=V).stderr
    return re.findall(r"I:\s+(-?[\d.]+) LUFS", o)[-1], re.findall(r"Peak:\s+(-?[\d.inf]+) dBFS", o)[-1]


for f in ["work/voice.wav", "work/sfx_ducked.wav", "work/music_raw.wav", "assets/mix.wav"]:
    i, p = meas(f); print(f"{f:22s} {i:>6} LUFS  true peak {p} dBFS")
