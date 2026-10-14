#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""PH1/PWM1 capacitive-key backlight. Nonexclusive input; no event logging."""
import glob
import json
import os
from pathlib import Path
import pwd
import select
import signal
import struct
import time

EVENT = struct.Struct('llHHi')
PERIOD = 1_000_000
CONFIG = Path(pwd.getpwnam('mocha').pw_dir) / '.config/mocha/touch-keys.json'
running = True


def stop(*_):
    global running
    running = False


def preferences():
    try:
        data = json.loads(CONFIG.read_text())
        return max(0, min(30, int(data['brightness']))), max(0, min(60, float(data['timeout'])))
    except (OSError, ValueError, KeyError, TypeError):
        return 10, 8


def awake():
    try:
        if int(Path('/sys/class/backlight/mocha-miui-backlight/brightness').read_text()) <= 0:
            return False
    except OSError:
        return False
    for filename in glob.glob('/sys/class/drm/card*-DSI-1/dpms'):
        if Path(filename).read_text().strip().lower() == 'off':
            return False
    return True


def main():
    pins = Path('/sys/kernel/debug/pinctrl/70000868.pinmux/pinmux-pins').read_text()
    if not any('(PH1)' in line and 'function pwm1 group ph1' in line for line in pins.splitlines()):
        raise RuntimeError('PH1 is not configured for the verified key LED PWM')
    chip = next(Path(path) for path in glob.glob('/sys/class/pwm/pwmchip*') if '7000a000.pwm' in str(Path(path).resolve()))
    pwm = chip / 'pwm1'
    if pwm.exists():
        raise RuntimeError('PWM1 is already owned; leave its state untouched')
    (chip / 'export').write_text('1')
    descriptor = None
    try:
        for _ in range(20):
            if (pwm / 'period').exists():
                break
            time.sleep(.05)
        (pwm / 'period').write_text(str(PERIOD))
        (pwm / 'duty_cycle').write_text('0')
        (pwm / 'enable').write_text('1')
        for path in glob.glob('/sys/class/input/event*/device/name'):
            if Path(path).read_text().strip() == 'Atmel maXTouch Touchscreen':
                event = Path(path).parents[1].name
                descriptor = os.open('/dev/input/' + event, os.O_RDONLY | os.O_NONBLOCK)
                break
        if descriptor is None:
            raise RuntimeError('The verified capacitive-key input device is missing')
        deadline = time.monotonic()
        was_awake = False
        duty = -1
        next_poll = 0
        brightness, timeout = preferences()
        screen = False
        while running:
            now = time.monotonic()
            # Motion events arrive much faster than lighting needs to react.
            # Bound filesystem polling instead of reading sysfs every frame.
            if now >= next_poll:
                brightness, timeout = preferences()
                screen = awake()
                next_poll = now + .25
            if screen and not was_awake:
                deadline = now + timeout
            was_awake = screen
            ready, _, _ = select.select([descriptor], [], [], .2)
            if ready:
                events = os.read(descriptor, EVENT.size * 64)
                for offset in range(0, len(events) - EVENT.size + 1, EVENT.size):
                    _, _, kind, code, value = EVENT.unpack_from(events, offset)
                    if kind == 1 and value == 1 and code in (102, 139, 158, 330):
                        deadline = time.monotonic() + timeout
            new_duty = PERIOD * brightness // 100 if screen and (timeout == 0 or time.monotonic() < deadline) else 0
            if new_duty != duty:
                (pwm / 'duty_cycle').write_text(str(new_duty))
                duty = new_duty
    finally:
        if descriptor is not None:
            os.close(descriptor)
        (pwm / 'duty_cycle').write_text('0')
        (pwm / 'enable').write_text('0')
        (chip / 'unexport').write_text('1')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    main()
