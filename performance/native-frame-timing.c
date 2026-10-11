// SPDX-License-Identifier: GPL-2.0-only
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <wayland-client.h>
#include <wayland-egl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "xdg-shell.h"
static struct wl_compositor *compositor;
static struct xdg_wm_base *wm;
static struct wl_egl_window *window;
static int configured, width=640, height=480;
static void ping(void *d,struct xdg_wm_base *w,uint32_t serial){(void)d;xdg_wm_base_pong(w,serial);}
static const struct xdg_wm_base_listener wm_listener={ping};
static void global(void*d,struct wl_registry*r,uint32_t id,const char*name,uint32_t version){
 (void)d;(void)version;
 if(!strcmp(name,"wl_compositor")) compositor=wl_registry_bind(r,id,&wl_compositor_interface,1);
 if(!strcmp(name,"xdg_wm_base")) {wm=wl_registry_bind(r,id,&xdg_wm_base_interface,1);xdg_wm_base_add_listener(wm,&wm_listener,NULL);}
}
static void removed(void*d,struct wl_registry*r,uint32_t id){(void)d;(void)r;(void)id;}
static const struct wl_registry_listener registry_listener={global,removed};
static void configure(void*d,struct xdg_surface*s,uint32_t serial){(void)d;xdg_surface_ack_configure(s,serial);configured=1;}
static const struct xdg_surface_listener surface_listener={configure};
static void top_config(void*d,struct xdg_toplevel*t,int32_t w,int32_t h,struct wl_array*states){
 (void)d;(void)t;(void)states;
 if(w>0&&h>0){width=w;height=h;if(window)wl_egl_window_resize(window,w,h,0,0);}
}
static void close_window(void*d,struct xdg_toplevel*t){(void)d;(void)t;exit(0);}
static const struct xdg_toplevel_listener top_listener={.configure=top_config,.close=close_window};
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static int compare_time(const void*a,const void*b){double x=*(const double*)a,y=*(const double*)b;return (x>y)-(x<y);}
int main(int argc,char**argv){
 int fullscreen=argc>1&&!strcmp(argv[1],"--fullscreen");
 struct wl_display*display=wl_display_connect(NULL);
 if(!display){perror("wl_display_connect");return 1;}
 struct wl_registry*registry=wl_display_get_registry(display);
 wl_registry_add_listener(registry,&registry_listener,NULL);wl_display_roundtrip(display);
 if(!wm||!compositor){fprintf(stderr,"Missing compositor/xdg_shell\n");return 1;}
 struct wl_surface*surface=wl_compositor_create_surface(compositor);
 struct xdg_surface*xdg=xdg_wm_base_get_xdg_surface(wm,surface);
 xdg_surface_add_listener(xdg,&surface_listener,NULL);
 struct xdg_toplevel*top=xdg_surface_get_toplevel(xdg);
 xdg_toplevel_add_listener(top,&top_listener,NULL);
 xdg_toplevel_set_title(top,"Mocha native GPU frame timing");
 xdg_toplevel_set_app_id(top,"mocha.frame-timing");
 if(fullscreen)xdg_toplevel_set_fullscreen(top,NULL);
 wl_surface_commit(surface);
 while(!configured&&wl_display_dispatch(display)>=0){}
 window=wl_egl_window_create(surface,width,height);
 EGLDisplay ed=eglGetDisplay((EGLNativeDisplayType)display);
 EGLint major,minor;
 if(!eglInitialize(ed,&major,&minor)){fprintf(stderr,"eglInitialize=%x\n",eglGetError());return 1;}
 eglBindAPI(EGL_OPENGL_ES_API);
 EGLint attrs[]={EGL_SURFACE_TYPE,EGL_WINDOW_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,0,EGL_NONE};
 EGLConfig config;EGLint count;
 eglChooseConfig(ed,attrs,&config,1,&count);
 EGLint ca[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};
 EGLContext ctx=eglCreateContext(ed,config,EGL_NO_CONTEXT,ca);
 EGLSurface es=eglCreateWindowSurface(ed,config,(EGLNativeWindowType)window,NULL);
 if(!eglMakeCurrent(ed,es,es,ctx)){fprintf(stderr,"eglMakeCurrent=%x\n",eglGetError());return 1;}
 eglSwapInterval(ed,1);
 printf("GPU=%s VERSION=%s MODE=%s SIZE=%dx%d\n",glGetString(GL_RENDERER),glGetString(GL_VERSION),fullscreen?"fullscreen":"window",width,height);fflush(stdout);
 const char*requested=getenv("MOCHA_BENCH_FRAMES");
 int frames=requested?atoi(requested):240;
 if(frames<120||frames>36000){fprintf(stderr,"Invalid frame count\n");return 1;}
 const int warmup=120;
 double*times=calloc(frames,sizeof(*times));
 if(!times)return 1;
 double start=0;
 int late=0;
 for(int f=0;f<frames+warmup;f++){
   if(f==warmup)start=now();
   double frame_start=now();
   wl_display_dispatch_pending(display);
   glViewport(0,0,width,height);
   glClearColor((f%120)/119.0f,0.15f,1.0f-(f%120)/119.0f,1.0f);
   glClear(GL_COLOR_BUFFER_BIT);
   if(!eglSwapBuffers(ed,es)){fprintf(stderr,"swap error=%x\n",eglGetError());return 1;}
   if(f>=warmup){times[f-warmup]=(now()-frame_start)*1000.0;if(times[f-warmup]>25.0)late++;}
 }
 double elapsed=now()-start;
 qsort(times,frames,sizeof(*times),compare_time);
 printf("NATIVE_COLOR_FRAMES=%d WARMUP=%d SECONDS=%.3f FPS=%.3f P50_MS=%.3f P95_MS=%.3f P99_MS=%.3f OVER_25MS=%d\n",frames,warmup,elapsed,frames/elapsed,times[frames/2],times[frames*95/100],times[frames*99/100],late);fflush(stdout);
 free(times);
 eglMakeCurrent(ed,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
 eglDestroySurface(ed,es);eglDestroyContext(ed,ctx);eglTerminate(ed);
 wl_egl_window_destroy(window);xdg_toplevel_destroy(top);xdg_surface_destroy(xdg);
 wl_surface_destroy(surface);wl_display_disconnect(display);
 return 0;
}
