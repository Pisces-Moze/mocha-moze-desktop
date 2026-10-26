"""Encode the original avatar cutout and a small indeterminate UI ring.
The avatar is resized/encoded only, never drawn or reconstructed by code.
"""
from pathlib import Path
from PIL import Image
import argparse,hashlib,json,math
p=Path(__file__).resolve().parent
a=argparse.ArgumentParser();a.add_argument('--image',type=Path,default=p/'moze-avatar-cutout.png');args=a.parse_args()
original=Image.open(args.image).convert('RGBA');original.thumbnail((420,420),Image.Resampling.LANCZOS)
background=Image.new('RGBA',(420,420),(0,0,0,255));background.alpha_composite(original,((420-original.width)//2,(420-original.height)//2))
im=background.convert('RGB').quantize(colors=128);pal=im.getpalette()
def array(name,data,kind='unsigned char'):
 return 'static const '+kind+' '+name+'[] = {\n'+''.join(' '+','.join(str(v) for v in data[i:i+24])+',\n' for i in range(0,len(data),24))+'};\n'
def bezier(q,b,c):return 3*(1-q)*(1-q)*q*b+3*(1-q)*q*q*c+q*q*q
atlas=[];frames=[]
for frame in range(120):
 t=frame/120;grow=t*2 if t<.5 else 2-t*2;lo,hi=0.,1.
 for _ in range(24):
  q=(lo+hi)/2
  if bezier(q,.77,.175)<grow:lo=q
  else:hi=q
 sweep=48+204*bezier((lo+hi)/2,0,1);start=-90+1080*t-sweep/2
 frames.append(dict(start=round(start,6),sweep=round(sweep,6)))
 angle=math.radians(start);extent=math.radians(sweep);end=angle+extent
 ax,ay=32+27*math.cos(angle),32+27*math.sin(angle);bx,by=32+27*math.cos(end),32+27*math.sin(end)
 alpha=[]
 for y in range(64):
  for x in range(64):
   hits=0
   for ox,oy in [(a,b) for a in (.125,.375,.625,.875) for b in (.125,.375,.625,.875)]:
    px,py=x+ox,y+oy;dx,dy=px-32,py-32;theta=(math.atan2(dy,dx)-angle)%(2*math.pi)
    body=theta<=extent and abs(math.hypot(dx,dy)-27)<=1.75
    caps=min((px-ax)**2+(py-ay)**2,(px-bx)**2+(py-by)**2)<=1.75**2
    hits+=bool(body or caps)
   alpha.append(round(hits*15/16))
 atlas.extend((alpha[i]<<4)|alpha[i+1] for i in range(0,len(alpha),2))
heads=[f['start']+f['sweep'] for f in frames]
tails=[f['start'] for f in frames]
for values in [heads,tails]:
 assert all(b>a for a,b in zip(values,values[1:]+[values[0]+1080])), 'Ring endpoints must keep moving forward through loop seam'
header='/* SPDX-License-Identifier: GPL-2.0-or-later */\n/* Original avatar cutout, UI ring, requested Debian and Moze marks. */\n#ifndef MOZE_BOOT_ASSETS_H\n#define MOZE_BOOT_ASSETS_H\n#define MOZE_ART_W 420\n#define MOZE_ART_H 420\n#define MOZE_RING_W 64\n#define MOZE_RING_H 64\n#define MOZE_RING_FRAMES 120\n#define MOZE_RING_FRAME_MS 20\n'
header+=array('moze_palette',[(pal[i]<<16)|(pal[i+1]<<8)|pal[i+2] for i in range(0,384,3)],'unsigned int')
header+=array('moze_emblem',list(im.tobytes()))+array('moze_ring_alpha4',atlas)+'#endif\n'
brand=Image.open(p/'powered-by-debian.png').convert('RGB').quantize(colors=128)
assert brand.size==(600,144)
bp=brand.getpalette()
footer=Image.open(p/'moze-footer.png').convert('L')
assert footer.size==(240,60)
header=header.removesuffix('#endif\n')
header+='#define MOZE_BRAND_W 600\n#define MOZE_BRAND_H 144\n#define MOZE_FOOTER_W 240\n#define MOZE_FOOTER_H 60\n'
header+=array('moze_brand_palette',[(bp[i]<<16)|(bp[i+1]<<8)|bp[i+2] for i in range(0,384,3)],'unsigned int')
header+=array('moze_brand',list(brand.tobytes()))+array('moze_footer',list(footer.tobytes()))+'#endif\n'
(p/'moze-boot-assets.h').write_text(header,encoding='ascii',newline='\n')
(p/'spinner-frames.json').write_text(json.dumps(dict(frame_ms=20,radius=27,stroke_width=3.5,reduced_frame=30,frames=frames),separators=(',',':'))+'\n',encoding='ascii',newline='\n')
print('MOZE_ASSET_BYTES',len(im.tobytes())+len(atlas)+512+len(brand.tobytes())+512+len(footer.tobytes()));print('SHA256',hashlib.sha256(header.encode()).hexdigest())
