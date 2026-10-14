#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Touch-accessible controls for Nyxuri's compositor effects and gestures.

The initial defaults are the upstream defaults. Nothing is automatically
reduced based on the board model. Changes are validated before installation.
"""
import os
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

DIRECTORY = Path.home() / ".config/niri"
ANIMATIONS = {
    "workspace-switch": "工作区切换",
    "horizontal-view-movement": "横向视图移动",
    "window-movement": "窗口移动",
    "window-resize": "窗口缩放",
    "config-notification-open-close": "配置通知",
    "overview-open-close": "概览",
}


def block(text, name):
    found = re.search(r"\b" + re.escape(name) + r"\s*\{([^{}]*)\}", text, re.S)
    return found.group(1) if found else ""


def number(text, key, default):
    found = re.search(r"\b" + re.escape(key) + r"(?:\s+|=)([-\d.]+)", text)
    return float(found.group(1)) if found else default


def install_validated(changes):
    with tempfile.TemporaryDirectory(prefix=".nyxuri-settings-", dir=DIRECTORY.parent) as temporary:
        staging = Path(temporary) / "niri"
        shutil.copytree(DIRECTORY, staging, symlinks=True)
        # The absolute EyeCare link belongs to the live directory; re-point
        # its staging copy so validate checks the new effect values too.
        link = staging / "effects.kdl"
        if link.is_symlink():
            target = Path(os.readlink(link)).name
            link.unlink()
            link.symlink_to(target)
        for name, text in changes.items():
            (staging / name).write_text(text, encoding="utf-8", newline="\n")
        checked = subprocess.run(["niri", "validate", "-c", str(staging / "config.kdl")],
                                 capture_output=True, text=True, timeout=15)
        if checked.returncode:
            raise ValueError(checked.stderr[-3000:])
        backup = Path.home() / ".local/state/nyxuri/effect-backups" / time.strftime("%Y%m%d-%H%M%S")
        backup.mkdir(parents=True, exist_ok=True)
        for name, text in changes.items():
            current = DIRECTORY / name
            shutil.copy2(current, backup / name)
            temporary_file = current.with_name(current.name + ".new")
            temporary_file.write_text(text, encoding="utf-8", newline="\n")
            os.replace(temporary_file, current)
        subprocess.run(["niri", "msg", "action", "load-config-file"], check=True, timeout=10)


class Settings(Gtk.Window):
    def __init__(self):
        super().__init__(title="Nyxuri 效果与触屏设置")
        self.set_default_size(820, 650)
        self.set_wmclass("mocha-nyxuri-settings", "mocha-nyxuri-settings")
        self.connect("destroy", Gtk.main_quit)
        css = Gtk.CssProvider()
        css.load_from_data(b'switch.mocha-switch { min-width: 50px; min-height: 26px; padding: 2px; border-radius: 16px; } switch.mocha-switch slider { min-width: 24px; min-height: 24px; margin: 0; padding: 0; border-radius: 50%; }')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        self.add(box)
        intro = Gtk.Label(label="完整保留 Nyxuri 效果。按你的偏好调整；应用前会检查配置，修改会持久保存。")
        intro.set_line_wrap(True)
        box.pack_start(intro, False, False, 0)
        tabs = Gtk.Notebook()
        box.pack_start(tabs, True, True, 0)
        self.values = {}
        effects = (DIRECTORY / "effects_normal.kdl").read_text()
        animations = (DIRECTORY / "animations__custom__.kdl").read_text()
        effect_grid = self.page(tabs, "毛玻璃与透明度")
        blur = block(effects, "blur")
        for key, label, default, low, high, step in (
            ("passes", "模糊次数", 3, 0, 8, 1),
            ("offset", "模糊半径", 2.3, 0, 10, .1),
            ("noise", "噪点", .001, 0, .1, .001),
            ("saturation", "饱和度", 2, 0, 4, .1),
        ):
            self.spin(effect_grid, key, label, number(blur, key, default), low, high, step)
        opacity = re.findall(r"\bopacity\s+([\d.]+)", effects)
        self.spin(effect_grid, "opacity", "活动窗口透明度", float(opacity[0]) if opacity else .9, .1, 1, .05)
        self.spin(effect_grid, "inactive-opacity", "非活动窗口透明度", float(opacity[1]) if len(opacity)>1 else .85, .1, 1, .05)
        self.toggle(effect_grid, "blur-enabled", "窗口毛玻璃", "blur true" in effects)
        self.toggle(effect_grid, "xray", "X-Ray 模糊", "xray true" in effects)
        animation_grid = self.page(tabs, "动画")
        for name, label in ANIMATIONS.items():
            data = block(animations, name)
            self.spin(animation_grid, name + ":damping", label + " · 阻尼", number(data, "damping-ratio", .85), .1, 2, .05)
            self.spin(animation_grid, name + ":stiffness", label + " · 弹簧刚度", number(data, "stiffness", 423), 20, 2000, 10)
        for name, label, default in (("window-open", "窗口打开",150), ("window-close","窗口关闭",150), ("screenshot-ui-open","截图界面",200)):
            self.spin(animation_grid, name + ":duration", label + " · 时长（毫秒）", number(block(animations,name),"duration-ms",default), 0, 1200, 10)
        input_grid = self.page(tabs, "显示与触屏")
        monitor = (DIRECTORY / "monitor.kdl").read_text()
        inputs = (DIRECTORY / "input__custom__.kdl").read_text()
        self.spin(input_grid, "scale", "显示缩放（旋转保持 270°）", number(monitor,"scale",1.5), 1, 2.5, .1)
        self.spin(input_grid, "fingers", "多指手势触发指数量", number(inputs,"fingers",3), 3, 8, 1)
        self.key_lights = Path.home() / '.config/mocha/touch-keys.json'
        try:
            lighting = json.loads(self.key_lights.read_text())
        except (OSError, ValueError):
            lighting = {}
        self.spin(input_grid, "key-brightness", "实体触控键背光亮度（%）", lighting.get('brightness',10), 0, 30, 1)
        self.spin(input_grid, "key-timeout", "按键背光时长（秒，0 为常亮）", lighting.get('timeout',8), 0, 60, 1)
        tip = Gtk.Label(label="底部上滑：概览；顶部下滑：控制中心；左右边缘：切换列。\n右下角：键盘开关；左下角：启动器。三指点按：最大化；四指下滑：关闭窗口。\n右上角向内滑：全屏切换。返回键：先收键盘，再返回；主页键：桌面；菜单键：概览。\n任务栏的 × 可关闭当前窗口，应用会保留自己的未保存提示。")
        tip.set_line_wrap(True)
        input_grid.attach(tip,0,20,2,1)
        performance = self.page(tabs, "CPU、GPU 与内存")
        self.runtime_config = Path.home() / '.config/mocha/runtime.json'
        self.gpu_limit = Path.home() / '.config/mocha/gpu-max-pstate'
        try:
            runtime = json.loads(self.runtime_config.read_text())
            if not isinstance(runtime, dict): runtime = {}
        except (OSError, ValueError): runtime = {}
        def bounded(key, default, low, high):
            value = runtime.get(key, default)
            return value if type(value) is int and low <= value <= high else default
        self.spin(performance, 'cpu-max-mhz', 'CPU 最高频率（MHz，向下匹配原厂档位）', bounded('cpu_max_mhz',1200,600,1200),600,1200,24)
        self.spin(performance, 'swappiness', '压缩内存使用倾向（swappiness）', bounded('swappiness',80,10,100),10,100,5)
        supported = bool(list(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')))
        for key in ('cpu-max-mhz','swappiness'):
            self.values[key].set_sensitive(supported)
        performance.attach(Gtk.Label(label='GPU 原厂最高档位',xalign=0),0,2,1,1)
        self.gpu_choice = Gtk.ComboBoxText()
        self.gpu_choice.append('0a','均衡 · 648 MHz')
        self.gpu_choice.append('0f','流畅 · 852 MHz')
        try: gpu = self.gpu_limit.read_text().strip()
        except OSError: gpu = '0f'
        self.gpu_choice.set_active_id(gpu if gpu in ('0a','0f') else '0f')
        self.gpu_choice.set_size_request(220,44)
        performance.attach(self.gpu_choice,1,2,1,1)
        note = Gtk.Label(label=('CPU 动态调频已提供。' if supported else '当前内核尚无 CPU 动态调频；候选通过实机验证后开放 CPU 与压缩内存控制。') +
            '\nGPU 温度、电池电压和供电限制始终生效。频率对应的电压由原厂驱动管理。\n压缩交换使用 RAM，不使用闪存；384 MiB 为逻辑容量。')
        note.set_line_wrap(True);note.set_xalign(0)
        performance.attach(note,0,4,2,1)
        more = self.page(tabs, "Nyxuri 工具")
        for label, command in (
            ("Noctalia 全部设置（任务栏、弹窗、插件、动画）", ["noctalia","msg","settings-toggle"]),
            ("静态与动态壁纸", [str(Path.home()/".config/noctalia/tools/wallpaper-picker.py")]),
            ("Orbit 星环启动器", [str(Path.home()/".config/noctalia/tools/orbit-launcher.py")]),
            ("护眼模式", [str(DIRECTORY/"scripts/toggle-eyecare.sh")]),
            ("Nyxuri 预设与模块管理", ["kitty","nyxuri"]),
        ):
            button = Gtk.Button(label=label)
            button.set_size_request(-1,48)
            button.connect("clicked", lambda _, argv=command: subprocess.Popen(argv))
            more.attach(button,0,len(more.get_children()),2,1)
        self.status = Gtk.Label(label="")
        self.status.set_line_wrap(True)
        box.pack_start(self.status, False, False, 0)
        apply = Gtk.Button(label="应用并保存")
        apply.set_size_request(-1,48)
        apply.connect("clicked",self.apply)
        box.pack_start(apply,False,False,0)
        self.show_all()

    def page(self, tabs, name):
        grid = Gtk.Grid(column_spacing=20,row_spacing=12,margin=16)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroller.add(grid)
        tabs.append_page(scroller,Gtk.Label(label=name))
        return grid

    def spin(self, grid, key, label, value, low, high, step):
        row = len(grid.get_children())//2
        grid.attach(Gtk.Label(label=label,xalign=0),0,row,1,1)
        widget = Gtk.SpinButton.new_with_range(low,high,step)
        widget.set_digits(3 if step==.001 else 2 if step<1 else 0)
        widget.set_value(value)
        widget.set_size_request(180,44)
        grid.attach(widget,1,row,1,1)
        self.values[key] = widget

    def toggle(self, grid, key, label, value):
        row = len(grid.get_children())//2
        grid.attach(Gtk.Label(label=label,xalign=0),0,row,1,1)
        widget = Gtk.Switch(active=value)
        widget.set_halign(Gtk.Align.START)
        widget.set_valign(Gtk.Align.CENTER)
        widget.set_hexpand(False)
        widget.get_style_context().add_class("mocha-switch")
        # A 44px hit area surrounds the compact, circular-thumb switch.
        target = Gtk.EventBox()
        target.set_above_child(True)
        target.set_size_request(64,44)
        target.set_halign(Gtk.Align.START)
        target.add(widget)
        target.connect("button-release-event", lambda _, event: self.switch_target(widget))
        grid.attach(target,1,row,1,1)
        self.values[key]=widget

    @staticmethod
    def switch_target(widget):
        widget.set_active(not widget.get_active())
        return True

    def apply(self, button):
        get = lambda key: self.values[key].get_value()
        effects = (DIRECTORY/"effects_normal.kdl").read_text()
        for key in ("passes","offset","noise","saturation"):
            effects = re.sub(r"(\b"+key+r"\s+)[\d.]+",lambda m:m[1]+f"{get(key):g}",effects)
        count = [0]
        def opacity(match):
            key = "opacity" if count[0]==0 else "inactive-opacity"
            count[0]+=1
            return match[1]+f"{get(key):g}"
        effects = re.sub(r"(\bopacity\s+)[\d.]+",opacity,effects)
        effects = re.sub(r"\bblur (true|false)","blur "+str(self.values["blur-enabled"].get_active()).lower(),effects)
        effects = re.sub(r"\bxray (true|false)","xray "+str(self.values["xray"].get_active()).lower(),effects)
        animations = (DIRECTORY/"animations__custom__.kdl").read_text()
        for name in ANIMATIONS:
            data = block(animations,name)
            new = re.sub(r"damping-ratio=[\d.]+",f"damping-ratio={get(name+':damping'):g}",data)
            new = re.sub(r"stiffness=[\d.]+",f"stiffness={get(name+':stiffness'):g}",new)
            animations = animations.replace(data,new,1)
        for name in ("window-open","window-close","screenshot-ui-open"):
            data = block(animations,name)
            new = re.sub(r"duration-ms\s+[\d.]+",f"duration-ms {get(name+':duration'):g}",data)
            animations = animations.replace(data,new,1)
        monitor = (DIRECTORY/"monitor.kdl").read_text()
        monitor = re.sub(r"\bscale\s+[\d.]+",f"scale {get('scale'):g}",monitor)
        inputs = (DIRECTORY/"input__custom__.kdl").read_text()
        inputs = re.sub(r"\bfingers\s+\d+",f"fingers {int(get('fingers'))}",inputs)
        changes={"effects_normal.kdl":effects,"animations__custom__.kdl":animations,"monitor.kdl":monitor,"input__custom__.kdl":inputs}
        lighting = {'brightness': int(get('key-brightness')), 'timeout': get('key-timeout')}
        runtime = {'cpu_max_mhz': int(get('cpu-max-mhz')), 'swappiness': int(get('swappiness'))}
        gpu = self.gpu_choice.get_active_id()
        button.set_sensitive(False)
        self.status.set_text("正在检查并应用…")
        def worker():
            try:
                install_validated(changes)
                self.key_lights.parent.mkdir(parents=True, exist_ok=True)
                pending = self.key_lights.with_suffix('.new')
                pending.write_text(json.dumps(lighting) + '\n')
                os.replace(pending, self.key_lights)
                for path, text in ((self.runtime_config,json.dumps(runtime)+'\n'), (self.gpu_limit,gpu+'\n')):
                    pending=path.with_suffix('.new')
                    pending.write_text(text)
                    os.replace(pending,path)
                message="已保存并应用。可在 Noctalia 设置中继续调整弹窗、任务栏和插件。"
            except Exception as error:
                message="配置未应用："+str(error)
            GLib.idle_add(self.done,button,message)
        threading.Thread(target=worker,daemon=True).start()

    def done(self,button,message):
        button.set_sensitive(True)
        self.status.set_text(message)


if __name__ == "__main__":
    Settings()
    Gtk.main()
