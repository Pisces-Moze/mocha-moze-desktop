#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Manual touch keyboard using Fcitx's documented virtual keyboard D-Bus API.

Layer-shell keeps application focus. Fcitx handles Pinyin and commits text to
native text-input clients; English shortcuts use the virtual-keyboard fallback.
No key events, preedit, candidate text or passwords are written to logs/files.
"""
import atexit, json, os, re, signal, subprocess, time
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
from gi.repository import Gtk, Gdk, Gio, GLib, GtkLayerShell

FCITX='org.fcitx.Fcitx5'
BACKEND='org.fcitx.Fcitx5.VirtualKeyboardBackend'
UI='org.fcitx.Fcitx5.VirtualKeyboard'
INTERFACE='org.fcitx.Fcitx5.VirtualKeyboard1'
XML='''<node><interface name="org.fcitx.Fcitx5.VirtualKeyboard1">
<method name="ShowVirtualKeyboard"/><method name="HideVirtualKeyboard"/>
<method name="UpdatePreeditCaret"><arg type="i" direction="in"/></method>
<method name="UpdatePreeditArea"><arg type="s" direction="in"/></method>
<method name="UpdateCandidateArea"><arg type="as" direction="in"/><arg type="b" direction="in"/><arg type="b" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="NotifyIMActivated"><arg type="s" direction="in"/></method>
<method name="NotifyIMDeactivated"><arg type="s" direction="in"/></method>
<method name="NotifyIMListChanged"/></interface></node>'''

class Keyboard:
    def __init__(self):
        self.shift=False; self.symbols=False; self.ctrl=False
        self.visibility_file = Path(os.environ['XDG_RUNTIME_DIR']) / 'mocha-keyboard-visible.json'
        self.last_visibility = None
        self.visibility_pending = 0
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.window=Gtk.Window(title='Mocha 中文触屏键盘')
        self.window.set_accept_focus(False)
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window,'mocha-touch-keyboard')
        # Stay above Top panels; Overlay panel shields also exclude the live
        # rectangles published below. NONE keeps the text input focused.
        GtkLayerShell.set_layer(self.window,GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self.window,GtkLayerShell.KeyboardMode.NONE)
        for edge in (GtkLayerShell.Edge.BOTTOM,GtkLayerShell.Edge.LEFT,GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self.window,edge,True)
        GtkLayerShell.auto_exclusive_zone_enable(self.window)
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        self.box.set_border_width(8)
        self.window.add(self.box)
        self.candidates=Gtk.Box(spacing=6)
        self.candidate_window=Gtk.Window(title='Mocha 拼音候选')
        self.candidate_window.set_accept_focus(False)
        GtkLayerShell.init_for_window(self.candidate_window)
        GtkLayerShell.set_namespace(self.candidate_window,'mocha-pinyin-candidates')
        GtkLayerShell.set_layer(self.candidate_window,GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self.candidate_window,GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_anchor(self.candidate_window,GtkLayerShell.Edge.BOTTOM,True)
        GtkLayerShell.set_margin(self.candidate_window,GtkLayerShell.Edge.BOTTOM,280)
        scroller=Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.NEVER)
        scroller.set_kinetic_scrolling(True)
        scroller.set_size_request(620,58)
        self.candidate_scroller=scroller
        self.candidate_swipe=Gtk.GestureSwipe.new(scroller)
        self.candidate_swipe.connect('swipe',lambda _,vx,vy:self.backend('NextPage' if vx<0 else 'PrevPage') if abs(vx)>200 and abs(vx)>abs(vy) else None)
        scroller.add(self.candidates)
        self.candidate_window.add(scroller)
        self.preedit=Gtk.Label(label='拼音')
        self.preedit.set_size_request(90,36)
        self.candidates.pack_start(self.preedit,False,False,0)
        self.candidate_buttons=[]
        for index in range(5):
            button=self.button('',lambda _,i=index:self.backend('SelectCandidate',GLib.Variant('(i)',(i,))))
            button.set_no_show_all(True);button.hide()
            self.candidates.pack_start(button,True,True,0)
            self.candidate_buttons.append(button)
        for label,method in [('‹','PrevPage'),('›','NextPage')]:
            self.candidates.pack_start(self.button(label,lambda _,m=method:self.backend(m)),False,False,0)
        self.keys=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.box.pack_start(self.keys,True,True,0)
        self.build_keys()
        self.css=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.css,Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.theme_directory=Path.home()/'.config/gtk-3.0'
        self.theme_pending=0
        self.theme_colors=None
        self.reload_theme()
        # Monitor the directory because Nyxuri replaces these files atomically.
        # Palette changes cause one CSS update; there is no per-frame polling.
        self.theme_monitor=Gio.File.new_for_path(str(self.theme_directory)).monitor_directory(Gio.FileMonitorFlags.NONE,None)
        self.theme_monitor.connect('changed',self.theme_changed)
        self.window.connect('destroy',Gtk.main_quit)
        for window in (self.window,self.candidate_window):
            for event in ('size-allocate','map','unmap'):
                window.connect(event,self.queue_visibility)
        self.registration=self.bus.register_object('/org/fcitx/virtualkeyboard/impanel',Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0],self.method,None,None)
        self.owner=Gio.bus_own_name_on_connection(self.bus,UI,Gio.BusNameOwnerFlags.NONE,None,None)
        self.window.show_all()
        self.record_visibility(True)
        atexit.register(self.record_visibility,False)
        GLib.timeout_add(250,self.show_fcitx)
        signal.signal(signal.SIGUSR1,lambda *_:GLib.idle_add(self.visible,False))
        signal.signal(signal.SIGUSR2,lambda *_:GLib.idle_add(self.visible,True))
        signal.signal(signal.SIGRTMIN,lambda *_:GLib.idle_add(self.visible,not self.window.get_visible()))
        for signum in (signal.SIGTERM,signal.SIGINT):
            signal.signal(signum,lambda *_:GLib.idle_add(Gtk.main_quit))

    def theme_changed(self,monitor,file,other,event):
        if file.get_basename() not in ('gtk.css','settings.ini'):
            return
        if self.theme_pending:
            GLib.source_remove(self.theme_pending)
        self.theme_pending=GLib.timeout_add(120,self.reload_theme)

    def reload_theme(self):
        self.theme_pending=0
        try:
            source=(self.theme_directory/'gtk.css').read_text()
        except OSError:
            source=''
        colors=dict(re.findall(r'@define-color\s+(\w+)\s+(#[0-9a-fA-F]{6})\s*;',source))
        palette=tuple(colors.get(name,default) for name,default in (
            ('theme_bg_color','#161a23'),('theme_fg_color','#e4e9f5'),
            ('insensitive_base_color','#283044'),('theme_unfocused_selected_bg_color','#374761'),
            ('theme_unfocused_selected_fg_color','#e4e9f5'),
            ('theme_selected_bg_color','#b6c7e7'),('theme_selected_fg_color','#161a23')))
        if palette==self.theme_colors:
            return False
        bg,fg,key,special,special_fg,pressed,pressed_fg=palette
        self.css.load_from_data(('''
            window { background: %s; color: %s; }
            button { background-image: none; background-color: %s; color: %s;
                box-shadow: none; text-shadow: none; outline-style: none;
                border: 0; border-radius: 8px; transition: none;
                font-family: "Noto Sans CJK SC", "Noto Sans Symbols 2";
                font-size: 22px; min-height: 48px; padding: 4px 8px; }
            button.special { background-color: %s; color: %s; }
            button:active, button.special:active { background-color: %s; color: %s; }
            label { font-family: "Noto Sans CJK SC"; font-size: 17px; }
        ''' % (bg,fg,key,fg,special,special_fg,pressed,pressed_fg)).encode())
        self.theme_colors=palette
        return False

    def call(self,name,path,interface,method,params=None):
        return self.bus.call_sync(name,path,interface,method,params,None,Gio.DBusCallFlags.NONE,800,None)

    def backend(self,method,params=None):
        try: self.call(BACKEND,'/virtualkeyboard','org.fcitx.Fcitx5.VirtualKeyboardBackend1',method,params)
        except GLib.Error: self.preedit.set_text('请先点选应用输入框')

    def show_fcitx(self):
        try:
            self.call(FCITX,'/virtualkeyboard','org.fcitx.Fcitx.VirtualKeyboard1','ShowVirtualKeyboard')
            self.backend('SetVirtualKeyboardFunctionMode',GLib.Variant('(u)',(1,)))
        except GLib.Error: self.preedit.set_text('输入法未连接')
        return False

    def visible(self,visible):
        if visible: self.window.show_all();self.show_fcitx()
        else: self.window.hide();self.candidate_window.hide()
        self.record_visibility(visible)
        return False

    def record_visibility(self, visible):
        # Only surface geometry/identity; never input or candidate text.
        state={'pid':os.getpid(),'visible':bool(visible and self.window.get_mapped()),'rects':[]}
        native=self.window.get_window()
        if state['visible'] and native:
            monitor=self.window.get_display().get_monitor_at_window(native)
            g=monitor.get_geometry()
            state['monitor']={'x':g.x,'y':g.y,'width':g.width,'height':g.height}
            for window in (self.window,self.candidate_window):
                if window.get_mapped():
                    state['rects'].append({'width':window.get_allocated_width(),'height':window.get_allocated_height(),
                        'bottom':GtkLayerShell.get_margin(window,GtkLayerShell.Edge.BOTTOM)})
        encoded=json.dumps(state,sort_keys=True)
        if encoded==self.last_visibility:return
        temporary = self.visibility_file.with_suffix('.new')
        temporary.write_text(encoded)
        temporary.chmod(0o600)
        os.replace(temporary, self.visibility_file)
        self.last_visibility=encoded

    def queue_visibility(self,*_):
        if not self.visibility_pending:
            self.visibility_pending=GLib.idle_add(self.flush_visibility)

    def flush_visibility(self):
        self.visibility_pending=0
        self.record_visibility(self.window.get_visible())
        return False

    def method(self,connection,sender,path,interface,method,params,invocation):
        # Only the input framework may supply preedit/candidate updates.
        owner=self.call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',GLib.Variant('(s)',(FCITX,))).unpack()[0]
        if sender!=owner:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied','Fcitx only');return
        values=params.unpack()
        if method=='UpdatePreeditArea': self.preedit.set_text(values[0] or '拼音')
        elif method=='UpdateCandidateArea':
            for index,button in enumerate(self.candidate_buttons):
                if index<len(values[0]): button.set_label(values[0][index]);button.show()
                else: button.hide()
            if values[0] and self.window.get_visible():self.candidate_window.show_all()
            else:self.candidate_window.hide()
            # A new composition/page must start at candidate zero, rather than
            # retaining the previous horizontally scrolled viewport.
            adjustment=self.candidate_scroller.get_hadjustment()
            adjustment.set_value(adjustment.get_lower())
        # Visibility remains manual; focus changes do not open/hide this app.
        invocation.return_value(None)

    def button(self,label,callback):
        button=Gtk.Button(label=label);button.set_can_focus(False)
        button.connect('clicked',callback)
        return button

    def build_keys(self):
        for child in self.keys.get_children():child.destroy()
        grid=Gtk.Grid(column_spacing=5,row_spacing=5)
        grid.set_column_homogeneous(True)
        self.keys.pack_start(grid,True,True,0)
        def add(label,callback,col,row,span=2,special=False):
            button=self.button(label,lambda _,f=callback:f())
            if special:button.get_style_context().add_class('special')
            grid.attach(button,col,row,span,1)
        if self.symbols:
            rows=['1234567890','!@#$%^&*()','_+-=[]{}\\|',':;"\'<>,.?/','`~']
            for row,text in enumerate(rows):
                for col,char in enumerate(text):add(char,lambda c=char:self.key(c),col*2,row)
            last=len(rows)
        else:
            for row,text in enumerate(['qwertyuiop','asdfghjkl','zxcvbnm']):
                offset=0 if row==0 else 1 if row==1 else 3
                for col,char in enumerate(text):
                    label=char.upper() if self.shift else char
                    add(label,lambda c=label:self.key(c),offset+col*2,row)
            add('⇧',self.shift_key,0,2,3,True)
            add('⌫',lambda:self.key('BackSpace'),17,2,3,True)
            last=3
        controls=[('ABC' if self.symbols else '⌨',self.symbol_key,0,2),('中/英',self.toggle_im,2,2),('Ctrl',self.ctrl_key,4,2),('-',lambda:self.key('-'),6,2),(',',lambda:self.key(','),8,2),(' ',lambda:self.key('space'),10,6),('.',lambda:self.key('.'),16,2),('Enter',lambda:self.key('Return'),18,2)]
        for label,callback,col,span in controls:add(label,callback,col,last,span,col in (0,2,4,18))
        self.keys.show_all()

    def shift_key(self): self.shift=not self.shift;self.build_keys()
    def symbol_key(self): self.symbols=not self.symbols;self.build_keys()
    def ctrl_key(self): self.ctrl=not self.ctrl;self.preedit.set_text('Ctrl' if self.ctrl else '拼音')
    def toggle_im(self):
        try:self.call(FCITX,'/controller','org.fcitx.Fcitx.Controller1','Toggle')
        except GLib.Error:self.preedit.set_text('请先点选应用输入框')

    def key(self,label):
        if label=='space' and self.ctrl:self.ctrl=False;self.toggle_im();return
        state=0
        try:state=self.call(FCITX,'/controller','org.fcitx.Fcitx.Controller1','State').unpack()[0]
        except GLib.Error:pass
        if state==2 and not self.ctrl:
            keyval=ord(label) if len(label)==1 else Gdk.keyval_from_name(label)
            stamp=int(time.monotonic()*1000)&0xffffffff
            for released in (False,True):
                self.backend('ProcessKeyEvent',GLib.Variant('(uuubu)',(keyval,0,0,released,stamp)))
        else:
            argv=['wtype']
            if self.ctrl:argv+=['-M','ctrl']
            argv += [label] if len(label)==1 else ['-k',label]
            if self.ctrl:argv+=['-m','ctrl']
            subprocess.run(argv,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
        self.ctrl=False

if __name__=='__main__':
    keyboard=Keyboard()
    Gtk.main()
