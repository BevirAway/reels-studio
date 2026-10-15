#!/usr/bin/env python3
# Лист кадров с подписями: contact_sheet.py <папка с png (имя NNN_подпись.png)> <out.png> [колонок]
# Кадры снимать: ffmpeg -nostdin -ss T -i video -frames:v 1 -vf scale=320:-1 dir/000_T.png  (drawtext в ffmpeg нет — подписи ставит PIL)
import sys,glob,os
from PIL import Image,ImageDraw,ImageFont
files=sorted(glob.glob(sys.argv[1]+'/*.png')); out=sys.argv[2]; cols=int(sys.argv[3]) if len(sys.argv)>3 else 8
ims=[Image.open(f) for f in files]; w,h=ims[0].size; rows=(len(ims)+cols-1)//cols
S=Image.new('RGB',(cols*w,rows*h))
try: font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',26)
except: font=None
for k,(f,im) in enumerate(zip(files,ims)):
    x,y=(k%cols)*w,(k//cols)*h; S.paste(im.resize((w,h)),(x,y)); d=ImageDraw.Draw(S)
    lab=os.path.basename(f)[:-4].split('_',1)[-1]; d.rectangle([x,y,x+110,y+32],fill='black'); d.text((x+4,y+2),lab,fill='yellow',font=font)
S.save(out); print(S.size)
