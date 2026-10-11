#!/usr/bin/env python3
"""Low overhead prototype telemetry: one process, no per-field cat forks."""
import argparse
import json
import time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--seconds', type=int, default=120)
a = p.parse_args()
if not 1 <= a.seconds <= 3600:
    p.error('seconds must be 1..3600')

def read(file):
    try:
        return file.read_text().strip()
    except OSError:
        return None

for sample in range(a.seconds):
    row = {'sample': sample + 1, 'monotonic': time.monotonic(), 'power': {}, 'thermal': {}}
    for supply in Path('/sys/class/power_supply').iterdir():
        row['power'][supply.name] = {name: read(supply / name) for name in
            ('capacity', 'voltage_now', 'current_now', 'status', 'online', 'input_current_limit', 'temp')}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        row['thermal'][read(zone / 'type') or zone.name] = read(zone / 'temp')
    print(json.dumps(row), flush=True)
    time.sleep(1)
