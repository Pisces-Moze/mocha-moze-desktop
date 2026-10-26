from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import subprocess,json,hashlib
p=Path(__file__).resolve().parent
font=p/'fonts/GoogleSans.ttf'
assert font.stat().st_size>10000
canvas=Image.new('RGBA',(600,144),(0,0,0,255));d=ImageDraw.Draw(canvas)
small=ImageFont.truetype(str(font),30)
large=ImageFont.truetype(str(font),64)
def toptext(x,y,text,font,fill):
 box=d.textbbox((0,0),text,font=font);d.text((x-box[0],y-box[1]),text,font=font,fill=fill)
label='powered by';word='debian'
label_width=d.textlength(label,font=small);word_width=d.textlength(word,font=large)
swirl=Image.open(p/'debian-swirl-small.png').convert('RGBA');swirl.thumbnail((52,64),Image.Resampling.LANCZOS)
total=word_width+18+swirl.width;start=(600-total)/2
d.text(((600-label_width)/2,36),label,font=small,fill='white',anchor='ls')
d.text((start,112),word,font=large,fill='white',anchor='ls')
canvas.alpha_composite(swirl,(round(start+word_width+18),58))
canvas.save(p/'powered-by-debian.png')
footer=Image.new('RGBA',(240,60),(0,0,0,255));d=ImageDraw.Draw(footer)
tiny=ImageFont.truetype(str(font),30);text='Moze';spacing=3
width=sum(d.textlength(c,font=tiny) for c in text)+(len(text)-1)*spacing;x=(240-width)/2
for c in text:
 d.text((x,40),c,font=tiny,fill=(180,180,180),anchor='ls');x+=d.textlength(c,font=tiny)+spacing
footer.save(p/'moze-footer.png')
print('POWERED_BY_DEBIAN_GOOGLE_SANS_AND_OFFICIAL_SWIRL_RENDERED')
