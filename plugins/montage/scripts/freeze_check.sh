#!/bin/bash
# «Зависання»: куски, де кадр майже не міняється довше 0.6 с (стоп-кадр, скінчилось відео). Друкує інтервали.
#   freeze_check.sh <рілс.mp4>
export PATH="$HOME/.studio/bin:$PATH"
ffmpeg -nostdin -i "$1" -vf "freezedetect=n=0.003:d=0.6" -map 0:v -f null - 2>&1 | grep -oE "freeze_(start|end): [0-9.]+" | paste - - | sed 's/freeze_start: //; s/freeze_end: / → /' || true
echo "(порожньо — зависань немає)"
