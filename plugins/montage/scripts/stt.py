#!/usr/bin/env python3
"""Распознавание речи студии: ElevenLabs Scribe v2 (ключ ELEVENLABS_API_KEY в ~/.studio/keys.env), подстраховка —
Whisper large-v3-turbo через MLX прямо на Mac (нет ключа, нет сети, сервис ответил ошибкой — расшифровка всё равно будет).

Выход в формате Whisper: {"text", "segments": [{"start", "end", "text", "words": [{"word", "start", "end"}]}], "language",
"engine"}.

usage: stt.py <аудио/видео> [--lang uk|ru|en|auto] [--out файл] [--format json|txt|srt|words] [--prompt текст]
              [--engine auto|scribe|whisper]
  --format words — плоский список [{text, start, end}] (transcript.json для hyperframes / talking-head-recut)
  --prompt — подсказка только для Whisper (initial_prompt); Scribe термины знает и так (замер: словарь не дал прибавки)
Без --out пишет <имя>.<формат> рядом с файлом. Расход — ~/.studio/stt_usage.jsonl.
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

S = Path.home() / ".studio"
USAGE = S / "stt_usage.jsonl"
os.environ["PATH"] = f"{S / 'bin'}:{os.environ.get('PATH', '')}"
SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MLX_TURBO = "mlx-community/whisper-large-v3-turbo"


def _env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    try:
        for line in (S / "keys.env").read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def duration(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _segments(words: list[dict]) -> list[dict]:
    """Слова → сегменты как у Whisper: конец фразы (.?!… и закрывающая кавычка), пауза > 1 с, 7 с или 80 знаков
    (длинная реплика в субтитрах закрывает кадр)."""
    segs, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        long = w["end"] - cur[0]["start"] >= 7 or len("".join(x["word"] for x in cur)) >= 80
        if not nxt or re.search(r"[.?!…][\"»”']?$", w["word"].strip()) or nxt["start"] - w["end"] > 1.0 or long:
            segs.append({"id": len(segs), "start": cur[0]["start"], "end": cur[-1]["end"],
                         "text": "".join(x["word"] for x in cur), "words": cur})
            cur = []
    return segs


def _audio_only(path, tmpdir: str) -> str:
    """Только звук, моно 16 кГц opus: исходник видео на гигабайты не грузим в память и в облако."""
    out = os.path.join(tmpdir, "a.ogg")
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "libopus", "-b:a", "32k", out], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"ffmpeg: {r.stderr[-200:]}")
    return out


def scribe(path, lang: str | None, sec: float = 0.0) -> dict:
    import tempfile
    import requests
    key = _env("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("нет ELEVENLABS_API_KEY")
    form = [("model_id", "scribe_v2"), ("tag_audio_events", "false"), ("timestamps_granularity", "word")]
    if lang:
        form.append(("language_code", lang))
    timeout = (15, 60 + 0.5 * sec)                  # чтение ответа ~ длительности звука; зависание — быстро к Whisper
    with tempfile.TemporaryDirectory() as td:
        audio = _audio_only(path, td)
        for attempt in range(2):                    # один повтор на перегрузку; ключ/квоту не повторяем
            with open(audio, "rb") as fh:
                r = requests.post(SCRIBE_URL, headers={"xi-api-key": key}, data=form,
                                  files={"file": ("audio.ogg", fh, "audio/ogg")}, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0 and "quota" not in r.text:
                time.sleep(5); continue
            break
    if r.status_code != 200:
        raise RuntimeError(f"Scribe HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    words = [{"word": " " + w["text"].strip(), "start": float(w["start"]), "end": float(w["end"])}
             for w in d.get("words") or [] if w.get("type") == "word" and str(w.get("text", "")).strip()]
    if not words and str(d.get("text") or "").strip():
        raise RuntimeError("Scribe вернул текст без слов")          # без таймкодов не годится — пусть сделает Whisper
    return {"text": str(d.get("text") or "").strip(), "segments": _segments(words),
            "language": d.get("language_code") or lang or "", "engine": "scribe_v2"}


def whisper(path, lang: str | None, prompt: str = "") -> dict:
    try:
        import mlx_whisper
    except ImportError:
        raise SystemExit("Whisper на цьому Mac недоступний (потрібен M-чип) — додайте ключ ElevenLabs: studio key set ELEVENLABS_API_KEY")
    r = mlx_whisper.transcribe(str(path), path_or_hf_repo=MLX_TURBO, language=lang, word_timestamps=True,
                               initial_prompt=prompt or None)
    segs = [{"id": i, "start": s["start"], "end": s["end"], "text": s["text"],
             "words": [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in s.get("words") or []]}
            for i, s in enumerate(r.get("segments") or [])]
    return {"text": (r.get("text") or "").strip(), "segments": segs, "language": r.get("language") or lang or "",
            "engine": "mlx-whisper-turbo"}


def _log(engine: str, path, sec: float, err: str = "") -> None:
    try:
        USAGE.parent.mkdir(parents=True, exist_ok=True)
        with USAGE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "engine": engine,
                                "audio_sec": round(sec, 1), "file": Path(path).name, **({"fallback_reason": err} if err else {})},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def transcribe(path, lang: str | None = "uk", prompt: str = "", engine: str = "auto") -> dict:
    """Расшифровка в формате Whisper. engine: auto (Scribe → при сбое Whisper MLX), scribe, whisper."""
    lang = None if lang in (None, "", "auto") else lang
    sec = duration(path)
    err = ""
    if engine in ("auto", "scribe"):
        try:
            d = scribe(path, lang, sec)
            _log(d["engine"], path, sec)
            return d
        except Exception as e:                      # сеть, ключ, лимит, ошибка сервиса — подстраховка
            err = str(e)[:200]
            if engine == "scribe":
                raise
            print(f"stt: Scribe не сработал ({err}) — Whisper MLX", file=sys.stderr)
    d = whisper(path, lang, prompt)
    _log(d["engine"], path, sec, err)
    return d


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def render(d: dict, fmt: str) -> str:
    if fmt == "txt":
        return ("\n".join(s["text"].strip() for s in d["segments"]) or d.get("text", "")) + "\n"
    if fmt == "srt":
        return "\n".join(f"{i + 1}\n{_ts(s['start'])} --> {_ts(s['end'])}\n{s['text'].strip()}\n"
                         for i, s in enumerate(d["segments"]))
    if fmt == "words":
        return json.dumps([{"text": w["word"].strip(), "start": w["start"], "end": w["end"]}
                           for s in d["segments"] for w in s["words"]], ensure_ascii=False)
    return json.dumps(d, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description="Расшифровка речи: Scribe v2, подстраховка Whisper turbo MLX")
    ap.add_argument("audio")
    ap.add_argument("--lang", default="uk")
    ap.add_argument("--out")
    ap.add_argument("--format", default="json", choices=["json", "txt", "srt", "words"])
    ap.add_argument("--prompt", default="")
    ap.add_argument("--engine", default="auto", choices=["auto", "scribe", "whisper"])
    a = ap.parse_args()
    src = Path(a.audio)
    if not src.exists():
        sys.exit(f"нет файла: {src}")
    d = transcribe(src, a.lang, a.prompt, a.engine)
    out = Path(a.out) if a.out else src.with_suffix("." + a.format)
    out.write_text(render(d, a.format), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
