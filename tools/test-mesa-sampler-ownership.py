#!/usr/bin/python3
"""Exercise actual Tegra binding/destruction functions against Gallium ownership."""
import os,re,subprocess,sys,tempfile
from pathlib import Path
source=(Path(sys.argv[1])/'src/gallium/drivers/tegra/tegra_context.c').read_text()
functions=[]
for name in ('tegra_set_sampler_views','tegra_sampler_view_destroy'):
    found=re.search(r'static void\n'+name+r'\(.*?\n\{.*?\n\}',source,re.S)
    assert found,name
    functions.append(found.group())
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define PIPE_MAX_SHADER_SAMPLER_VIEWS 16
enum pipe_shader_type {FRAGMENT};
struct pipe_resource {int dummy;};
struct pipe_reference {int count;};
struct pipe_sampler_view {struct pipe_reference reference;struct pipe_resource *texture;bool wrapper;struct pipe_context *context;};
struct pipe_context {
    void (*set_sampler_views)(struct pipe_context *,enum pipe_shader_type,unsigned,unsigned,unsigned,bool,struct pipe_sampler_view **);
};
struct tegra_context {struct pipe_context base;struct pipe_context *gpu;};
struct tegra_sampler_view {struct pipe_sampler_view base;struct pipe_sampler_view *gpu;unsigned refcount;};
static struct tegra_context *to_tegra_context(struct pipe_context *p) {return (struct tegra_context *)p;}
static struct tegra_sampler_view *to_tegra_sampler_view(struct pipe_sampler_view *p) {return (struct tegra_sampler_view *)p;}
static struct pipe_sampler_view *tegra_sampler_view_unwrap(struct pipe_sampler_view *p) {return p ? to_tegra_sampler_view(p)->gpu : NULL;}
static void p_atomic_add(int *count,int delta) {*count+=delta;}
static unsigned released,wrappers_released;
static struct pipe_sampler_view *bound;
static void tegra_sampler_view_destroy(struct pipe_context *,struct pipe_sampler_view *);
static void pipe_resource_reference(struct pipe_resource **p,struct pipe_resource *v) {*p=v;}
static void unref(struct pipe_sampler_view *v) {
    if(v && --v->reference.count==0) {
        if(v->wrapper) {wrappers_released++;tegra_sampler_view_destroy(v->context,v);}
        else {released++;free(v);}
    }
}
static void pipe_sampler_view_reference(struct pipe_sampler_view **p,struct pipe_sampler_view *v) {
    if(*p==v)return;
    if(v)v->reference.count++;
    unref(*p);*p=v;
}
static void gpu_bind(struct pipe_context *ctx,enum pipe_shader_type s,unsigned start,unsigned count,unsigned trailing,bool owned,struct pipe_sampler_view **views) {
    (void)ctx;(void)s;(void)start;(void)trailing;
    struct pipe_sampler_view *v=count ? views[0] : NULL;
    if(owned) {unref(bound);bound=v;}
    else pipe_sampler_view_reference(&bound,v);
}
'''
exercise=r'''
static void trial(bool owned,bool repeat) {
    struct pipe_context gpu={.set_sampler_views=gpu_bind};
    struct tegra_context context={.gpu=&gpu};
    unsigned before=released;
    unsigned wrappers_before=wrappers_released;
    for(unsigned i=0;i<100;i++) {
        struct tegra_sampler_view *v=calloc(1,sizeof(*v));
        v->gpu=calloc(1,sizeof(*v->gpu));
        v->refcount=100000000;v->gpu->reference.count=100000001;
        /* The cache keeps one wrapper ref; transfer gives the binding another. */
        v->base.wrapper=true;v->base.context=&context.base;
        v->base.reference.count=owned ? 2 : 1;
        struct pipe_sampler_view *views[1]={&v->base};
        tegra_set_sampler_views(&context.base,FRAGMENT,0,1,0,owned,views);
        assert(v->base.reference.count==1);
        if(repeat)tegra_set_sampler_views(&context.base,FRAGMENT,0,1,0,false,views);
        tegra_set_sampler_views(&context.base,FRAGMENT,0,0,1,false,NULL);
        struct pipe_sampler_view *cache=&v->base;
        pipe_sampler_view_reference(&cache,NULL);
    }
    assert(bound==NULL && released==before+100);
    assert(wrappers_released==wrappers_before+100);
}
static void full_transfer(void) {
    struct pipe_context gpu={.set_sampler_views=gpu_bind};
    struct tegra_context context={.gpu=&gpu};
    unsigned before=released,wrappers_before=wrappers_released;
    struct tegra_sampler_view *v=calloc(1,sizeof(*v));
    v->gpu=calloc(1,sizeof(*v->gpu));
    v->refcount=100000000;v->gpu->reference.count=100000001;
    v->base.wrapper=true;v->base.context=&context.base;v->base.reference.count=1;
    struct pipe_sampler_view *views[1]={&v->base};
    tegra_set_sampler_views(&context.base,FRAGMENT,0,1,0,true,views);
    assert(wrappers_released==wrappers_before+1 && released==before);
    assert(bound && bound->reference.count==1);
    tegra_set_sampler_views(&context.base,FRAGMENT,0,0,1,false,NULL);
    assert(bound==NULL && released==before+1);
}
int main(void) {
    trial(false,false);trial(false,true);trial(true,false);trial(true,true);
    full_transfer();
    puts("TEGRA_SAMPLER_OWNERSHIP_PASSED borrowed/repeated/transferred/mixed/full-transfer");
}
'''
with tempfile.TemporaryDirectory() as directory:
    src=Path(directory)/'ownership.c';binary=Path(directory)/'ownership'
    src.write_text(fixture+'\n'.join(functions)+exercise)
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Wno-unused-parameter','-Werror',str(src),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
