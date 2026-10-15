"""Summarize complete Niri profile records; percentiles use nearest rank."""
import json
import math
import re
import sys
from pathlib import Path

FIELDS = ('elements_ms', 'render_ms', 'wait_ms', 'queue_ms', 'total_ms')


def summarize(text, filename):
    frames = []
    for number, line in enumerate(text.splitlines(), 1):
        if 'MOCHA_FRAME ' not in line:
            continue
        tokens = dict(re.findall(r'\b(\w+_ms|needs_sync)=([^\s,\x1b]+)', line))
        try:
            row = {key: float(tokens[key]) for key in FIELDS}
            if any(not math.isfinite(value) or value < 0 for value in row.values()):
                raise ValueError('non-finite or negative duration')
            if tokens.get('needs_sync') not in ('true', 'false'):
                raise ValueError('missing or invalid needs_sync')
            row['needs_sync'] = tokens['needs_sync'] == 'true'
        except (KeyError, ValueError) as error:
            raise ValueError(f'{filename}:{number}: incomplete or invalid frame: {error}') from error
        frames.append(row)
    if not frames:
        raise ValueError(f'No frames: {filename}')
    result = {'file': filename, 'frames': len(frames),
              'cpu_wait_frames': sum(row['needs_sync'] for row in frames),
              'percentile_method': 'nearest-rank'}
    for key in FIELDS:
        values = sorted(row[key] for row in frames)
        result[key] = {'mean': round(sum(values) / len(values), 3),
                       **{f'p{q}': values[math.ceil(len(values) * q / 100) - 1]
                          for q in (50, 95, 99)}, 'max': max(values)}
    result['over_16_65ms'] = sum(row['total_ms'] > 16.65 for row in frames)
    result['startup_over_16_65ms'] = sum(row['total_ms'] > 16.65 for row in frames[:2])
    return result


def main(files):
    if not files:
        raise ValueError('usage: summarize-frame-profile.py LOG [LOG ...]')
    # Validate every input before printing anything that could look like a pass.
    results = [summarize(Path(file).read_text(), file) for file in files]
    for result in results:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
