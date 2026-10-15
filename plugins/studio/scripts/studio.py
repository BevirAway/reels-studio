#!/usr/bin/env python3
"""Студія — налаштування на Mac: модулі, ключі, перевірка. Запуск: ~/.studio/bin/studio <команда>.

  studio status [--json]            що увімкнено, які ключі є, чи все встановлено
  studio module list                модулі й стан
  studio module on|off <модуль>     увімкнути (докачати потрібне) / вимкнути модуль
  studio key list                   які ключі збережено (значення приховані)
  studio key set <NAME> [значення]  зберегти ключ (без значення — читає зі stdin)
  studio key get <NAME>             надрукувати ключ (для скриптів)
  studio key del <NAME>             видалити ключ
  studio key test [NAME]            перевірити ключі запитом до сервісу
  studio doctor                     перевірити програми, моделі, модулі
  studio paths [--json]             де лежать робоча папка, бібліотеки, програми
  studio update                     оновити студію з GitHub

Дані: ~/.studio/config.json (модулі, робоча папка), ~/.studio/keys.env (ключі, лише для власника файлу).
"""
import json, os, shutil, subprocess, sys, urllib.request
from pathlib import Path

S = Path.home() / ".studio"
CONFIG, KEYS = S / "config.json", S / "keys.env"
REPO = S / "repo"
MARKET = "reels-studio"

MODULES = {
    "studio":   ("Студія — основа", []),
    "montage":  ("Монтаж рілсів", ["ELEVENLABS_API_KEY?"]),
    "voice":    ("Чистка голосу", []),
    "upscale":  ("Покращення якості відео", []),
    "sounds":   ("Звуки", ["ELEVENLABS_API_KEY?"]),
    "texts":    ("Тексти й каруселі", []),
    "research": ("Дослідження Instagram", ["APIFY_TOKEN"]),
    "publish":  ("Публікація", ["IG_TOKEN?", "TG_BOT_TOKEN?"]),
}
KEY_INFO = {
    "ELEVENLABS_API_KEY": "ElevenLabs — розпізнавання мови і генерація звуків",
    "APIFY_TOKEN": "Apify — завантаження постів Instagram",
    "IG_TOKEN": "Instagram — публікація (довгий токен)",
    "IG_USER_ID": "Instagram — ID акаунта",
    "TG_BOT_TOKEN": "Telegram — бот для каналу",
    "TG_CHANNEL": "Telegram — канал (@назва або -100…)",
}


# ------------------------------------------------------------------ дані
def config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {"modules": {"studio": True}}


def save_config(c: dict) -> None:
    S.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(c, ensure_ascii=False, indent=2))


def keys() -> dict:
    out = {}
    try:
        for line in KEYS.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def save_keys(d: dict) -> None:
    S.mkdir(exist_ok=True)
    KEYS.touch(mode=0o600, exist_ok=True)
    os.chmod(KEYS, 0o600)
    KEYS.write_text("".join(f"{k}={v}\n" for k, v in sorted(d.items()) if v))


def key(name: str) -> str:
    """Для інших скриптів: from studio import key."""
    return os.environ.get(name) or keys().get(name, "")


def workspace() -> Path:
    return Path(config().get("workspace") or Path.home() / "Студія")


def mask(v: str) -> str:
    return (v[:4] + "…" + v[-3:]) if len(v) > 10 else "…"


def claude_bin() -> str | None:
    for c in [shutil.which("claude"), str(Path.home() / ".local/bin/claude"), "/usr/local/bin/claude",
              "/opt/homebrew/bin/claude"]:
        if c and Path(c).exists():
            return c
    return None


# ------------------------------------------------------------------ перевірки ключів
def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def test_key(name: str, v: str) -> tuple[bool, str]:
    try:
        if name == "ELEVENLABS_API_KEY":
            _get("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": v})
        elif name == "APIFY_TOKEN":
            _get("https://api.apify.com/v2/users/me?token=" + v)
        elif name == "IG_TOKEN":
            _, b = _get("https://graph.instagram.com/me?fields=user_id,username&access_token=" + v)
            return True, "акаунт @" + json.loads(b).get("username", "?")
        elif name == "TG_BOT_TOKEN":
            _, b = _get(f"https://api.telegram.org/bot{v}/getMe")
            return True, "бот @" + json.loads(b)["result"]["username"]
        else:
            return True, "без перевірки"
        return True, "працює"
    except urllib.error.HTTPError as e:
        return False, f"сервіс відповів {e.code} — ключ неправильний або закінчився"
    except Exception as e:  # мережа
        return False, f"не вдалося перевірити: {e.__class__.__name__}"


# ------------------------------------------------------------------ модулі
def plugin(cmd: list[str]) -> bool:
    cb = claude_bin()
    if not cb:
        print("! Claude Code не знайдено — модуль увімкнеться після встановлення Claude")
        return False
    r = subprocess.run([cb, "plugin", *cmd], capture_output=True, text=True)
    if r.returncode:
        print("!", (r.stderr or r.stdout).strip()[-300:])
    return r.returncode == 0


def plugin_state() -> dict:
    cb = claude_bin()
    if not cb:
        return {}
    r = subprocess.run([cb, "plugin", "list", "--json"], capture_output=True, text=True)
    try:
        items = json.loads(r.stdout)
    except ValueError:
        return {}
    out = {}
    for it in items if isinstance(items, list) else items.get("plugins", []):
        pid = it.get("id") or it.get("name", "")
        if pid.endswith("@" + MARKET):
            out[pid.split("@")[0]] = bool(it.get("enabled", it.get("status") == "enabled"))
    return out


def module_on(m: str) -> None:
    c = config()
    setup = REPO / "installer" / "setup.sh"
    if setup.exists() and m != "studio":
        print(f"Встановлюю потрібне для «{MODULES[m][0]}»…", flush=True)
        subprocess.run(["bash", str(setup), "--deps", m], check=False)
    st = plugin_state()
    ok = plugin(["enable", f"{m}@{MARKET}"]) if m in st else plugin(["install", f"{m}@{MARKET}", "--scope", "user"])
    c.setdefault("modules", {})[m] = True
    save_config(c)
    need = [k.rstrip("?") for k in MODULES[m][1] if not k.endswith("?") and not key(k.rstrip("?"))]
    print(f"✓ «{MODULES[m][0]}» увімкнено" + ("" if ok else " (Claude підхопить при наступному запуску)"))
    if need:
        print("  Потрібен ключ:", ", ".join(need), "— studio key set <NAME>")


def module_off(m: str) -> None:
    if m == "studio":
        sys.exit("Основу вимкнути не можна.")
    plugin(["disable", f"{m}@{MARKET}"])
    c = config()
    c.setdefault("modules", {})[m] = False
    save_config(c)
    print(f"✓ «{MODULES[m][0]}» вимкнено (файли лишились — увімкнути можна будь-коли)")


# ------------------------------------------------------------------ лікар
def which(name: str) -> str | None:
    p = S / "bin" / name
    return str(p) if p.exists() else shutil.which(name)


def doctor() -> list[tuple[str, bool, str]]:
    c, rows = config(), []
    for b in ["ffmpeg", "ffprobe", "node", "uv"]:
        p = which(b)
        rows.append((b, bool(p), p or "немає — запустіть «Налаштування студії» ще раз"))
    rows.append(("python (base)", (S / "venvs/base/bin/python").exists(), str(S / "venvs/base")))
    rows.append(("Claude Code", bool(claude_bin()), claude_bin() or "немає — встановіть застосунок Claude"))
    mods = c.get("modules", {})
    if mods.get("montage"):
        hf = which("hyperframes")
        rows.append(("hyperframes", bool(hf), hf or "немає"))
        mw = Path.home() / ".cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo"
        rows.append(("Whisper (запасне розпізнавання)", mw.exists(), "модель завантажена" if mw.exists() else "докачається при першому запуску"))
    if mods.get("voice"):
        ok = (S / "models/resemble/enhancer_stage2").exists() and (S / "venvs/torch/bin/python").exists()
        rows.append(("Resemble Enhance", ok, "готово" if ok else "немає — studio module on voice"))
    if mods.get("upscale"):
        ok = (S / "models/realesr-general-x4v3.pth").exists()
        rows.append(("Real-ESRGAN", ok, "готово" if ok else "немає — studio module on upscale"))
    ws = workspace()
    rows.append(("Робоча папка", ws.exists(), str(ws)))
    return rows


# ------------------------------------------------------------------ main
def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "status":
        c, k, st = config(), keys(), plugin_state()
        data = {"workspace": str(workspace()), "modules": {m: bool(c.get("modules", {}).get(m)) for m in MODULES},
                "claude_plugins": st, "keys": {n: bool(k.get(n)) for n in KEY_INFO}, "pack": c.get("pack")}
        if "--json" in rest:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return
        print("Робоча папка:", data["workspace"])
        print("\nМодулі:")
        for m, (title, _) in MODULES.items():
            on = data["modules"][m]
            note = "" if m not in st or st[m] == on else "  (у Claude: " + ("увімкнено" if st[m] else "вимкнено") + ")"
            print(f"  {'✓' if on else '·'} {title} [{m}]{note}")
        print("\nКлючі:")
        for n, info in KEY_INFO.items():
            print(f"  {'✓' if k.get(n) else '·'} {info} [{n}]" + (f" {mask(k[n])}" if k.get(n) else ""))
    elif cmd == "module":
        if not rest or rest[0] == "list":
            main(["status"])
        elif rest[0] in ("on", "off") and len(rest) > 1 and rest[1] in MODULES:
            (module_on if rest[0] == "on" else module_off)(rest[1])
        else:
            sys.exit("Модулі: " + ", ".join(MODULES))
    elif cmd == "key":
        sub = rest[0] if rest else "list"
        k = keys()
        if sub == "list":
            for n, info in KEY_INFO.items():
                print(f"{'✓' if k.get(n) else '·'} {n:<20} {info}" + (f"  {mask(k[n])}" if k.get(n) else ""))
        elif sub == "set" and len(rest) > 1:
            v = rest[2] if len(rest) > 2 else sys.stdin.readline()
            k[rest[1]] = v.strip()
            save_keys(k)
            ok, msg = test_key(rest[1], v.strip())
            print(f"{'✓' if ok else '!'} {rest[1]} збережено — {msg}")
        elif sub == "get" and len(rest) > 1:
            print(key(rest[1]))
        elif sub == "del" and len(rest) > 1:
            k.pop(rest[1], None)
            save_keys(k)
            print(f"✓ {rest[1]} видалено")
        elif sub == "test":
            for n in rest[1:] or [n for n in KEY_INFO if k.get(n)]:
                ok, msg = test_key(n, k.get(n, ""))
                print(f"{'✓' if ok else '!'} {n}: {msg}")
        else:
            sys.exit("key list|set|get|del|test")
    elif cmd == "doctor":
        bad = 0
        for name, ok, info in doctor():
            print(f"{'✓' if ok else '!'} {name}: {info}")
            bad += not ok
        sys.exit(1 if bad else 0)
    elif cmd == "paths":
        ws = workspace()
        p = {"workspace": str(ws), "inbox": str(ws / "Вхідні"), "done": str(ws / "Готово"), "projects": str(ws / "Проєкти"),
             "style": str(ws / "Мій стиль"), "sounds": str(ws / "Бібліотека" / "Звуки"),
             "music": str(ws / "Бібліотека" / "Музика"), "bin": str(S / "bin"), "py": str(S / "bin" / "py"),
             "models": str(S / "models"), "repo": str(REPO)}
        print(json.dumps(p, ensure_ascii=False, indent=2) if "--json" in rest else "\n".join(f"{k}: {v}" for k, v in p.items()))
    elif cmd == "update":
        subprocess.run(["bash", str(REPO / "installer" / "update.sh")], check=False)
    else:
        sys.exit(f"Невідома команда {cmd}. studio help")


if __name__ == "__main__":
    main(sys.argv[1:])
