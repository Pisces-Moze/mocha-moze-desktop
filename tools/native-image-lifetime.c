/* SPDX-License-Identifier: GPL-2.0-only */
/* Offscreen import/sample/destruction only; no modeset or framebuffer writes. */
#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <gbm.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static void sample(unsigned n) {
 FILE *f=fopen("/sys/kernel/debug/dma_buf/bufinfo","r");assert(f);
 char l[256];while(fgets(l,sizeof(l),f))if(strstr(l," objects,"))printf("cycles=%u %s",n,l);
 fclose(f);fflush(stdout);
}
int main(int argc,char **argv) {
 assert(argc==2);int fd=open(argv[1],O_RDWR|O_CLOEXEC);assert(fd>=0);
 struct gbm_device *g=gbm_create_device(fd);assert(g);
 PFNEGLGETPLATFORMDISPLAYEXTPROC platform=(void *)eglGetProcAddress("eglGetPlatformDisplayEXT");
 PFNEGLCREATEIMAGEKHRPROC create=(void *)eglGetProcAddress("eglCreateImageKHR");
 PFNEGLDESTROYIMAGEKHRPROC destroy=(void *)eglGetProcAddress("eglDestroyImageKHR");
 PFNGLEGLIMAGETARGETTEXTURE2DOESPROC target=(void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");
 assert(platform&&create&&destroy&&target);
 EGLDisplay d=platform(EGL_PLATFORM_GBM_KHR,g,NULL);assert(eglInitialize(d,NULL,NULL));
 assert(eglBindAPI(EGL_OPENGL_ES_API));
 EGLint attrs[]={EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_SURFACE_TYPE,EGL_WINDOW_BIT,EGL_NONE};
 EGLConfig config;EGLint count;assert(eglChooseConfig(d,attrs,&config,1,&count)&&count);
 EGLint ca[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};
 EGLContext c=eglCreateContext(d,config,EGL_NO_CONTEXT,ca);assert(c!=EGL_NO_CONTEXT);
 assert(eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,c));
 const char *vs="attribute vec2 pos;varying vec2 uv;void main(){uv=(pos+1.0)*0.5;gl_Position=vec4(pos,0,1);}";
 const char *fs="precision mediump float;varying vec2 uv;uniform sampler2D img;void main(){gl_FragColor=texture2D(img,uv);}";
 GLuint v=glCreateShader(GL_VERTEX_SHADER),f=glCreateShader(GL_FRAGMENT_SHADER);
 glShaderSource(v,1,&vs,NULL);glCompileShader(v);glShaderSource(f,1,&fs,NULL);glCompileShader(f);
 GLuint program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glBindAttribLocation(program,0,"pos");glLinkProgram(program);
 GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);assert(ok);glUseProgram(program);
 GLfloat vertices[]={-1,-1,1,-1,0,1};glVertexAttribPointer(0,2,GL_FLOAT,0,0,vertices);glEnableVertexAttribArray(0);
 glViewport(0,0,128,128);
 for(unsigned i=1;i<=384;i++) {
  struct gbm_bo *bo=gbm_bo_create(g,128,128,GBM_FORMAT_XRGB8888,GBM_BO_USE_SCANOUT|GBM_BO_USE_RENDERING|GBM_BO_USE_LINEAR);assert(bo);
  int dma=gbm_bo_get_fd(bo);assert(dma>=0);
  EGLint ia[]={EGL_WIDTH,128,EGL_HEIGHT,128,EGL_LINUX_DRM_FOURCC_EXT,GBM_FORMAT_XRGB8888,EGL_DMA_BUF_PLANE0_FD_EXT,dma,EGL_DMA_BUF_PLANE0_OFFSET_EXT,0,EGL_DMA_BUF_PLANE0_PITCH_EXT,gbm_bo_get_stride(bo),EGL_NONE};
  EGLImageKHR image=create(d,EGL_NO_CONTEXT,EGL_LINUX_DMA_BUF_EXT,NULL,ia);assert(image!=EGL_NO_IMAGE_KHR);
  close(dma);
  GLuint tex;glGenTextures(1,&tex);glBindTexture(GL_TEXTURE_2D,tex);target(GL_TEXTURE_2D,image);assert(glGetError()==GL_NO_ERROR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
  GLuint output,frame;glGenTextures(1,&output);glBindTexture(GL_TEXTURE_2D,output);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,128,128,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  glGenFramebuffers(1,&frame);glBindFramebuffer(GL_FRAMEBUFFER,frame);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,output,0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
  glBindTexture(GL_TEXTURE_2D,tex);glDrawArrays(GL_TRIANGLES,0,3);glFinish();assert(glGetError()==GL_NO_ERROR);
  glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&frame);glDeleteTextures(1,&output);
  glBindTexture(GL_TEXTURE_2D,0);glDeleteTextures(1,&tex);assert(destroy(d,image));gbm_bo_destroy(bo);glFinish();
  if(i%128==0)sample(i);
 }
 assert(eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT));
 assert(eglDestroyContext(d,c));eglTerminate(d);gbm_device_destroy(g);close(fd);sample(0);
 puts("IMAGE_LIFETIME_COMPLETED");
}
