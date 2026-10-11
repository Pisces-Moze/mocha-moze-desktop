// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <gbm.h>
#include <fcntl.h>
#include <dirent.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL line=%d EGL=0x%x GL=0x%x\n",__LINE__,eglGetError(),glGetError()); return 1; } } while(0)
static int fd_count(void) { DIR *d=opendir("/proc/self/fd"); int n=0; struct dirent *e; while((e=readdir(d))) if(e->d_name[0]!='.') n++; closedir(d); return n; }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9; }
int main(int argc, char **argv) {
 if (argc != 2) { fprintf(stderr,"usage: %s /dev/dri/renderDTEGRA\n",argv[0]); return 2; }
 int dev=open(argv[1],O_RDWR|O_CLOEXEC); CHECK(dev>=0);
 struct gbm_device *gbm=gbm_create_device(dev); CHECK(gbm);
 PFNEGLGETPLATFORMDISPLAYEXTPROC display=(void*)eglGetProcAddress("eglGetPlatformDisplayEXT"); CHECK(display);
 EGLDisplay d=display(EGL_PLATFORM_GBM_KHR,gbm,NULL); CHECK(eglInitialize(d,NULL,NULL));
 const char *ext=eglQueryString(d,EGL_EXTENSIONS); CHECK(ext);
 printf("native_fence=%d wait_sync=%d\n",strstr(ext,"EGL_ANDROID_native_fence_sync")!=NULL,strstr(ext,"EGL_KHR_wait_sync")!=NULL);
 CHECK(strstr(ext,"EGL_ANDROID_native_fence_sync"));
 EGLint attrs[]={EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_SURFACE_TYPE,0,EGL_NONE}; EGLConfig config; EGLint n;
 CHECK(eglChooseConfig(d,attrs,&config,1,&n)&&n>0); CHECK(eglBindAPI(EGL_OPENGL_ES_API));
 EGLint ca[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE}; EGLContext c=eglCreateContext(d,config,EGL_NO_CONTEXT,ca); CHECK(c!=EGL_NO_CONTEXT);
 CHECK(eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,c)); printf("renderer=%s\n",glGetString(GL_RENDERER));
 PFNEGLCREATESYNCKHRPROC create=(void*)eglGetProcAddress("eglCreateSyncKHR");
 PFNEGLDESTROYSYNCKHRPROC destroy=(void*)eglGetProcAddress("eglDestroySyncKHR");
 PFNEGLDUPNATIVEFENCEFDANDROIDPROC dupfd=(void*)eglGetProcAddress("eglDupNativeFenceFDANDROID");
 PFNEGLCLIENTWAITSYNCKHRPROC clientwait=(void*)eglGetProcAddress("eglClientWaitSyncKHR");
 PFNEGLWAITSYNCKHRPROC serverwait=(void*)eglGetProcAddress("eglWaitSyncKHR"); CHECK(create&&destroy&&dupfd&&clientwait&&serverwait);
 GLuint tex,fbo; glGenTextures(1,&tex); glBindTexture(GL_TEXTURE_2D,tex); glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,2048,2048,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 glGenFramebuffers(1,&fbo); glBindFramebuffer(GL_FRAMEBUFFER,fbo); glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,tex,0); CHECK(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
 int initial=-1,pending=0; double export_time=0; EGLint none[]={EGL_NONE};
 for(int i=0;i<80;i++) {
  for(int j=0;j<(i==0?256:16);j++) { glClearColor((j&1)?1:0,0,1,1); glClear(GL_COLOR_BUFFER_BIT); }
  glClearColor(0,1,0,1); glClear(GL_COLOR_BUFFER_BIT);
  EGLSyncKHR out=create(d,EGL_SYNC_NATIVE_FENCE_ANDROID,none); CHECK(out!=EGL_NO_SYNC_KHR); glFlush();
  double t=now(); int fd=dupfd(d,out); export_time+=now()-t; CHECK(fd>=0);
  struct pollfd p={.fd=fd,.events=POLLIN}; CHECK(poll(&p,1,0)>=0); if(!(p.revents&POLLIN)) pending++;
  int other=dup(fd); CHECK(other>=0); EGLint ia[]={EGL_SYNC_NATIVE_FENCE_FD_ANDROID,other,EGL_NONE};
  EGLSyncKHR in=create(d,EGL_SYNC_NATIVE_FENCE_ANDROID,ia); CHECK(in!=EGL_NO_SYNC_KHR);
  CHECK(clientwait(d,in,0,0)==EGL_TIMEOUT_EXPIRED_KHR || (p.revents&POLLIN) || clientwait(d,in,0,0)==EGL_CONDITION_SATISFIED_KHR);
  CHECK(serverwait(d,in,0)); CHECK(clientwait(d,in,0,1000000000ULL)==EGL_CONDITION_SATISFIED_KHR);
  CHECK(poll(&p,1,1000)==1 && (p.revents&POLLIN));
  CHECK(destroy(d,in)); CHECK(destroy(d,out)); close(fd);
  unsigned char pixel[4]; glReadPixels(1024,1024,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel); CHECK(pixel[0]==0&&pixel[1]==255&&pixel[2]==0&&pixel[3]==255); CHECK(glGetError()==GL_NO_ERROR);
  if(i==4) initial=fd_count();
 }
 int final=fd_count(); CHECK(final==initial); CHECK(pending>0);
 printf("PASS exports=80 imports=80 pending=%d export_mean_ms=%.3f fd_baseline=%d fd_final=%d pixel=0,255,0,255\n",pending,export_time/80*1000,initial,final);
 glDeleteFramebuffers(1,&fbo); glDeleteTextures(1,&tex); eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT); eglDestroyContext(d,c); eglTerminate(d); gbm_device_destroy(gbm); close(dev); return 0;
}
