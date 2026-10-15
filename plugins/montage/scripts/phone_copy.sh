#!/bin/bash
# Копія для телефону/месенджера: двопрохідний x264 під розмір (типово 24 МБ), звук AAC 160k. Оригінал не чіпає.
#   phone_copy.sh <відео.mp4> [МБ]   → <відео>_phone.mp4
export PATH="$HOME/.studio/bin:$PATH"
in="$1"; mb="${2:-24}"; out="${in%.*}_phone.mp4"
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$in")
vk=$("$HOME/.studio/bin/py" -c "print(max(800, int($mb*8192*0.96/$dur - 160)))")
t=$(mktemp -d)
ffmpeg -nostdin -v error -y -i "$in" -c:v libx264 -preset slow -b:v ${vk}k -pass 1 -passlogfile "$t/p" -an -f mp4 /dev/null && \
ffmpeg -nostdin -v error -y -i "$in" -c:v libx264 -preset slow -b:v ${vk}k -pass 2 -passlogfile "$t/p" -c:a aac -b:a 160k -movflags +faststart "$out"
rm -rf "$t"; ls -lh "$out" | awk '{print $5, $9}'
