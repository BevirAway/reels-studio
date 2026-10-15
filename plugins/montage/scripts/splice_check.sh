#!/bin/zsh
# Склеить куски исходника по таймкодам и перерасшифровать — проверка, что склейки чистые (без обрывков слов).
export PATH="$HOME/.studio/bin:$PATH"
# usage: splice_check.sh <source.(wav|mp4)> <out_name> START-END [START-END ...]
# пример: splice_check.sh ../src/audio.wav segA 1341.12-1356.45 638.84-641.80
set -e
src=$1; name=$2; shift 2
tmp=$(mktemp -d); i=0
for r in "$@"; do a=${r%-*}; b=${r#*-}
  ffmpeg -nostdin -v error -y -ss $a -to $b -i "$src" -ar 16000 -ac 1 "$tmp/p$i.wav"; echo "file '$tmp/p$i.wav'" >> "$tmp/l.txt"; i=$((i+1)); done
ffmpeg -nostdin -v error -y -f concat -safe 0 -i "$tmp/l.txt" -c copy "$tmp/$name.wav"
echo "длительность: $(ffprobe -v error -show_entries format=duration -of csv=p=0 $tmp/$name.wav) с"
# расшифровка — stt.py рядом (Scribe v2, подстраховка Whisper MLX)
"$HOME/.studio/bin/py" "$(dirname "$0")/stt.py" "$tmp/$name.wav" --lang ${STT_LANG:-uk} --format txt --out "$tmp/$name.txt" >/dev/null 2>&1
tr '\n' ' ' < "$tmp/$name.txt"; echo
echo "(аудио: $tmp/$name.wav)"
