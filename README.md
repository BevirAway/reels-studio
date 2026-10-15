# Студія рілсів

Помічник для рілсів, текстів і публікацій, з яким говориш звичайними словами в застосунку **Claude**.
Монтаж рілсів «говорюча голова» (нарізка без пауз, субтитри по словах, анімації у твоєму стилі, звук і музика),
чистка голосу, підписи й каруселі, контент-план, дослідження Instagram, публікація в Instagram і Telegram за розкладом.

## Що потрібно
- Mac з чипом M1 або новішим (на Intel працює без чистки голосу й покращення якості), macOS 13+, 15 ГБ вільного місця.
- Акаунт Claude з підпискою (Pro або Max — монтаж забирає багато).
- За бажанням ключі: ElevenLabs (точніше розпізнавання мови, генерація звуків), Apify (дослідження Instagram).

## Встановлення
1. Встанови застосунок Claude: https://claude.ai/download і увійди в свій акаунт.
2. Відкрий **Термінал** (Cmd+Пробіл → «Термінал»), встав рядок і натисни Enter:
   ```
   curl -fsSL https://raw.githubusercontent.com/BevirAway/reels-studio/main/install.sh | bash
   ```
3. З'являться вікна: обери, що потрібно, і за бажанням встав ключі. Встановлення — 10–30 хвилин. Пароль не потрібен.
4. Відкрий Claude → **Code** → папка **Студія** → напиши «Привіт! Давай налаштуємо студію».

Налаштування потім — ярлик «Налаштування студії» в папці «Студія», оновлення — «Оновити студію».

## Як влаштовано (для того, хто допомагає)
- `install.sh` → завантажує репозиторій у `~/.studio/repo` → `installer/setup.sh`: uv + Python, ffmpeg, Node,
  Claude Code CLI, залежності модулів (hyperframes + браузер + навички, Whisper MLX, PyTorch + Resemble Enhance,
  Real-ESRGAN) — усе в `~/.studio`, без sudo і Homebrew. Робоча папка `~/Студія` з `AGENTS.md`, профілем і бібліотекою.
- Модулі — плагіни Claude Code з цього маркетплейсу (`reels-studio`): `studio` (основа), `montage`, `voice`,
  `upscale`, `sounds`, `texts`, `research`, `publish`. Увімкнути/вимкнути — `~/.studio/bin/studio module on|off <модуль>`.
- Ключі — `~/.studio/keys.env` (600), стан — `~/.studio/config.json`, журнал встановлення — `~/.studio/install.log`.
- Перевірка без вікон: `STUDIO_SRC=<папка репо> bash install.sh --auto --modules montage,voice --pack ~/Downloads/studio-pack-iryna.zip`.
- Пакет стилю (особисте, не в репозиторії): zip з `стиль/`, `профіль.md`, `зразок рілса/` — `--pack <zip>` або просто лежить у `~/Downloads/studio-pack*.zip`.
