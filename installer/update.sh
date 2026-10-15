#!/bin/bash
# Оновити Студію: свіжі файли з GitHub → модулі в Claude → докачати нове для увімкнених модулів → системні файли папки.
# Свої файли (Профіль, Мій стиль, Бібліотека, проєкти) не чіпає.
S="$HOME/.studio"
ZIP="${STUDIO_ZIP:-https://codeload.github.com/BevirAway/reels-studio/zip/refs/heads/main}"
echo ""; echo "  ✦ Оновлюю Студію…"
tmp=$(mktemp -d)
if ! curl -fsSL "$ZIP" -o "$tmp/s.zip" || ! unzip -q "$tmp/s.zip" -d "$tmp"; then
  echo "  ✗ Не вдалося завантажити оновлення — перевірте інтернет."; exit 1
fi
rm -rf "$S/repo.old"; mv "$S/repo" "$S/repo.old" && mv "$tmp"/reels-studio-*/ "$S/repo" && rm -rf "$tmp" "$S/repo.old"
mods=$("$S/venvs/base/bin/python" -c "import json,os; c=json.load(open(os.path.expanduser('~/.studio/config.json'))); print(','.join(m for m,v in c['modules'].items() if v and m!='studio'))")
ws=$("$S/venvs/base/bin/python" -c "import json,os; print(json.load(open(os.path.expanduser('~/.studio/config.json')))['workspace'])")
exec bash "$S/repo/installer/setup.sh" --auto --modules "$mods" --workspace "$ws"
