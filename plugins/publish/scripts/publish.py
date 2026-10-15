#!/usr/bin/env python3
"""Публікація студії: Instagram (Instagram API з Instagram Login) і Telegram-канал, зараз або за розкладом.

  publish.py setup-ig                       перевірити IG_TOKEN, зберегти IG_USER_ID і нік
  publish.py setup-tg                       перевірити бота й канал (TG_BOT_TOKEN, TG_CHANNEL), бот — адмін каналу
  publish.py add --when "2026-10-20 18:00" --to ig,tg --files Готово/x.mp4 [--files …] --text Публікації/x.md [--cover img]
                                            додати в чергу (ЛИШЕ після «так» власниці на цей текст і файли)
  publish.py now <id>                       опублікувати запис черги зараз
  publish.py list                           черга й історія
  publish.py cancel <id>                    зняти з черги
  publish.py tick                           опублікувати все, чому настав час (раз на 5 хв — launchd)
  publish.py schedule-on | schedule-off     увімкнути/вимкнути перевірку черги кожні 5 хв

Тексти: файл .md з блоками «## INSTAGRAM» і «## TELEGRAM» (без блоку — весь файл для всіх).
Файли для Instagram тимчасово кладуться на litterbox.catbox.moe (1 год) — Instagram бере відео лише за посиланням.
Черга — Публікації/черга.json. Після публікації — сповіщення на Mac.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

S = Path.home() / ".studio"
os.environ["PATH"] = f"{S / 'bin'}:{os.environ.get('PATH', '')}"
IG = "https://graph.instagram.com/v25.0"
PLIST = Path.home() / "Library/LaunchAgents/com.studio.publish.plist"


# ------------------------------------------------------------------ дані
def keys():
    out = {}
    try:
        for line in (S / "keys.env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def set_key(name, value):
    subprocess.run([str(S / "bin/studio"), "key", "set", name, value], capture_output=True)


def workspace():
    try:
        return Path(json.loads((S / "config.json").read_text())["workspace"])
    except Exception:
        return Path.home() / "Студія"


QUEUE = workspace() / "Публікації" / "черга.json"


def load_q():
    try:
        return json.loads(QUEUE.read_text())
    except (OSError, ValueError):
        return []


def save_q(q):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1))


def notify(title, text):
    subprocess.run(["osascript", "-e", f'display notification {json.dumps(text)} with title {json.dumps(title)}'],
                   capture_output=True)


def texts(path):
    s = Path(path).read_text()
    blocks = dict(re.findall(r"^##\s*(INSTAGRAM|TELEGRAM)\s*\n(.*?)(?=^##\s|\Z)", s, flags=re.M | re.S))
    return {"ig": (blocks.get("INSTAGRAM") or s).strip(), "tg": (blocks.get("TELEGRAM") or blocks.get("INSTAGRAM") or s).strip()}


# ------------------------------------------------------------------ http
def http(url, data=None, method=None, files=None, timeout=120):
    if files:
        boundary = "----studio" + str(int(time.time() * 1000))
        body = b""
        for k, v in (data or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, p in files.items():
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{Path(p).name}"\r\n'
                     f'Content-Type: application/octet-stream\r\n\r\n').encode() + Path(p).read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        enc = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=enc, method=method or ("POST" if enc else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode('utf8', 'ignore')}")
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf8", "ignore").strip()


def host_temp(path):
    """Тимчасове публічне посилання (1 год) — Instagram завантажує медіа сам за URL."""
    url = http("https://litterbox.catbox.moe/resources/internals/api.php",
               {"reqtype": "fileupload", "time": "1h"}, files={"fileToUpload": path}, timeout=600)
    if not str(url).startswith("http"):
        raise RuntimeError(f"тимчасовий хостинг не прийняв файл: {url}")
    return url


# ------------------------------------------------------------------ Instagram
def ig_wait(cid, token, tries=40):
    for _ in range(tries):
        st = http(f"{IG}/{cid}?fields=status_code,status&access_token={token}")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram не обробив файл: {st.get('status')}")
        time.sleep(15)
    raise RuntimeError("Instagram обробляє файл занадто довго")


def ig_refresh(k):
    """Довгий токен живе 60 днів; оновлюємо, якщо старший за 30 днів."""
    try:
        at = float(k.get("IG_TOKEN_AT") or 0)
        if time.time() - at > 30 * 86400:
            r = http(f"https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={k['IG_TOKEN']}")
            if r.get("access_token"):
                set_key("IG_TOKEN", r["access_token"]); set_key("IG_TOKEN_AT", str(int(time.time())))
                k["IG_TOKEN"] = r["access_token"]
    except Exception as e:
        print("! не вдалося оновити токен Instagram:", e)


def publish_ig(files, caption, cover=None):
    k = keys()
    if not k.get("IG_TOKEN") or not k.get("IG_USER_ID"):
        raise RuntimeError("Instagram не підключено (IG_TOKEN, IG_USER_ID) — навичка publish:setup")
    ig_refresh(k)
    tok, uid = k["IG_TOKEN"], k["IG_USER_ID"]
    vids = [f for f in files if Path(f).suffix.lower() in (".mp4", ".mov")]
    if len(files) == 1 and vids:
        d = {"media_type": "REELS", "video_url": host_temp(files[0]), "caption": caption, "share_to_feed": "true",
             "access_token": tok}
        if cover:
            d["cover_url"] = host_temp(cover)
        cid = http(f"{IG}/{uid}/media", d)["id"]
    elif len(files) == 1:
        cid = http(f"{IG}/{uid}/media", {"image_url": host_temp(files[0]), "caption": caption, "access_token": tok})["id"]
    else:
        kids = []
        for f in files[:10]:
            isv = Path(f).suffix.lower() in (".mp4", ".mov")
            d = {"is_carousel_item": "true", "access_token": tok,
                 **({"media_type": "VIDEO", "video_url": host_temp(f)} if isv else {"image_url": host_temp(f)})}
            c = http(f"{IG}/{uid}/media", d)["id"]
            if isv:
                ig_wait(c, tok)
            kids.append(c)
        cid = http(f"{IG}/{uid}/media", {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption,
                                          "access_token": tok})["id"]
    ig_wait(cid, tok)
    mid = http(f"{IG}/{uid}/media_publish", {"creation_id": cid, "access_token": tok})["id"]
    link = http(f"{IG}/{mid}?fields=permalink&access_token={tok}").get("permalink", "")
    return link or mid


# ------------------------------------------------------------------ Telegram
def publish_tg(files, caption):
    k = keys()
    tok, ch = k.get("TG_BOT_TOKEN"), k.get("TG_CHANNEL")
    if not tok or not ch:
        raise RuntimeError("Telegram не підключено (TG_BOT_TOKEN, TG_CHANNEL) — навичка publish:setup")
    api = f"https://api.telegram.org/bot{tok}"
    cap = caption[:1024]
    if not files:
        r = http(f"{api}/sendMessage", {"chat_id": ch, "text": caption[:4096]})
    elif len(files) == 1:
        f = files[0]
        isv = Path(f).suffix.lower() in (".mp4", ".mov")
        if Path(f).stat().st_size > 49 * 1024 * 1024:
            raise RuntimeError("файл більший за 50 МБ — зробіть копію для телефону (phone_copy.sh)")
        r = http(f"{api}/{'sendVideo' if isv else 'sendPhoto'}", {"chat_id": ch, "caption": cap,
                 **({"supports_streaming": "true"} if isv else {})}, files={"video" if isv else "photo": f}, timeout=600)
    else:
        media, fl = [], {}
        for i, f in enumerate(files[:10]):
            isv = Path(f).suffix.lower() in (".mp4", ".mov")
            media.append({"type": "video" if isv else "photo", "media": f"attach://f{i}", **({"caption": cap} if i == 0 else {})})
            fl[f"f{i}"] = f
        r = http(f"{api}/sendMediaGroup", {"chat_id": ch, "media": json.dumps(media)}, files=fl, timeout=600)
    if not (isinstance(r, dict) and r.get("ok")):
        raise RuntimeError(f"Telegram: {r}")
    res = r["result"][0] if isinstance(r["result"], list) else r["result"]
    un = res.get("chat", {}).get("username")
    return f"https://t.me/{un}/{res['message_id']}" if un else f"повідомлення {res['message_id']}"


# ------------------------------------------------------------------ черга
def run_item(it):
    ws = workspace()
    files = [str(ws / f) if not Path(f).is_absolute() else f for f in it["files"]]
    tx = texts(ws / it["text"] if not Path(it["text"]).is_absolute() else it["text"]) if it.get("text") else {"ig": "", "tg": ""}
    it.setdefault("result", {})
    for p in it["to"]:
        if it["result"].get(p, {}).get("ok"):
            continue                                    # уже вийшло — не дублювати
        try:
            link = publish_ig(files, tx["ig"], it.get("cover")) if p == "ig" else publish_tg(files, tx["tg"])
            it["result"][p] = {"ok": True, "link": link, "at": datetime.now().isoformat(timespec="minutes")}
        except Exception as e:
            it["result"][p] = {"ok": False, "error": str(e)[:300], "at": datetime.now().isoformat(timespec="minutes")}
    ok = all(it["result"].get(p, {}).get("ok") for p in it["to"])
    it["status"] = "done" if ok else "failed"
    name = Path(it["files"][0]).stem if it["files"] else it["id"]
    notify("Студія", f"Опубліковано: {name}" if ok else f"Не вийшло опублікувати {name} — спитайте Claude")
    return it


def cmd_add(a):
    q = load_q()
    when = datetime.strptime(a.when, "%Y-%m-%d %H:%M") if a.when != "now" else datetime.now()
    it = {"id": datetime.now().strftime("%m%d-%H%M%S"), "when": when.isoformat(timespec="minutes"), "to": a.to.split(","),
          "files": a.files, "text": a.text, "cover": a.cover, "status": "queued",
          "approved_at": datetime.now().isoformat(timespec="minutes")}
    q.append(it); save_q(q)
    print(f"✓ у черзі {it['id']}: {it['when']} → {', '.join(it['to'])}")
    if not PLIST.exists() and a.when != "now":
        print("! розклад вимкнено — publish.py schedule-on, інакше опублікується лише вручну")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("setup-ig", "setup-tg", "list", "tick", "schedule-on", "schedule-off"):
        sp.add_parser(c)
    ad = sp.add_parser("add")
    ad.add_argument("--when", required=True); ad.add_argument("--to", required=True)
    ad.add_argument("--files", nargs="+", default=[]); ad.add_argument("--text"); ad.add_argument("--cover")
    for c in ("now", "cancel"):
        sp.add_parser(c).add_argument("id")
    a = ap.parse_args()

    if a.cmd == "setup-ig":
        k = keys()
        me = http(f"https://graph.instagram.com/me?fields=user_id,username,account_type&access_token={k.get('IG_TOKEN', '')}")
        set_key("IG_USER_ID", str(me["user_id"])); set_key("IG_TOKEN_AT", str(int(time.time())))
        print(f"✓ Instagram @{me.get('username')} ({me.get('account_type')}), ID збережено")
    elif a.cmd == "setup-tg":
        k = keys()
        me = http(f"https://api.telegram.org/bot{k.get('TG_BOT_TOKEN', '')}/getMe")["result"]
        ch = http(f"https://api.telegram.org/bot{k.get('TG_BOT_TOKEN', '')}/getChat?chat_id={urllib.parse.quote(k.get('TG_CHANNEL', ''))}")["result"]
        adm = http(f"https://api.telegram.org/bot{k.get('TG_BOT_TOKEN', '')}/getChatAdministrators?chat_id={ch['id']}")["result"]
        ok = any(x["user"]["id"] == me["id"] and x.get("can_post_messages", True) for x in adm)
        print(f"✓ бот @{me['username']}, канал «{ch.get('title')}»" + ("" if ok else " — ! бот не адмін каналу або не може писати"))
    elif a.cmd == "add":
        cmd_add(a)
    elif a.cmd == "list":
        for it in load_q()[-30:]:
            res = " ".join(f"{p}:{'✓ ' + r.get('link', '') if r.get('ok') else '✗ ' + r.get('error', '')[:60]}"
                           for p, r in it.get("result", {}).items())
            print(f"{it['id']}  {it['when']}  {it['status']:<7} {','.join(it['to']):<6} {Path(it['files'][0]).name if it['files'] else ''}  {res}")
    elif a.cmd in ("now", "cancel"):
        q = load_q()
        it = next((x for x in q if x["id"] == a.id), None)
        if not it:
            sys.exit("немає такого запису")
        if a.cmd == "cancel":
            it["status"] = "cancelled"
        else:
            run_item(it)
            print(json.dumps(it["result"], ensure_ascii=False, indent=1))
        save_q(q)
    elif a.cmd == "tick":
        q, now = load_q(), datetime.now()
        for it in q:
            if it["status"] == "queued" and it.get("approved_at") and datetime.fromisoformat(it["when"]) <= now:
                it["status"] = "running"; save_q(q)        # не запускати двічі, якщо tick накладеться
                run_item(it); save_q(q)
    elif a.cmd == "schedule-on":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.studio.publish</string>
<key>ProgramArguments</key><array><string>{S / 'venvs/base/bin/python'}</string><string>{S / 'repo/plugins/publish/scripts/publish.py'}</string><string>tick</string></array>
<key>StartInterval</key><integer>300</integer>
<key>StandardOutPath</key><string>{S / 'publish.log'}</string><key>StandardErrorPath</key><string>{S / 'publish.log'}</string>
</dict></plist>""")
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        subprocess.run(["launchctl", "load", str(PLIST)], check=True)
        print("✓ розклад увімкнено: черга перевіряється кожні 5 хв (Mac має бути увімкнений)")
    elif a.cmd == "schedule-off":
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink(missing_ok=True)
        print("✓ розклад вимкнено")


if __name__ == "__main__":
    main()
