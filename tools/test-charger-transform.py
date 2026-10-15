#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the real framebuffer mapping and check physical corner orientation."""
from pathlib import Path
import subprocess,tempfile

root=Path(__file__).resolve().parents[1]
text=(root/'charging/mocha-charger-ui.c').read_text()
mapping=text[text.index('static void frame_point('):text.index('static void present(')]
packing=text[text.index('static uint32_t channel('):text.index('static void frame_point(')]
fixture='''
#include <assert.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <linux/fb.h>
#define W 720
#define H 520
typedef struct {uint32_t pixels[W*H];} cairo_surface_t;
static unsigned char *cairo_image_surface_get_data(cairo_surface_t *s){return (unsigned char *)s->pixels;}
'''+packing+mapping+'''
int main(void){
 cairo_surface_t *surface=malloc(sizeof(*surface));assert(surface);
 for(unsigned i=0;i<W*H;i++)surface->pixels[i]=(i*2654435761u)&0xffffff;
 struct fb_var_screeninfo formats[3]={
  {.bits_per_pixel=32,.red={16,8,0},.green={8,8,0},.blue={0,8,0},.transp={24,8,0}},
  {.bits_per_pixel=16,.red={11,5,0},.green={5,6,0},.blue={0,5,0}},
  {.bits_per_pixel=32,.red={0,8,0},.green={8,8,0},.blue={16,8,0}}
 };
 double opacity[]={0,.27,1},scales[]={.95,1};
 for(unsigned format=0;format<3;format++)for(unsigned a=0;a<3;a++)for(unsigned b=0;b<2;b++){
  struct fb_var_screeninfo *v=&formats[format];unsigned bytes=v->bits_per_pixel/8;
  uint8_t *packed=pack(v,surface,opacity[a],scales[b]);assert(packed);
  for(int y=0;y<H;y++)for(int x=0;x<W;x++){
   int sx=(int)((x-W/2)/scales[b]+W/2),sy=(int)((y-H/2)/scales[b]+H/2);
   uint32_t rgb=(sx>=0&&sx<W&&sy>=0&&sy<H)?surface->pixels[sy*W+sx]:0;
   uint32_t expected=channel((unsigned)(((rgb>>16)&255)*opacity[a]),v->red)
    |channel((unsigned)(((rgb>>8)&255)*opacity[a]),v->green)
    |channel((unsigned)((rgb&255)*opacity[a]),v->blue)|channel(255,v->transp);
   assert(!memcmp(packed+((size_t)y*W+x)*bytes,&expected,bytes));
  }
  free(packed);
 }
 free(surface);
 const int expected[4][4]={{408,764,1127,1283},{1027,664,508,1383},
                          {1127,1283,408,764},{508,1383,1027,664}};
 unsigned angles[4]={0,90,180,270};
 for(int i=0;i<4;i++){
  int x,y;frame_point(angles[i],1536,2048,0,0,&x,&y);
  assert(x==expected[i][0]&&y==expected[i][1]);
  frame_point(angles[i],1536,2048,W-1,H-1,&x,&y);
  assert(x==expected[i][2]&&y==expected[i][3]);
  unsigned char *seen=calloc(1536*2048,1);assert(seen);
  for(int sy=0;sy<H;sy++)for(int sx=0;sx<W;sx++){
   frame_point(angles[i],1536,2048,sx,sy,&x,&y);
   assert(x>=0&&x<1536&&y>=0&&y<2048);
   assert(!seen[y*1536+x]);seen[y*1536+x]=1;
  }
  free(seen);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory() as folder:
    source=Path(folder)/'mapping.c';binary=Path(folder)/'mapping'
    source.write_text(fixture)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('Four physical orientations and 18 pixel-format/opacity/scale cases passed')
