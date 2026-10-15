#!/usr/bin/env python3
"""HTML-слайди → PNG тим самим браузером, що рендерить рілси (hyperframes).
  render_slides.py <папка з 01.html 02.html …> [--size 1080x1350]   → 01.png 02.png … поруч
  render_slides.py <файл.html> [--size 1080x1920]                    → файл.png"""
import argparse, os, subprocess, sys
from pathlib import Path
S = Path.home() / ".studio"
os.environ["PATH"] = f"{S / 'bin'}:{S / 'node/bin'}:{os.environ.get('PATH', '')}"
ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("--size", default="1080x1350")
a = ap.parse_args()
w, h = a.size.lower().split("x")
chrome = subprocess.run(["hyperframes", "browser", "path"], capture_output=True, text=True).stdout.strip().splitlines()
chrome = chrome[-1] if chrome else ""
if not chrome or not Path(chrome).exists():
    sys.exit("Немає браузера для рендеру: hyperframes browser ensure (модуль «Монтаж рілсів»)")
src = Path(a.src)
pages = sorted(src.glob("*.html")) if src.is_dir() else [src]
for p in pages:
    out = p.with_suffix(".png")
    subprocess.run([chrome, "--headless", "--hide-scrollbars", "--force-device-scale-factor=1", f"--window-size={w},{h}",
                    "--virtual-time-budget=3000", f"--screenshot={out}",
                    p.resolve().as_uri()], capture_output=True, check=False)
    print(("✓ " if out.exists() else "✗ ") + str(out))
