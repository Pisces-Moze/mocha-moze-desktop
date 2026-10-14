#!/usr/bin/python3
"""Compile the patched Tegra import/release helpers with a simulated GEM API."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

source=(Path(sys.argv[1])/'src/gallium/drivers/tegra/tegra_screen.c').read_text()
start=source.index('struct tegra_scanout_handle {')
end=source.index('static void tegra_screen_destroy',start)
helper=source[start:end]
fixture=r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef pthread_mutex_t simple_mtx_t;
#define simple_mtx_lock pthread_mutex_lock
#define simple_mtx_unlock pthread_mutex_unlock
struct tegra_screen {
    int fd;
    simple_mtx_t scanout_lock;
    struct tegra_scanout_handle *scanout_handles;
};
static unsigned closed;
static int fail_alloc;
static void *test_calloc(size_t count,size_t size) {
    return fail_alloc ? NULL : calloc(count,size);
}
static int drmPrimeFDToHandle(int screenfd,int fd,uint32_t *handle) {
    assert(screenfd==9);
    if(fd<0) {errno=EBADF;return -1;}
    *handle=(uint32_t)fd+100;
    return 0;
}
static int drmCloseBufferHandle(int fd,uint32_t handle) {
    assert(fd==9 && handle>=100);
    closed++;
    return 0;
}
#define calloc test_calloc
'''
exercise=r'''
#undef calloc
static struct tegra_screen screen={.fd=9,.scanout_lock=PTHREAD_MUTEX_INITIALIZER};
static pthread_barrier_t barrier;
static unsigned initial;
static void *worker(void *arg) {
    intptr_t id=(intptr_t)arg;
    for(unsigned cycle=0;cycle<100;cycle++) {
        uint32_t a,b;
        assert(tegra_scanout_import(&screen,21,&a)==0);
        assert(tegra_scanout_import(&screen,21,&b)==0 && a==b);
        pthread_barrier_wait(&barrier);
        tegra_scanout_release(&screen,a);
        pthread_barrier_wait(&barrier);
        if(id==0) {assert(closed==initial+cycle);assert(screen.scanout_handles->references==8);}
        pthread_barrier_wait(&barrier);
        tegra_scanout_release(&screen,b);
        pthread_barrier_wait(&barrier);
        if(id==0) {assert(closed==initial+cycle+1);assert(screen.scanout_handles==NULL);}
        pthread_barrier_wait(&barrier);
    }
    return NULL;
}
int main(void) {
    uint32_t a,b,c=0;
    assert(tegra_scanout_import(&screen,4,&a)==0);
    assert(tegra_scanout_import(&screen,4,&b)==0 && a==b);
    assert(tegra_scanout_import(&screen,-1,&c)==-EBADF && c==0);
    fail_alloc=1;
    assert(tegra_scanout_import(&screen,4,&c)==-ENOMEM && c==0);
    fail_alloc=0;
    tegra_scanout_release(&screen,0);
    tegra_scanout_release(&screen,a);assert(closed==0);
    tegra_scanout_release(&screen,b);assert(closed==1 && screen.scanout_handles==NULL);
    assert(tegra_scanout_import(&screen,7,&a)==0);
    assert(tegra_scanout_import(&screen,8,&b)==0);
    tegra_scanout_release(&screen,a);assert(screen.scanout_handles!=NULL);
    tegra_scanout_release(&screen,b);assert(closed==3 && screen.scanout_handles==NULL);
    initial=closed;
    pthread_t threads[8];
    assert(pthread_barrier_init(&barrier,NULL,8)==0);
    for(intptr_t id=0;id<8;id++) assert(pthread_create(&threads[id],NULL,worker,(void*)id)==0);
    for(unsigned id=0;id<8;id++) assert(pthread_join(threads[id],NULL)==0);
    assert(closed==103 && screen.scanout_handles==NULL);
    pthread_barrier_destroy(&barrier);
    pthread_mutex_destroy(&screen.scanout_lock);
    puts("TEGRA_SCANOUT_LIFETIME_PASSED shared/unique/failure/zero/concurrent");
}
'''
with tempfile.TemporaryDirectory() as directory:
    src=Path(directory)/'lifetime.c';binary=Path(directory)/'lifetime'
    src.write_text(fixture+helper+exercise)
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-D_XOPEN_SOURCE=700','-Wall','-Wextra','-Werror','-pthread',str(src),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
