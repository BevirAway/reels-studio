#!/usr/bin/env python3
"""Голос рілса: «студійно» — Resemble Enhance (модуль «Чистка голосу») → highpass 70 Гц → loudnorm у два проходи до
−13 LUFS, TP −1. БЕЗ компресора (звучить «стиснуто»). Модуль вимкнено — лише highpass + loudnorm.
  voice.py <сирий голос нарізки.wav> <вихід.wav> [--plain]
--plain — без Resemble (якщо після чистки зникли слова: багато голосів, сміх, музика поверх мови).
Resemble ~1 хв на хвилину звуку на M-чипі. Після обробки — перевірити розшифровкою (stt.py), що слова на місці."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path
S = Path.home() / ".studio"
os.environ["PATH"] = f"{S / 'bin'}:{os.environ.get('PATH', '')}"
TPY, MODEL = S / "venvs/torch/bin/python", S / "models/resemble/enhancer_stage2"
RUN = r'''
import sys, torch, soundfile as sf
from pathlib import Path
import resemble_enhance.enhancer.inference as inf
inf.download = lambda: Path(sys.argv[3])
x, sr = sf.read(sys.argv[1], dtype="float32")
x = x.mean(1) if x.ndim > 1 else x
e, esr = inf.enhance(torch.from_numpy(x), sr, "cpu", nfe=32, solver="midpoint", lambd=0.9, tau=0.5)
sf.write(sys.argv[2], e.cpu().numpy(), esr)
'''
args = [a for a in sys.argv[1:] if not a.startswith("--")]
src, out = Path(args[0]), Path(args[1])
plain = "--plain" in sys.argv or not (TPY.exists() and MODEL.exists())
with tempfile.TemporaryDirectory() as td:
    enh = Path(td) / "enh.wav"
    if plain:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", str(enh)], check=True)
    else:
        subprocess.run([str(TPY), "-c", RUN, str(src), str(enh), str(MODEL)], check=True, stderr=subprocess.DEVNULL)
    pre = "highpass=f=70"
    o = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(enh), "-af", f"{pre},loudnorm=I=-13:TP=-1:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(o[o.rindex("{"):o.rindex("}") + 1])
    ln = (f"loudnorm=I=-13:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(enh), "-af", f"{pre},{ln}", "-ar", "48000", "-ac", "2", str(out)],
                   check=True)
o = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
print(out, re.findall(r"I:\s+(-?[\d.]+) LUFS", o)[-1], "LUFS", "(без Resemble)" if plain else "(Resemble)")
