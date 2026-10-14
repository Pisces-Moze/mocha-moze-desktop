/* SPDX-License-Identifier: GPL-2.0-only */
/* Allocations only: no modeset, framebuffer writes or foreign GEM handles. */
#include <errno.h>
#include <fcntl.h>
#include <gbm.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <xf86drm.h>

static void snapshot(const char *stage) {
    FILE *file=fopen("/sys/kernel/debug/dma_buf/bufinfo","r");
    char line[256];
    if(!file) {perror("DMA-BUF diagnostic list");exit(1);}
    while(fgets(line,sizeof(line),file)) {
        unsigned objects;uint64_t bytes;
        if(sscanf(line,"Total %u objects, %" SCNu64 " bytes",&objects,&bytes)==2)
            printf("%s objects=%u bytes=%" PRIu64 "\n",stage,objects,bytes);
    }
    fclose(file);fflush(stdout);
}

static void cycle(struct gbm_device *device) {
    for(unsigned i=0;i<128;i++) {
        struct gbm_bo *bo=gbm_bo_create(device,128,128,GBM_FORMAT_XRGB8888,
                                      GBM_BO_USE_SCANOUT|GBM_BO_USE_RENDERING|GBM_BO_USE_LINEAR);
        if(!bo) {perror("gbm scanout allocation");exit(1);}
        if(gbm_bo_get_handle(bo).u32==0) {fprintf(stderr,"Missing scanout GEM handle\n");exit(1);}
        gbm_bo_destroy(bo);
    }
}

int main(int argc,char **argv) {
    if(argc!=2) {fprintf(stderr,"Usage: %s /dev/dri/cardN (Tegra primary node)\n",argv[0]);return 2;}
    int fd=open(argv[1],O_RDWR|O_CLOEXEC);
    if(fd<0) {perror("DRM node");return 1;}
    drmVersionPtr version=drmGetVersion(fd);
    if(!version || strcmp(version->name,"tegra")) {fprintf(stderr,"Expected Tegra DRM\n");return 1;}
    drmFreeVersion(version);
    struct gbm_device *device=gbm_create_device(fd);
    if(!device) {perror("GBM device");return 1;}
    cycle(device);snapshot("warmup-128");
    cycle(device);snapshot("after-256");
    cycle(device);snapshot("after-384");
    gbm_device_destroy(device);close(fd);
    snapshot("after-device-close");
    puts("SCANOUT_CREATE_DESTROY_COMPLETED 384; compare live-device buffer growth separately");
    return 0;
}
