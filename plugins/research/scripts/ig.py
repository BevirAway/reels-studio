#!/usr/bin/env python3
"""Instagram через Apify (ключ APIFY_TOKEN у ~/.studio/keys.env). Платно за кожен результат — малими порціями.

  ig.py posts <нік> [-n 30] [--media]   пости профілю (фото, каруселі, відео) → Бібліотека/Instagram/<нік>/posts.json
  ig.py reels <нік> [-n 20] [--media]   рілси профілю з переглядами → …/reels.json
  ig.py top <нік> [-n 10]               найкращі з уже завантаженого (перегляди, лайки, коментарі)
--media — завантажити й самі картинки/відео (для стилю, кольорів, шрифтів, перемонтажу).
"""
import argparse, json, os, re, sys, urllib.request
from datetime import datetime
from pathlib import Path

S = Path.home() / ".studio"


def key(name):
    try:
        for line in (S / "keys.env").read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    sys.exit("Немає ключа Apify — «Налаштування студії» або: studio key set APIFY_TOKEN")


def workspace():
    try:
        return Path(json.loads((S / "config.json").read_text())["workspace"])
    except Exception:
        return Path.home() / "Студія"


def actor(name, payload, timeout=600):
    url = f"https://api.apify.com/v2/acts/{name}/run-sync-get-dataset-items?token={key('APIFY_TOKEN')}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def norm(it):
    ts = it.get("timestamp") or ""
    return {"date": ts[:10], "type": it.get("productType") or it.get("type") or "", "url": it.get("url"),
            "shortcode": it.get("shortCode") or it.get("shortcode"), "caption": it.get("caption") or "",
            "likes": it.get("likesCount"), "comments": it.get("commentsCount"),
            "views": it.get("videoPlayCount") or it.get("videoViewCount") or it.get("playsCount"),
            "image": it.get("displayUrl"), "images": it.get("images") or [], "video": it.get("videoUrl"),
            "duration": it.get("videoDuration")}


def save_media(rows, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for r in rows:
        base = f"{r['date']}_{r['shortcode']}"
        urls = ([("mp4", r["video"])] if r.get("video") else []) + \
               [("jpg", u) for u in ([r["image"]] if r.get("image") else []) + r.get("images", [])[1:]]
        for i, (ext, u) in enumerate(urls):
            dst = folder / (f"{base}.{ext}" if i == 0 else f"{base}_{i}.{ext}")
            if dst.exists():
                continue
            try:
                urllib.request.urlretrieve(u, dst)
            except Exception as e:
                print(f"  ! {dst.name}: {e.__class__.__name__}")


def show(rows, n=None):
    for r in rows[:n]:
        v = f"{r['views']:>7}" if r.get("views") else "      ·"
        cap = re.sub(r"\s+", " ", r["caption"])[:70]
        print(f"{r['date']}  {r['type'][:6]:<6} {v} перегл. {r.get('likes') or 0:>5} ♥ {r.get('comments') or 0:>4} 💬  {cap}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["posts", "reels", "top"])
    ap.add_argument("user")
    ap.add_argument("-n", type=int, default=None)
    ap.add_argument("--media", action="store_true")
    a = ap.parse_args()
    user = a.user.lstrip("@").strip("/").split("/")[-1]
    folder = workspace() / "Бібліотека" / "Instagram" / user
    folder.mkdir(parents=True, exist_ok=True)
    if a.cmd == "posts":
        items = actor("apify~instagram-scraper", {"directUrls": [f"https://www.instagram.com/{user}/"],
                                                   "resultsType": "posts", "resultsLimit": a.n or 30})
        rows = [norm(i) for i in items if not i.get("error")]
    elif a.cmd == "reels":
        items = actor("apify~instagram-reel-scraper", {"username": [user], "resultsLimit": a.n or 20})
        rows = [norm(i) for i in items if not i.get("error")]
    else:
        rows = []
        for f in ("posts.json", "reels.json"):
            p = folder / f
            if p.exists():
                rows += json.loads(p.read_text())
        seen, uniq = set(), []
        for r in rows:
            if r["shortcode"] not in seen:
                seen.add(r["shortcode"]); uniq.append(r)
        uniq.sort(key=lambda r: (r.get("views") or 0, r.get("likes") or 0), reverse=True)
        show(uniq, a.n or 10)
        return
    (folder / f"{a.cmd}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"{len(rows)} шт. → {folder / (a.cmd + '.json')}  ({datetime.now():%H:%M})")
    show(rows, 15)
    if a.media:
        save_media(rows, folder / "media")
        print("медіа →", folder / "media")


if __name__ == "__main__":
    main()
