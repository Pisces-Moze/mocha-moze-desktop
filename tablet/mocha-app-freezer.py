#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Niri policy adapter for systemd's cgroup freezer; no process checkpointing."""
import ctypes
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

from gi.repository import Gio, GLib

LOG=logging.getLogger('mocha-freezer')
UID=os.getuid()
RUNTIME=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{UID}'))/'mocha-freezer'
STATE=RUNTIME/'state.json'
CONFIG=Path.home()/'.config/mocha/memory.json'
PREFIX=f'/user.slice/user-{UID}.slice/user@{UID}.service/app.slice/'
PROTECTED=re.compile(r'niri|noctalia|fcitx|pipewire|wireplumber|portal|dbus|polkit|mocha-|xdg-',re.I)
EXEMPT=re.compile(r'firefox|chrom(e|ium)|brave|vivaldi|kitty|foot|alacritty|terminal|konsole|mpv|vlc|obs|spotify|telegram|discord|signal',re.I)

def config():
    value={'enabled':True,'grace_seconds':60,'pressure_grace_seconds':15,'low_memory_mib':320,
           'opaque_maximized':True,'exclude_app_ids':[]}
    try:value.update(json.loads(CONFIG.read_text()))
    except (OSError,ValueError):pass
    for key in ['grace_seconds','pressure_grace_seconds']:
        value[key]=max(5,min(3600,int(value[key])))
    value['low_memory_mib']=max(128,min(700,int(value['low_memory_mib'])))
    return value

def state():
    try:return json.loads(STATE.read_text())
    except (OSError,ValueError):return {'frozen':{},'scores':{},'opaque':[]}

def proc_unit(pid):
    try:
        p=Path('/proc')/str(int(pid))
        if p.stat().st_uid!=UID:return None
        path=next(l[3:] for l in (p/'cgroup').read_text().splitlines() if l.startswith('0::'))
        if not path.startswith(PREFIX):return None
        leaf=path[len(PREFIX):].split('/')[0]
        if re.fullmatch(r'app-[A-Za-z0-9_@.\\:-]+\.(?:scope|service)',leaf):return leaf
    except (OSError,ValueError,StopIteration):pass
    return None

def group(unit):
    return Path('/sys/fs/cgroup'+PREFIX)/unit

def pids(unit):
    result=set()
    try:
        for p in group(unit).rglob('cgroup.procs'):result.update(map(int,p.read_text().split()))
    except (OSError,ValueError):pass
    return result

def start_time(pid):
    s=Path(f'/proc/{pid}/stat').read_text();return s[s.rfind(')')+2:].split()[19]

def request(message):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(1);s.connect(os.environ['NIRI_SOCKET']);s.sendall(json.dumps(message).encode()+b'\n')
        result=json.loads(s.makefile('rb').readline())
        if 'Err' in result:raise RuntimeError(str(result['Err']))
        return result['Ok']

def toggle_opacity(window):
    request({'Action':{'ToggleWindowRuleOpacity':{'id':int(window)}}})

def systemd(bus,method,unit):
    if not re.fullmatch(r'app-[A-Za-z0-9_@.\\:-]+\.(?:scope|service)',unit):raise ValueError('Not an application unit')
    bus.call_sync('org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager',method,
                  GLib.Variant('(s)',(unit,)),None,Gio.DBusCallFlags.NONE,1500,None)

def restore(bus,owned):
    for unit in owned.get('frozen',{}):
        try:systemd(bus,'ThawUnit',unit)
        except GLib.Error:pass
    for pid,item in owned.get('scores',{}).items():
        try:
            if start_time(pid)==item['start'] and Path(f'/proc/{pid}').stat().st_uid==UID:
                Path(f'/proc/{pid}/oom_score_adj').write_text(str(item['original']))
        except (OSError,ValueError):pass
    current=os.environ.get('NIRI_SOCKET')
    recorded=owned.get('niri_socket')
    if not current and recorded and Path(recorded).is_socket():os.environ['NIRI_SOCKET']=recorded
    for wid in owned.get('opaque',[]) if os.environ.get('NIRI_SOCKET')==recorded else []:
        try:toggle_opacity(wid)
        except (OSError,ValueError,RuntimeError,KeyError):pass

class Policy:
    def __init__(self):
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        restore(self.bus,state())
        self.owned={'frozen':{},'scores':{},'opaque':[],'niri_socket':os.environ.get('NIRI_SOCKET')};self.pending={}
        self.windows=[];self.workspaces=[];self.outputs={};self.clipboard=None;self.overview=False
        self.stream=None;self.buffer=b'';self.refresh_source=None;self.last_snapshot=0;self.connected=False
        RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True);self.save()
        self.clipboard_watcher=None
        if shutil.which('wl-paste'):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGUSR1,self.clipboard_changed)
            # Existing wl-clipboard owns protocol handling. Drain data locally
            # without retaining/logging it; only signal the owner-change event.
            self.clipboard_watcher=subprocess.Popen(['wl-paste','--watch','sh','-c',
                'kill -USR1 "$1"; exec cat >/dev/null','mocha-clipboard',str(os.getpid())],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:LOG.warning('Install wl-clipboard; new freezing disabled until clipboard protection is available')

    def save(self):
        self.owned['memory_cgroup']='memory' in Path('/sys/fs/cgroup/cgroup.controllers').read_text().split()
        self.owned['updated']=time.time()
        tmp=STATE.with_suffix('.new');tmp.write_text(json.dumps(self.owned,indent=2));tmp.replace(STATE)

    def clipboard_changed(self,*_):
        self.clipboard=next((w.get('app_id') for w in self.windows if w.get('is_focused')),None)
        self.evaluate();return True

    def schedule_refresh(self):
        if not self.refresh_source:self.refresh_source=GLib.timeout_add(150,self.refresh)

    def refresh(self):
        self.refresh_source=None
        try:
            self.windows=request('Windows')['Windows'];self.workspaces=request('Workspaces')['Workspaces']
            self.outputs=request('Outputs')['Outputs'];self.last_snapshot=time.monotonic();self.connected=True
            self.evaluate()
        except (OSError,ValueError,RuntimeError,KeyError) as e:
            self.connected=False;LOG.warning('Niri unavailable, releasing applications: %s',e);self.release()
        return False

    def connect(self):
        try:
            self.stream=socket.socket(socket.AF_UNIX);self.stream.connect(os.environ['NIRI_SOCKET'])
            self.stream.sendall(b'"EventStream"\n');self.stream.setblocking(False)
            GLib.io_add_watch(self.stream,GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.read_events)
            self.refresh();return False
        except OSError:
            if self.stream:self.stream.close()
            self.stream=None;return True

    def read_events(self,source,condition):
        if condition&(GLib.IO_HUP|GLib.IO_ERR):
            self.connected=False;self.release();self.stream.close();self.stream=None;GLib.timeout_add_seconds(2,self.connect);return False
        try:
            data=source.recv(65536)
            if not data:return self.read_events(source,GLib.IO_HUP)
            self.buffer+=data
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                event=json.loads(line)
                if 'OverviewOpenedOrClosed' in event:self.overview=bool(event['OverviewOpenedOrClosed'].get('is_open'))
                if 'WindowFocusChanged' in event:
                    target=event['WindowFocusChanged'].get('id')
                    w=next((w for w in self.windows if w['id']==target),None)
                    unit=proc_unit(w['pid']) if w and w.get('pid') else None
                    if unit in self.owned['frozen']:self.thaw(unit);self.save()
                if any(k.startswith(('Window','Workspace','Overview')) for k in event):self.schedule_refresh()
        except BlockingIOError:pass
        except (OSError,ValueError):self.schedule_refresh()
        return True

    def audio_units(self):
        try:
            result=set()
            for kind in ['sink-inputs','source-outputs']:
                p=subprocess.run(['pactl','-f','json','list',kind],capture_output=True,text=True,timeout=1)
                if p.returncode:return None
                for item in json.loads(p.stdout):
                    if str(item.get('corked',False)).lower() not in ['false','no','0']:continue
                    pid=item.get('properties',{}).get('application.process.id')
                    if not pid:return None
                    unit=proc_unit(pid)
                    # Audio in a session/shell unit is already outside our
                    # eligible app-* units; it must not disable all freezing.
                    if unit:result.add(unit)
            return result
        except (OSError,ValueError,subprocess.TimeoutExpired):return None

    def opaque_windows(self,cfg):
        selected=set()
        if cfg['opaque_maximized']:
            for w in self.windows:
                if w.get('is_floating'):continue
                ws=next((x for x in self.workspaces if x['id']==w.get('workspace_id')),None)
                logical=self.outputs.get(ws.get('output'),{}).get('logical') if ws else None
                size=w.get('layout',{}).get('tile_size',[0,0])
                if logical and size[0]>=logical['width']-32 and size[1]>=logical['height']-96:selected.add(w['id'])
        current=set(self.owned['opaque']);live={w['id'] for w in self.windows}
        for wid in selected^current:
            if wid in live:
                try:toggle_opacity(wid)
                except (OSError,ValueError,RuntimeError,KeyError):continue
            if wid in current:current.remove(wid)
            elif wid in selected:current.add(wid)
        self.owned['opaque']=sorted(current&live)

    def thaw(self,unit):
        try:systemd(self.bus,'ThawUnit',unit)
        except GLib.Error as e:
            if group(unit).exists():LOG.warning('Could not thaw %s: %s',unit,e);return
        self.owned['frozen'].pop(unit,None)
        for pid,item in list(self.owned['scores'].items()):
            if item['unit']!=unit:continue
            try:
                if start_time(pid)==item['start']:Path(f'/proc/{pid}/oom_score_adj').write_text(str(item['original']))
            except (OSError,ValueError):pass
            del self.owned['scores'][pid]
        LOG.info('thawed %s',unit)

    def release(self):
        restore(self.bus,self.owned)
        self.owned={'frozen':{},'scores':{},'opaque':[],'niri_socket':os.environ.get('NIRI_SOCKET')};self.pending={};self.save()

    def evaluate(self):
        cfg=config()
        if not cfg['enabled'] or not self.stream:self.release();return True
        if not self.connected:self.refresh();return True
        self.opaque_windows(cfg)
        active={w['id'] for w in self.workspaces if w.get('is_active') or w.get('is_focused')}
        audio=self.audio_units()
        mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()}
        psi=Path('/proc/pressure/memory').read_text().splitlines()[0]
        pressure=mem['MemAvailable']<cfg['low_memory_mib']*1024 or float(psi.split('avg10=')[1].split()[0])>=5
        grace=cfg['pressure_grace_seconds'] if pressure else cfg['grace_seconds']
        units={}
        for w in self.windows:
            if w.get('pid') and (unit:=proc_unit(w['pid'])):units.setdefault(unit,[]).append(w)
        eligible=set()
        brightness=list(Path('/sys/class/backlight').glob('*/actual_brightness'))
        try:screen_off=bool(brightness) and all(int(p.read_text())==0 for p in brightness)
        except (OSError,ValueError):screen_off=False
        clipboard_ok=self.clipboard_watcher is not None and self.clipboard_watcher.poll() is None
        if audio is not None and active and clipboard_ok and not getattr(self,'overview',False):
            for unit,windows in units.items():
                if unit in audio:continue
                if any(w.get('workspace_id') is None or (not screen_off and (w.get('is_focused') or w.get('workspace_id') in active)) or EXEMPT.search(w.get('app_id') or '')
                       or PROTECTED.search(w.get('app_id') or '') or w.get('app_id')==self.clipboard
                       or w.get('app_id') in cfg['exclude_app_ids'] for w in windows):continue
                members=pids(unit)
                try:
                    if not members or any(PROTECTED.search(Path(f'/proc/{p}/comm').read_text()) for p in members):continue
                except OSError:continue
                eligible.add(unit)
        for unit in set(self.owned['frozen'])-eligible:self.thaw(unit)
        now=time.monotonic()
        for unit in set(self.pending)-eligible:self.pending.pop(unit,None)
        for unit in eligible-set(self.owned['frozen']):
            self.pending.setdefault(unit,now)
            if now-self.pending[unit]<grace:continue
            try:
                systemd(self.bus,'FreezeUnit',unit)
                self.owned['frozen'][unit]={'since':time.time(),'apps':sorted({w.get('app_id') for w in units[unit]})}
                for pid in pids(unit):
                    try:
                        node=Path(f'/proc/{pid}/oom_score_adj');original=int(node.read_text())
                        if 0<=original<300:
                            self.owned['scores'][str(pid)]={'start':start_time(pid),'original':original,'unit':unit}
                            node.write_text('300')
                    except (OSError,ValueError):pass
                LOG.info('frozen %s',unit)
            except GLib.Error as e:LOG.warning('Freeze failed %s: %s',unit,e)
        self.owned['eligible']=sorted(eligible);self.owned['available_mib']=mem['MemAvailable']//1024
        self.owned['audio_protection_available']=audio is not None
        self.owned['clipboard_protection_available']=clipboard_ok
        self.save();return True

def main():
    if '--status' in sys.argv:print(json.dumps(state(),ensure_ascii=False,indent=2));return
    if '--restore' in sys.argv:
        restore(Gio.bus_get_sync(Gio.BusType.SESSION,None),state());STATE.unlink(missing_ok=True);return
    ctypes.CDLL(None).prctl(15,b'mocha-freezer',0,0,0)
    logging.basicConfig(level=logging.INFO,format='%(name)s %(message)s')
    policy=Policy();loop=GLib.MainLoop()
    def stop(*_):loop.quit();return False
    for sig in [signal.SIGTERM,signal.SIGINT]:GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,sig,stop)
    GLib.timeout_add_seconds(5,policy.evaluate)
    if policy.connect():GLib.timeout_add_seconds(2,policy.connect)
    try:loop.run()
    finally:
        policy.release()
        if policy.clipboard_watcher and policy.clipboard_watcher.poll() is None:policy.clipboard_watcher.terminate()

if __name__=='__main__':main()
