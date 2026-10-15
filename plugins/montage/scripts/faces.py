#!/usr/bin/env python3
"""Где лицо в исходнике (для кадрирования 9:16 и места субтитров).
usage: faces.py <video> START-END [START-END ...]
Печатает медиану центра лица (x, y) и ширину в пикселях исходника. OpenCV Haar, 2 кадра/с.
Перевод в кадр 1080x1920 при заполнении по высоте (исходник 1920x1080 → масштаб 1.778):
  left видео = 540 - cx*1.778 ; лицо по y = cy*1.778 ; подбородок ≈ (cy + 0.65*w)*1.778 → субтитры ниже на 60–100 px.
"""
import cv2, sys, subprocess, numpy as np
src = sys.argv[1]
cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
probe = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0",src],capture_output=True,text=True).stdout.strip().split(",")
W, H = int(probe[0]), int(probe[1]); w2, h2 = W // 2, H // 2
for r in sys.argv[2:]:
    a, b = map(float, r.split("-"))
    raw = subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",str(a),"-to",str(b),"-i",src,"-vf",f"fps=2,scale={w2}:{h2},format=gray","-f","rawvideo","-"],capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h2, w2)
    xs, ys, ws = [], [], []
    for f in fr:
        fs = cc.detectMultiScale(f, 1.1, 5, minSize=(40, 40))
        if len(fs):
            x, y, w, h = max(fs, key=lambda q: q[2] * q[3]); xs.append((x + w / 2) * 2); ys.append((y + h / 2) * 2); ws.append(w * 2)
    if xs:
        print(f"{a}-{b}: cx={np.median(xs):.0f} [{min(xs):.0f}..{max(xs):.0f}] cy={np.median(ys):.0f} w={np.median(ws):.0f}  ({len(xs)}/{len(fr)} кадров с лицом)")
    else:
        print(f"{a}-{b}: лица нет (перебивка/крупный план предметов?)")
