#!/usr/bin/env python3
"""Звуки студії: пошук на Freesound (CC0, без ключа), завантаження в `Бібліотека/Звуки` робочої папки, генерація
в ElevenLabs — лише запасний шлях, якщо на Freesound немає потрібного або не подобається (ключ ELEVENLABS_API_KEY).
Спершу шукати у своїй бібліотеці (`lib` показує першими звуки куплених паків, напр. Old Sport), потім на Freesound.
Послухати їй — `open <файл>`.

  sfx.py lib [запит] [--cat whoosh]              що вже є
  sfx.py search "apple crunch" [--min 0.1] [--max 3] [-n 8]
  sfx.py get freesound:12345 freesound:67890 --cat apple [--tags "fruit,bite"]
  sfx.py fetch "door creak" --cat door -n 3 [--min …] [--max …]   знайти й завантажити найкращі
  sfx.py gen "apple dropped into a wooden crate" --cat apple --dur 1.2 [-n 2]   запасний шлях: ElevenLabs
  sfx.py audit [--cat …]                           переміряти пік, гучність
  sfx.py add-dir <папка пака> --src oldsport        додати готовий пак звуків (копія + заміри)

Категорії — будь-які слова (whoosh, click, paper, nature, apple, music …). Запит — англійською.
"""
import argparse
import os
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

S = Path.home() / ".studio"
os.environ["PATH"] = f"{S / 'bin'}:{os.environ.get('PATH', '')}"


def _workspace():
    try:
        return Path(json.loads((S / "config.json").read_text())["workspace"])
    except Exception:
        return Path.home() / "Студія"


LIB = _workspace() / "Бібліотека" / "Звуки"
INDEX = LIB / "library.json"
CACHE = LIB / ".search_cache.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36"}


def _load(p, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def _slug(s, n=40):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "sfx"


def _get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


# ---------- источники ----------

def search_freesound(q, dmin, dmax, n):
    url = "https://freesound.org/search/?" + urllib.parse.urlencode(
        {"q": q, "f": 'license:"Creative Commons 0"', "s": "Downloads (most first)"})
    h = _get(url, 30).decode("utf8", "ignore")
    rows = re.findall(r'data-sound-id="(\d+)"\s+data-username="([^"]+)".*?data-mp3="([^"]+)".*?'
                      r'data-title="([^"]*)"\s+data-duration="([\d.]+)".*?data-num-downloads="(\d+)"', h, re.S)
    out = []
    for sid, user, mp3, title, dur, dl in rows:
        dur = float(dur)
        if not dmin <= dur <= dmax:
            continue
        out.append(dict(id=f"freesound:{sid}", title=title, author=user, duration=round(dur, 2), downloads=int(dl),
                        audio=mp3.replace("-lq.mp3", "-hq.mp3"), license="CC0",
                        page=f"https://freesound.org/people/{user}/sounds/{sid}/"))
        if len(out) >= n:
            break
    return out


SOURCES = {"freesound": search_freesound}


def search(q, srcs, dmin, dmax, n):
    res = []
    for s in srcs:
        res += SOURCES[s](q, dmin, dmax, n)
    cache = _load(CACHE, {})
    for r in res:
        cache[r["id"]] = r
    _save(CACHE, cache)
    return res


# ---------- библиотека ----------

def measure(path):
    """Пик (dBFS), громкость (LUFS), длительность, тишина в начале (с)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "silencedetect=n=-45dB:d=0.02,ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    peak = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", p)
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", p)
    lead = 0.0
    m = re.search(r"silence_start: (-?[\d.]+)\s.*?silence_end: ([\d.]+)", p, re.S)
    if m and float(m.group(1)) <= 0.01:
        lead = float(m.group(2))
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True).stdout.strip()
    return dict(peak_db=float(peak[-1]) if peak and peak[-1] != "-inf" else None,
                lufs=float(lufs[-1]) if lufs else None, duration=round(float(d or 0), 3), lead_silence=round(lead, 3))


def get(ids, cat, tags):
    cache, index = _load(CACHE, {}), _load(INDEX, [])
    have = {e["id"] for e in index}
    for sid in ids:
        if sid in have:
            print(f"уже есть: {sid}")
            continue
        r = cache.get(sid)
        if not r:
            print(f"нет в последних результатах поиска: {sid} — сначала search", file=sys.stderr)
            continue
        dst = LIB / _slug(cat, 20) / f"{sid.replace(':', '_')}_{_slug(r['title'])}.mp3"
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = dst.with_suffix(".raw.mp3")
        raw.write_bytes(_get(r["audio"]))
        lead = measure(raw)["lead_silence"]
        if lead > 0.03:  # тишину в начале срезаем, чтобы звук стоял ровно на кадре события
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{lead - 0.01:.3f}", "-i", str(raw), "-c:a",
                            "libmp3lame", "-q:a", "2", str(dst)], check=True)
            raw.unlink()
        else:
            raw.rename(dst)
        e = dict(r, file=str(dst.relative_to(LIB)), category=cat, tags=[t for t in tags.split(",") if t],
                 **{k: v for k, v in measure(dst).items() if k != "lead_silence"})
        e.pop("audio", None)
        index.append(e)
        have.add(sid)
        print(f"+ {e['file']}  {e['duration']} с, пик {e['peak_db']} dBFS, {e['lufs']} LUFS")
    _save(INDEX, index)


def _eleven_key():
    try:
        for line in (S / "keys.env").read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    sys.exit("Немає ключа ElevenLabs — studio key set ELEVENLABS_API_KEY (або «Налаштування студії»)")


def gen(prompt, cat, dur, n, tags):
    """Згенерувати звук в ElevenLabs (запасний шлях) і покласти в бібліотеку, як завантажений."""
    import hashlib
    key, index = _eleven_key(), _load(INDEX, [])
    for k in range(n):
        body = json.dumps({"text": prompt, "duration_seconds": dur, "prompt_influence": 0.5}).encode()
        req = urllib.request.Request("https://api.elevenlabs.io/v1/sound-generation", data=body, method="POST",
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
        audio = urllib.request.urlopen(req, timeout=120).read()
        sid = "elevenlabs:" + hashlib.sha1(audio).hexdigest()[:10]
        dst = LIB / _slug(cat, 20) / f"{sid.replace(':', '_')}_{_slug(prompt)}.mp3"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(audio)
        e = dict(id=sid, title=prompt, author="ElevenLabs (генерация)", license="ElevenLabs", query=prompt,
                 file=str(dst.relative_to(LIB)), category=cat, tags=["generated"] + [t for t in tags.split(",") if t],
                 **{k2: v for k2, v in measure(dst).items() if k2 != "lead_silence"})
        index.append(e)
        print(f"+ {e['file']}  {e['duration']} с, пик {e['peak_db']} dBFS, {e['lufs']} LUFS")
    _save(INDEX, index)


AUDIO = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aif", ".aiff"}


def add_dir(src_dir, src, cat_prefix, tags, skip):
    """Додати готовий пак звуків: файли копіюються в `<src>/<категорія>/…`, категорія — верхня папка пака (якщо в ній
    лише підпапки — наступна: Games/GTA → games-gta), теги — слова шляху. Повторний запуск додає тільки нове."""
    from concurrent.futures import ThreadPoolExecutor
    import shutil
    root, index = Path(src_dir).expanduser(), _load(INDEX, [])
    have = {e["id"] for e in index}
    todo = []
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root)
        if f.suffix.lower() not in AUDIO or any(x and x.lower() in str(rel).lower() for x in skip):
            continue
        sid = f"{src}:{rel}"
        if sid in have:
            continue
        parts = rel.parts[:-1] or ("misc",)
        top = root / parts[0]
        depth = 1 if any(c.is_file() and c.suffix.lower() in AUDIO for c in top.iterdir()) or len(parts) < 2 else 2
        cat = cat_prefix + _slug("-".join(parts[:depth]), 30)
        sub = "__".join(_slug(x, 30) for x in parts[depth:])
        dst = LIB / src / cat / sub / (_slug(f.stem, 60) + f.suffix.lower())
        todo.append((f, sid, cat, dst, rel))

    def one(t):
        f, sid, cat, dst, rel = t
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        words = [w for x in rel.parts[:-1] for w in _slug(x).split("-") if w]
        return dict(id=sid, title=f.stem, author=src, license=src, file=str(dst.relative_to(LIB)), category=cat,
                    tags=sorted(set(words + [t for t in tags.split(",") if t])), **measure(dst))

    with ThreadPoolExecutor(8) as ex:
        for k, e in enumerate(ex.map(one, todo), 1):
            index.append(e)
            if k % 200 == 0:
                _save(INDEX, index)
                print(f"… {k}/{len(todo)}", flush=True)
    _save(INDEX, index)
    print(f"+ {len(todo)} файлів з {root.name} → {LIB / src}")


RANK = {"starter": 1, "freesound": 1, "elevenlabs": 2}  # спершу куплені паки, потім Freesound, генерація остання


def lib(q, cat):
    words = (q or "").lower().split()
    rows = []
    for e in _load(INDEX, []):
        hay = " ".join([e["title"], e["category"], e["file"], " ".join(e.get("tags", [])), e.get("query", "")]).lower()
        if (not cat or e["category"] == cat or e["category"].startswith(cat + "-")) and all(w in hay for w in words):
            rows.append(e)
    rows.sort(key=lambda e: RANK.get(e["id"].split(":")[0], 0))
    for e in rows:
        print(f"{e['file']:<70} {e['duration']:>6} с  пік {e['peak_db']}  {e['id']} — {e['author']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("search", "fetch"):
        s = sp.add_parser(name)
        s.add_argument("query")
        s.add_argument("--src", default="freesound")
        s.add_argument("--min", type=float, default=0.05)
        s.add_argument("--max", type=float, default=4.0)
        s.add_argument("-n", type=int, default=8 if name == "search" else 3)
        if name == "fetch":
            s.add_argument("--cat", required=True)
            s.add_argument("--tags", default="")
    g = sp.add_parser("get")
    g.add_argument("ids", nargs="+")
    g.add_argument("--cat", required=True)
    g.add_argument("--tags", default="")
    l = sp.add_parser("lib")
    l.add_argument("query", nargs="?")
    l.add_argument("--cat")
    a = sp.add_parser("audit")
    a.add_argument("--cat")
    ge = sp.add_parser("gen")
    ge.add_argument("prompt")
    ge.add_argument("--cat", required=True)
    ge.add_argument("--dur", type=float, default=1.5)
    ge.add_argument("-n", type=int, default=1)
    ge.add_argument("--tags", default="")
    ad = sp.add_parser("add-dir")
    ad.add_argument("dir")
    ad.add_argument("--src", required=True)
    ad.add_argument("--cat-prefix", default="")
    ad.add_argument("--tags", default="")
    ad.add_argument("--skip", action="append", default=[])
    args = ap.parse_args()

    if args.cmd in ("search", "fetch"):
        srcs = [s for s in args.src.split(",") if s in SOURCES]
        res = search(args.query, srcs, args.min, args.max, args.n)
        if args.cmd == "search":
            for r in res:
                dl = f"{r['downloads']} скач." if r["downloads"] is not None else ""
                print(f"{r['id']:<18} {str(r['duration']):>6} с  {dl:<12} {r['title'][:50]}  — {r['author']}")
        else:
            ids = []
            for s in srcs:  # поровну с каждого источника, лучшие первыми
                ids += [r["id"] for r in res if r["id"].startswith(s)][: max(1, args.n // len(srcs))]
            get(ids[: args.n], args.cat, ",".join(filter(None, [args.tags, args.query.replace(" ", "-")])))
    elif args.cmd == "get":
        get(args.ids, args.cat, args.tags)
    elif args.cmd == "lib":
        lib(args.query, args.cat)
    elif args.cmd == "add-dir":
        add_dir(args.dir, args.src, args.cat_prefix, args.tags, args.skip)
    elif args.cmd == "gen":
        gen(args.prompt, args.cat, args.dur, args.n, args.tags)
    elif args.cmd == "audit":
        index = _load(INDEX, [])
        for e in index:
            if not args.cat or e["category"] == args.cat:
                e.update({k: v for k, v in measure(LIB / e["file"]).items() if k != "lead_silence"})
                print(f"{e['file']:<70} пик {e['peak_db']}  {e['lufs']} LUFS")
        _save(INDEX, index)


if __name__ == "__main__":
    main()
