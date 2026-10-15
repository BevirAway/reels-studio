#!/bin/bash
# Студія — встановлення однією командою (вставити в Термінал):
#   curl -fsSL https://raw.githubusercontent.com/BevirAway/reels-studio/main/install.sh | bash
# Для перевірки з локальної папки: STUDIO_SRC=/шлях/до/reels-studio bash install.sh [--auto …]
set -e
S="$HOME/.studio"
ZIP="${STUDIO_ZIP:-https://codeload.github.com/BevirAway/reels-studio/zip/refs/heads/main}"
mkdir -p "$S"
echo ""
echo "  Студія — завантажую файли…"
if [ -n "${STUDIO_SRC:-}" ]; then
  rm -rf "$S/repo.new"; mkdir -p "$S/repo.new"
  (cd "$STUDIO_SRC" && tar --exclude .git -cf - .) | (cd "$S/repo.new" && tar -xf -)
else
  tmp=$(mktemp -d)
  curl -fsSL "$ZIP" -o "$tmp/studio.zip"
  unzip -q "$tmp/studio.zip" -d "$tmp"
  rm -rf "$S/repo.new"; mv "$tmp"/reels-studio-*/ "$S/repo.new"; rm -rf "$tmp"
fi
rm -rf "$S/repo"; mv "$S/repo.new" "$S/repo"
if [ -e /dev/tty ] && [ -t 1 ]; then
  exec bash "$S/repo/installer/setup.sh" "$@" </dev/tty
else
  exec bash "$S/repo/installer/setup.sh" "$@"
fi
