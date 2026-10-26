/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef MOZE_BOOT_ART_H
#define MOZE_BOOT_ART_H
#include "moze-boot-assets.h"
/* Physical portrait pixels; desktop and charger orientation are independent. */
#define MOZE_SCREEN_W 1536
#define MOZE_SCREEN_H 2048
#define MOZE_BG 0x000000u
#define MOZE_FG 0xffffffu
#define MOZE_LOG_X 0
#define MOZE_LOG_Y 0
#define MOZE_LOG_COLS 96
#define MOZE_LOG_ROWS 64
#define MOZE_ART_X 558
#define MOZE_ART_Y 430
#define MOZE_RING_X 736
#define MOZE_RING_Y 1388
#define MOZE_BRAND_X 468
#define MOZE_BRAND_Y 1760
#define MOZE_FOOTER_X 648
#define MOZE_FOOTER_Y 1940
static inline unsigned int moze_art_pixel(int x, int y, unsigned int ms, int reduced_motion)
{
    int u=x-MOZE_ART_X, v=y-MOZE_ART_Y;
    unsigned int frame, offset, alpha, value;
    if (u>=0 && u<MOZE_ART_W && v>=0 && v<MOZE_ART_H)
        return moze_palette[moze_emblem[v*MOZE_ART_W+u]];
    u=x-MOZE_BRAND_X; v=y-MOZE_BRAND_Y;
    if (u>=0 && u<MOZE_BRAND_W && v>=0 && v<MOZE_BRAND_H)
        return moze_brand_palette[moze_brand[v*MOZE_BRAND_W+u]];
    u=x-MOZE_FOOTER_X; v=y-MOZE_FOOTER_Y;
    if (u>=0 && u<MOZE_FOOTER_W && v>=0 && v<MOZE_FOOTER_H) {
        value=moze_footer[v*MOZE_FOOTER_W+u];
        return (value<<16)|(value<<8)|value;
    }
    u=x-MOZE_RING_X; v=y-MOZE_RING_Y;
    if (u<0 || u>=MOZE_RING_W || v<0 || v>=MOZE_RING_H) return MOZE_BG;
    frame=reduced_motion ? 30 : (ms/MOZE_RING_FRAME_MS)%MOZE_RING_FRAMES;
    offset=frame*MOZE_RING_W*MOZE_RING_H+v*MOZE_RING_W+u;
    alpha=moze_ring_alpha4[offset/2];
    alpha=offset&1 ? alpha&15 : alpha>>4;
    value=alpha*17;
    return (value<<16)|(value<<8)|value;
}
static inline unsigned short moze_rgb565(unsigned int rgb)
{
    return ((rgb>>8)&0xf800)|((rgb>>5)&0x07e0)|((rgb>>3)&0x001f);
}
#endif
