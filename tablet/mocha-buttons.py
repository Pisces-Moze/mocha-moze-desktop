#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Own gpio-keys once; act on power RELEASE so it cannot wake its own DPMS."""
import fcntl, glob, json, os, select, signal, struct, subprocess, time
from pathlib import Path

EVENT = struct.Struct('llHHi')  # native ABI: 16 bytes armhf, 24 bytes amd64
GRAB = 0x40044590
NIRI = os.environ.get('MOCHA_NIRI', '/usr/local/bin/niri')
NOCTALIA = os.environ.get('MOCHA_NOCTALIA', '/usr/local/bin/noctalia')
BACKLIGHT = Path('/sys/class/backlight/mocha-miui-backlight/brightness')

def display_off():
    """Idle DPMS is independent of this controller's last button action."""
    states = []
    for name in glob.glob('/sys/class/drm/card*-DSI-1/dpms'):
        try: states.append(Path(name).read_text().strip() != 'On')
        except OSError: pass
    # Input can bring DRM DPMS back to On while our explicit backlight blank
    # is still active. Both must be checked before deciding this is a wake.
    try:
        if int(BACKLIGHT.read_text()) == 0: return True
    except (OSError, ValueError): pass
    if states: return all(states)
    return None

def record(*parts):
    """Retain only button actions across reboot, never text or touch input."""
    message = ' '.join(map(str, parts))
    print(message, flush=True)
    try:
        path = Path.home()/'.local/state/mocha/power-events.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 65536:
            path.replace(path.with_suffix('.previous.log'))
        with path.open('a') as stream:
            stream.write(time.strftime('%Y-%m-%dT%H:%M:%S ') + message + '\n')
        path.chmod(0o600)
    except OSError: pass

def command(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=4)
    except subprocess.TimeoutExpired:
        return None

def shell(*args):
    return command([NOCTALIA, 'msg', *args])

def status():
    result = shell('status')
    if not result or result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None

def socket_env():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    sockets = list(runtime.glob('niri*.sock'))
    if len(sockets) != 1:
        raise RuntimeError('Expected one live Niri socket')
    os.environ['NIRI_SOCKET'] = str(sockets[0])
    os.environ['WAYLAND_DISPLAY'] = sockets[0].name.split('.')[1]

class Buttons:
    def __init__(self):
        self.pressed = None
        self.screen_off = False
        self.last_release = -1.0
        self.last_volume = -1.0
        self.saved_brightness = None

    def backlight(self, on):
        try:
            if on:
                if self.saved_brightness is not None:
                    BACKLIGHT.write_text(str(self.saved_brightness))
                    self.saved_brightness = None
            else:
                value = int(BACKLIGHT.read_text())
                if value > 0: self.saved_brightness = value
                BACKLIGHT.write_text('0')
        except OSError:
            print('BACKLIGHT_CONTROL_UNAVAILABLE', flush=True)

    def event(self, code, value, now):
        if code == 116:
            if value == 1 and self.pressed is None:
                self.pressed = now
            elif value == 0 and self.pressed is not None:
                duration = now - self.pressed
                self.pressed = None
                if now - self.last_release < .35:
                    return
                self.last_release = now
                self.power(duration)
        elif code in (114, 115) and value in (1, 2) and now - self.last_volume >= .12:
            self.last_volume = now
            shell('volume-up' if code == 115 else 'volume-down', '5')
            print('VOLUME', 'up' if code == 115 else 'down', flush=True)

    def power(self, duration):
        record('POWER_RELEASE_SECONDS', round(duration, 3))
        actual_off = display_off()
        if actual_off is not None:
            self.screen_off = actual_off
        # Touch can wake and unlock independently of this input device.
        current = status() if self.screen_off else None
        if current is not None and not current.get('locked'):
            self.screen_off = False
        if self.screen_off:
            shell('dpms-on')
            self.backlight(True)
            self.screen_off = False
            record('POWER_WAKE_LOCKED')
            return
        if duration >= 2:
            shell('panel-open', 'session')
            record('POWER_SESSION_MENU')
            return
        result = shell('session', 'lock')
        if not result or result.returncode:
            record('POWER_LOCK_FAILED')
            return
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            current = status()
            if current and current.get('locked'):
                # Lock acquisition can request DPMS-on. Wait for that transition
                # before off; the physical release never enters the compositor.
                time.sleep(.3)
                result = shell('dpms-off')
                self.screen_off = bool(result and result.returncode == 0)
                if self.screen_off: self.backlight(False)
                record('POWER_LOCKED_OFF', self.screen_off)
                return
            time.sleep(.05)
        record('POWER_LOCK_TIMEOUT')

def main():
    def terminate(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,terminate)
    socket_env()
    device = None
    for path in glob.glob('/dev/input/event*'):
        candidate = Path('/sys/class/input') / Path(path).name / 'device/name'
        if candidate.read_text().strip() == 'gpio-keys':
            device = path
            break
    if device is None:
        raise RuntimeError('gpio-keys not found')
    with open(device, 'rb', buffering=0) as stream:
        fcntl.ioctl(stream, GRAB, 1)
        record('GPIO_BUTTONS_OWNED', Path(device).name,
               Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        controller = Buttons()
        try:
            while True:
                select.select([stream], [], [])
                data = stream.read(EVENT.size)
                if len(data) != EVENT.size:
                    raise RuntimeError('Input device disconnected')
                _, _, kind, code, value = EVENT.unpack(data)
                if kind == 1:
                    controller.event(code, value, time.monotonic())
        finally:
            controller.backlight(True)
            fcntl.ioctl(stream, GRAB, 0)

if __name__ == '__main__':
    main()
