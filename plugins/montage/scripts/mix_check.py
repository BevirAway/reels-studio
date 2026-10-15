#!/usr/bin/env python3
# Голос против микса: mix_check.py <голос.wav> <итог.mp4> [<фон_после_приглушения.wav>]
# по опыту правок: сначала «голос намного тише музыки и эффектов», потом «вообще не слышу звуковые эффекты». Норма:
#  итог −12…−13 LUFS; в речи итог ≈ голос; нигде фон не громче голоса рядом больше чем на +3 дБ (верхняя граница);
#  с третьим аргументом (стем ЭФФЕКТОВ без музыки, уже приглушённый) — медиана событий −16…−20 дБ к голосу рядом
#  (по опыту: при ~−16 «чуть тише», при −33 «не слышу»); тише −24 — не слышно, громче −10 — громко. Окна по 400 мс; «рядом» — самый громкий голос в ±0.6 с.
import re, statistics, subprocess, sys
def mom(f):
    o = subprocess.run(['ffmpeg', '-hide_banner', '-i', f, '-af', 'ebur128=metadata=1,ametadata=print:key=lavfi.r128.M',
                        '-f', 'null', '-'], capture_output=True, text=True).stderr
    t = [round(float(x), 1) for x in re.findall(r'pts_time:([\d.]+)', o)]
    m = [float(x) for x in re.findall(r'lavfi.r128.M=(-?[\d.]+)', o)]
    return dict(zip(t, m)), re.findall(r'I:\s+(-?[\d.]+) LUFS', o)[-1]
v, vi = mom(sys.argv[1]); f, fi = mom(sys.argv[2])
near = lambda t: max([v[x] for x in v if abs(x - t) <= 0.6] or [-70])
sp = [f[t] - v[t] for t in f if t in v and v[t] > -30]
print(f'голос {vi} LUFS, итог {fi} LUFS, в речи итог−голос медиана {statistics.median(sp):+.1f} дБ')
loud = [(t, round(f[t] - near(t), 1)) for t in sorted(f) if near(t) > -35 and f[t] - near(t) > 3]
print('фон громче голоса на >3 дБ:', loud[:20] or 'нет')
bad = bool(loud) or not -13.6 <= float(fi) <= -11.5
if len(sys.argv) > 3:
    b, bi = mom(sys.argv[3])
    # события фона: локальные максимумы громче −45 LUFS
    ev = [t for t in sorted(b) if b[t] > -45 and b[t] >= max(b.get(round(t + k / 10, 1), -99) for k in range(-3, 4))]
    rel = [(t, round(b[t] - near(t), 1)) for t in ev if near(t) > -35]
    quiet = [x for x in rel if x[1] < -24]; hot = [x for x in rel if x[1] > -10]
    print(f'фон {bi} LUFS; событий {len(rel)}, медиана {statistics.median([x[1] for x in rel]) if rel else 0:+.1f} дБ к голосу')
    print('не слышно (тише −24 дБ):', quiet[:15] or 'нет'); print('громко (выше −10 дБ):', hot[:15] or 'нет')
    med = statistics.median([x[1] for x in rel]) if rel else -99
    bad = bad or bool(hot) or len(quiet) > len(rel) / 4 or not -20.5 <= med <= -15.5
sys.exit(1 if bad else 0)
