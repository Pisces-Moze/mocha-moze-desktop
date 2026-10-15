#define _GNU_SOURCE
#include <cairo.h>
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/kd.h>
#include <linux/vt.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

/* Independent charging UI. No GPU render/readback and no desktop process.
 * Only the central icon region is refreshed; the panel sleeps after 15 s.
 * Exit 10 requests desktop boot; exit 20 requests poweroff. */
#define W 720
#define H 520
static volatile sig_atomic_t stop;
static bool net_charging=true;
static unsigned rotation;
static void interrupted(int signal_number) { (void)signal_number;stop=1; }
static double now(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9; }
static int read_int(const char *path, int fallback) { FILE *f=fopen(path,"r");int n=fallback;if(f){if(fscanf(f,"%d",&n)!=1)n=fallback;fclose(f);}return n; }
static bool power_held(int fd) {
 unsigned char keys[(KEY_MAX+8)/8]={0};
 return fd>=0&&!ioctl(fd,EVIOCGKEY(sizeof(keys)),keys)&&
        (keys[KEY_POWER/8]&(1u<<(KEY_POWER%8)));
}
static void write_int(const char *path,int n) { FILE *f=fopen(path,"w");if(f){fprintf(f,"%d\n",n);fclose(f);} }
static void round_rect(cairo_t *c,double x,double y,double w,double h,double r) {
 cairo_new_sub_path(c);cairo_arc(c,x+w-r,y+r,r,-M_PI/2,0);cairo_arc(c,x+w-r,y+h-r,r,0,M_PI/2);
 cairo_arc(c,x+r,y+h-r,r,M_PI/2,M_PI);cairo_arc(c,x+r,y+r,r,M_PI,3*M_PI/2);cairo_close_path(c);
}
static void text(cairo_t *c,const char *s,double size,double y,double alpha) {
 cairo_select_font_face(c,"sans-serif",CAIRO_FONT_SLANT_NORMAL,CAIRO_FONT_WEIGHT_NORMAL);
 cairo_set_font_size(c,size);cairo_text_extents_t e;cairo_text_extents(c,s,&e);
 cairo_set_source_rgba(c,1,1,1,alpha);cairo_move_to(c,(W-e.width)/2-e.x_bearing,y);cairo_show_text(c,s);
}
static cairo_surface_t *render(int percent,bool online,double pulse) {
 cairo_surface_t *s=cairo_image_surface_create(CAIRO_FORMAT_RGB24,W,H);cairo_t *c=cairo_create(s);
 cairo_set_source_rgb(c,0,0,0);cairo_paint(c);
 double r=percent<10?.96:.20,g=percent<10?.30:.88,b=percent<10?.32:.48;
 if(!online){r=.60;g=.60;b=.65;}
 cairo_pattern_t *glow=cairo_pattern_create_radial(W/2,202,0,W/2,202,210);
 cairo_pattern_add_color_stop_rgba(glow,0,r,g,b,.13+.04*pulse);
 cairo_pattern_add_color_stop_rgba(glow,.55,r,g,b,.045);
 cairo_pattern_add_color_stop_rgba(glow,1,0,0,0,0);
 cairo_set_source(c,glow);cairo_rectangle(c,100,0,520,385);cairo_fill(c);cairo_pattern_destroy(glow);
 round_rect(c,194,142,316,134,28);cairo_set_source_rgba(c,1,1,1,.34);cairo_set_line_width(c,5);cairo_stroke(c);
 round_rect(c,522,182,12,54,5);cairo_set_source_rgba(c,1,1,1,.30);cairo_fill(c);
 round_rect(c,206,154,292,110,18);cairo_set_source_rgba(c,1,1,1,.055);cairo_fill(c);
 cairo_save(c);round_rect(c,206,154,292,110,18);cairo_clip(c);
 double fill=292*fmax(.055,fmin(1,percent/100.));
 cairo_pattern_t *p=cairo_pattern_create_linear(206,154,206,264);
 cairo_pattern_add_color_stop_rgb(p,0,fmin(1,r+.12),fmin(1,g+.07),fmin(1,b+.08));
 cairo_pattern_add_color_stop_rgb(p,1,r*.77,g*.86,b*.88);cairo_set_source(c,p);
 cairo_rectangle(c,206,154,fill,110);cairo_fill(c);cairo_pattern_destroy(p);cairo_restore(c);
 if(online){
  cairo_move_to(c,368,171);cairo_line_to(c,342,211);cairo_line_to(c,363,211);
  cairo_line_to(c,352,246);cairo_line_to(c,385,202);cairo_line_to(c,364,202);cairo_close_path(c);
  cairo_set_source_rgba(c,1,1,1,.94);cairo_fill(c);
 }
 char label[32];if(percent>=0)snprintf(label,sizeof(label),"%d%%",percent);else snprintf(label,sizeof(label),"—");
 text(c,label,58,355,.96);text(c,online?(percent>=100?"Charged":(net_charging?"Charging":"Power connected")):"Disconnected",22,399,.58);
 text(c,percent<5?"Power on after the battery reaches 5%":"Hold the power button to start",15,468,.30);
 cairo_destroy(c);cairo_surface_flush(s);return s;
}
static double bezier(double progress) {
 /* animate skill's ease-out: cubic-bezier(.23,1,.32,1). */
 double lo=0,hi=1,t=.5;
 for(int i=0;i<14;i++){t=(lo+hi)/2;double u=1-t;double x=3*u*u*t*.23+3*u*t*t*.32+t*t*t;if(x<progress)lo=t;else hi=t;}
 return 1-pow(1-t,3);
}
static uint32_t channel(unsigned byte,struct fb_bitfield field) {
 return field.length?((byte*((1u<<field.length)-1)+127)/255)<<field.offset:0;
}
static uint8_t *pack(const struct fb_var_screeninfo *v,cairo_surface_t *surface,double opacity,double scale) {
 const uint32_t *src=(const uint32_t *)cairo_image_surface_get_data(surface);
 unsigned bytes=v->bits_per_pixel/8;uint8_t *packed=calloc(W*H,bytes);if(!packed)return NULL;
 uint32_t red[256],green[256],blue[256],alpha=channel(255,v->transp);int columns[W],rows[H];
 for(unsigned i=0;i<256;i++){
  unsigned level=(unsigned)(i*opacity);
  red[i]=channel(level,v->red);green[i]=channel(level,v->green);blue[i]=channel(level,v->blue);
 }
 for(int x=0;x<W;x++)columns[x]=(int)((x-W/2)/scale+W/2);
 for(int y=0;y<H;y++)rows[y]=(int)((y-H/2)/scale+H/2);
 for(int y=0;y<H;y++)for(int x=0;x<W;x++){
  int sx=columns[x],sy=rows[y];uint32_t rgb=0;
  if(sx>=0&&sx<W&&sy>=0&&sy<H)rgb=src[sy*W+sx];
  uint32_t pixel=red[(rgb>>16)&255]|green[(rgb>>8)&255]|blue[rgb&255]|alpha;
  memcpy(packed+((size_t)y*W+x)*bytes,&pixel,bytes);
 }
 return packed;
}
static void frame_point(unsigned angle,int width,int height,int x,int y,int *px,int *py) {
 int rw=(angle==90||angle==270)?H:W,rh=(angle==90||angle==270)?W:H;
 int ox=(width-rw)/2,oy=(height-rh)/2;
 switch(angle){
  case 90: *px=ox+H-1-y;*py=oy+x;break;
  case 180:*px=ox+W-1-x;*py=oy+H-1-y;break;
  case 270:*px=ox+y;*py=oy+W-1-x;break;
  default:*px=ox+x;*py=oy+y;break;
 }
}
static void present(uint8_t *fb,const struct fb_fix_screeninfo *fix,const struct fb_var_screeninfo *v,const uint8_t *packed) {
 unsigned bytes=v->bits_per_pixel/8;int px=((int)v->xres-W)/2,py=((int)v->yres-H)/2;
 if(rotation){
  for(int y=0;y<H;y++)for(int x=0;x<W;x++){
   int tx,ty;frame_point(rotation,v->xres,v->yres,x,y,&tx,&ty);
   size_t offset=(size_t)(ty+v->yoffset)*fix->line_length+(tx+v->xoffset)*bytes;
   if(offset+bytes<=fix->smem_len)memcpy(fb+offset,packed+((size_t)y*W+x)*bytes,bytes);
  }
  return;
 }
 for(int row=0;row<H;row++){
  size_t offset=(size_t)(py+row+v->yoffset)*fix->line_length+(px+v->xoffset)*bytes;
  if(offset+(size_t)W*bytes<=fix->smem_len)memcpy(fb+offset,packed+(size_t)row*W*bytes,W*bytes);
 }
}
static void hold_progress(uint8_t *fb,const struct fb_fix_screeninfo *fix,const struct fb_var_screeninfo *v,double progress) {
 unsigned bytes=v->bits_per_pixel/8;
 for(int y=490;y<494;y++)for(int x=W/2-96;x<W/2+96;x++){
  unsigned level=(x-W/2+96)<192*progress?215:24;
  if(progress<0)level=0;
  uint32_t pixel=channel(level,v->red)|channel(level,v->green)|channel(level,v->blue)|channel(255,v->transp);
  int px,py;frame_point(rotation,v->xres,v->yres,x,y,&px,&py);
  size_t offset=(size_t)(py+v->yoffset)*fix->line_length+(px+v->xoffset)*bytes;
  if(offset+bytes<=fix->smem_len)memcpy(fb+offset,&pixel,bytes);
 }
}
struct frames {uint8_t *entry[15],*pulse[24],*exit[15],*base;cairo_surface_t *surface;unsigned prepared;};
static void free_frames(struct frames *f) {
 for(int i=0;i<15;i++){free(f->entry[i]);free(f->exit[i]);}for(int i=0;i<24;i++)free(f->pulse[i]);
 free(f->base);if(f->surface)cairo_surface_destroy(f->surface);memset(f,0,sizeof(*f));
}
static bool cache_frames(struct frames *f,const struct fb_var_screeninfo *v,int percent,bool online) {
 free_frames(f);f->surface=render(percent,online,0);f->base=pack(v,f->surface,1,1);
 return f->base!=NULL;
}
static bool prepare_frame(struct frames *f,const struct fb_var_screeninfo *v,int percent,bool online,bool reduced) {
 /* One frame per event-loop iteration: never hide cable/key events behind
  * a synchronous 55-frame cache rebuild on the powersave CPU governor. */
 unsigned index=f->prepared;uint8_t **target;
 if(index>=54)return true;
 if(index<15){double e=bezier(index/14.);target=&f->entry[index];*target=pack(v,f->surface,e,reduced?1:.95+.05*e);}
 else if(index<30){double e=bezier((index-15)/14.);target=&f->exit[index-15];*target=pack(v,f->surface,1-e,1);}
 else {unsigned phase=index-30;target=&f->pulse[phase];
  cairo_surface_t *s=render(percent,online,reduced?0:(1-cos(phase*2*M_PI/24))/2);
  *target=pack(v,s,1,1);cairo_surface_destroy(s);
 }
 if(!*target)return false;
 f->prepared++;return true;
}
int main(int argc,char **argv) {
 if(argc==3&&!strcmp(argv[1],"--snapshot")){
  cairo_surface_t *s=render(67,true,.5);int code=cairo_surface_write_to_png(s,argv[2]);cairo_surface_destroy(s);return code!=CAIRO_STATUS_SUCCESS;
 }
 bool preview=argc==2&&!strcmp(argv[1],"--preview"),live=argc==2&&!strcmp(argv[1],"--live");
 const char *angle=getenv("MOCHA_CHARGER_TRANSFORM");
 if(angle){
  if(!strcmp(angle,"90"))rotation=90;
  else if(!strcmp(angle,"180"))rotation=180;
  else if(!strcmp(angle,"270"))rotation=270;
  else if(strcmp(angle,"0")){fprintf(stderr,"unsupported charger transform\n");return 2;}
 }
 bool reduced=getenv("MOCHA_REDUCED_MOTION")&&!strcmp(getenv("MOCHA_REDUCED_MOTION"),"1");
 if(!preview&&!live){fprintf(stderr,"usage: %s --snapshot FILE | --preview | --live\n",argv[0]);return 2;}
 int fbfd=open("/dev/fb0",O_RDWR|O_CLOEXEC);struct fb_fix_screeninfo fix;struct fb_var_screeninfo v;
 if(fbfd<0||ioctl(fbfd,FBIOGET_FSCREENINFO,&fix)||ioctl(fbfd,FBIOGET_VSCREENINFO,&v)){perror("framebuffer");return 2;}
 bool sideways=rotation==90||rotation==270;
 if((v.bits_per_pixel!=16&&v.bits_per_pixel!=32)||v.xres<(sideways?H:W)||v.yres<(sideways?W:H)){fprintf(stderr,"unsupported framebuffer\n");return 2;}
 uint8_t *fb=mmap(NULL,fix.smem_len,PROT_READ|PROT_WRITE,MAP_SHARED,fbfd,0);
 if(fb==MAP_FAILED){perror("framebuffer map");return 2;}
 uint8_t *saved=NULL;if(preview){saved=malloc(fix.smem_len);if(!saved)return 2;memcpy(saved,fb,fix.smem_len);}
 int tty=open("/dev/tty1",O_RDWR|O_CLOEXEC);int old_mode=KD_TEXT;
 if(tty>=0){ioctl(tty,KDGETMODE,&old_mode);ioctl(tty,KDSETMODE,KD_TEXT);ioctl(tty,VT_ACTIVATE,1);ioctl(tty,VT_WAITACTIVE,1);ioctl(fbfd,FBIOBLANK,FB_BLANK_UNBLANK);ioctl(tty,KDSETMODE,KD_GRAPHICS);}
 const char *charger="/sys/class/power_supply/bq24190-charger/online";
 const char *capacity="/sys/class/power_supply/bq27520g4-0/capacity";
 glob_t backlights={0};glob("/sys/class/backlight/mocha-miui-backlight/brightness",0,NULL,&backlights);
 const char *brightness=backlights.gl_pathc?backlights.gl_pathv[0]:NULL;
 int old_brightness=brightness?read_int(brightness,100):100;
 if(live&&brightness)write_int(brightness,60);
 int input=-1;if(live){glob_t inputs={0};glob("/dev/input/event*",0,NULL,&inputs);
  for(size_t i=0;i<inputs.gl_pathc;i++){int fd=open(inputs.gl_pathv[i],O_RDONLY|O_NONBLOCK|O_CLOEXEC);char name[128]={0};
   if(fd>=0&&ioctl(fd,EVIOCGNAME(sizeof(name)),name)>=0&&!strcmp(name,"gpio-keys")){input=fd;break;}if(fd>=0)close(fd);
  }globfree(&inputs);
 }
 if(live&&power_held(input)&&read_int(capacity,-1)>=5){
  if(brightness)write_int(brightness,old_brightness);
  if(tty>=0){ioctl(tty,KDSETMODE,old_mode);close(tty);}
  close(input);globfree(&backlights);munmap(fb,fix.smem_len);close(fbfd);
  fprintf(stderr,"CHARGER_UI_EXIT=10 initial_power_held=1\n");return 10;
 }
 signal(SIGINT,interrupted);signal(SIGTERM,interrupted);
 memset(fb,0,fix.smem_len);double started=now(),shown=started,hide_at=started+15,next_status=0,pressed=0,offline=0,next_frame=started,reveal_at=0;
 int reveal_from=0;
 int percent=-1,last_percent=-2,result=0;bool online=true,last_online=false,blank=false,last_charging=false;
 struct frames cached={0};unsigned frames=0;const uint8_t *last_frame=NULL;
 while(!stop){
  double t=now();if(preview&&t-started>8)break;
  if(t>=next_status){percent=read_int(capacity,-1);online=read_int(charger,0)>0;
   net_charging=read_int("/sys/class/power_supply/bq27520g4-0/current_now",-1)>0;next_status=t+.25;
   bool reconnected=online&&offline;
   if(!online){if(!offline)offline=t;}else offline=0;
   if(live&&offline&&t-offline>8){result=20;break;}
   if(live&&reconnected){
    /* A cable insertion must reveal the charge UI even after its timeout. */
    shown=t;hide_at=t+15;next_frame=t;reveal_at=0;blank=false;last_frame=NULL;
    memset(fb,0,fix.smem_len);if(brightness)write_int(brightness,60);
   }
   if(!blank&&(!cached.base||percent!=last_percent||online!=last_online||net_charging!=last_charging)){
    double cache_started=now();
    if(!cache_frames(&cached,&v,percent,online)){result=2;break;}
    if(frames==0){
     present(fb,&fix,&v,cached.base);frames++;
     fprintf(stderr,"CHARGER_UI_FIRST_PAINT_MS=%.0f\n",(now()-started)*1000);
    }
    fprintf(stderr,"CHARGER_UI_BASE_MS=%.0f\n",(now()-cache_started)*1000);
    last_frame=NULL;last_percent=percent;last_online=online;last_charging=net_charging;
    if(frames==1){shown=now()-.24;next_frame=now();hide_at=now()+15;}
    t=now();
   }
  }
  if(input>=0){struct input_event event;
   while(read(input,&event,sizeof(event))==sizeof(event))if(event.type==EV_KEY&&event.code==KEY_POWER){
    if(event.value==1){pressed=t;
     if(!blank&&t>hide_at-.24){reveal_at=t;reveal_from=0;for(int i=0;i<15;i++)if(last_frame==cached.exit[i])reveal_from=i;}
     hide_at=t+15;
     if(blank){shown=t;blank=false;last_frame=NULL;memset(fb,0,fix.smem_len);if(brightness)write_int(brightness,60);}
    }
    else if(event.value==0)pressed=0;
   }
   if(pressed&&t-pressed>=2&&percent>=5){result=10;break;}
  }
  double age=t-shown;
  if(live&&t>=hide_at&&!blank){if(brightness)write_int(brightness,0);memset(fb,0,fix.smem_len);blank=true;}
  if(!blank){
   if(!prepare_frame(&cached,&v,percent,online,reduced)){result=2;break;}
   const uint8_t *frame=cached.base;
   if(age<.24)frame=cached.entry[(int)fmax(0,fmin(14,age/.24*14))];
   else if(!reduced&&age<6)frame=cached.pulse[(int)(age/2.8*24)%24];
   if(live&&t>hide_at-.24)frame=cached.exit[(int)fmin(14,(t-hide_at+.24)/.24*14)];
   else if(reveal_at&&t-reveal_at<.2)frame=cached.exit[(int)(reveal_from*(1-bezier((t-reveal_at)/.2)))];
   if(!frame)frame=cached.base;
   if(frame!=last_frame){present(fb,&fix,&v,frame);last_frame=frame;frames++;}
   hold_progress(fb,&fix,&v,pressed?fmin(1,(t-pressed)/2):-1);
  }
  next_frame+=blank?.1:1./60;double wait=next_frame-now();if(wait<0){next_frame=now();wait=0;}
  struct timespec delay={(time_t)wait,(long)((wait-floor(wait))*1e9)};nanosleep(&delay,NULL);
 }
 free_frames(&cached);
 if(preview&&saved){memcpy(fb,saved,fix.smem_len);free(saved);}else memset(fb,0,fix.smem_len);
 if(brightness)write_int(brightness,result==10?old_brightness:(preview?old_brightness:0));
 if(tty>=0){ioctl(tty,KDSETMODE,old_mode);close(tty);}if(input>=0)close(input);
 globfree(&backlights);munmap(fb,fix.smem_len);close(fbfd);
 fprintf(stderr,"CHARGER_UI_EXIT=%d frames=%u capacity=%d online=%d\n",result,frames,percent,online);return result;
}
