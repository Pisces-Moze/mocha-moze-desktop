#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Add touch navigation to full Nyxuri without replacing user effect settings.

Run as the desktop user after installing tablet/mocha-touch-nav in /usr/local/bin.
Re-running retains all other bar items and user settings. Validate before writes.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import tomllib

ITEMS = {
    'touch_keyboard': ('keyboard', '显示／收起触屏键盘', '/usr/local/bin/mocha-keyboard'),
    'touch_close': ('x', '关闭当前窗口（保留应用的未保存提示）', '/usr/local/bin/mocha-touch-nav close'),
}


def section(text, name, values):
    header = '[' + name + ']'
    match = re.search(r'^' + re.escape(header) + r'\s*$', text, re.M)
    if match:
        rest = text[match.end():]
        next_header = re.search(r'^\[', rest, re.M)
        end = match.end() + next_header.start() if next_header else len(text)
        body = text[match.end():end]
        for key, value in values.items():
            expression = r'^' + re.escape(key) + r'\s*=\s*(?:\[[^\]]*\]|[^\n]*)'
            line = key + ' = ' + json.dumps(value, ensure_ascii=False)
            if re.search(expression, body, re.M):
                body = re.sub(expression, lambda _: line, body, count=1, flags=re.M)
            else:
                body += '\n' + line + '\n'
        return text[:match.end()] + body + text[end:]
    return text.rstrip() + '\n\n' + header + '\n' + '\n'.join(key + ' = ' + json.dumps(value, ensure_ascii=False) for key, value in values.items()) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as the desktop user')
    home = Path.home()
    niri = home / '.config/niri'
    changes = {}
    custom = (niri / '__custom__.kdl').read_text()
    if 'include "touch-nav.kdl"' not in custom:
        custom += '\n// Mocha touch navigation; preserved by Nyxuri updates.\ninclude "touch-nav.kdl"\n'
    if 'app-id="mocha-nyxuri-settings.py"' not in custom:
        custom += '\nwindow-rule {\n    match app-id="mocha-nyxuri-settings.py"\n    open-floating true\n    default-column-width { proportion 0.65; }\n    default-window-height { proportion 0.75; }\n}\n'
    changes[niri / '__custom__.kdl'] = custom
    changes[niri / 'touch-nav.kdl'] = (args.adapter / 'tablet/touch-nav.kdl').read_text()
    inputs = (niri / 'input__custom__.kdl').read_text()
    found = re.search(r'^gestures\s*\{', inputs, re.M)
    if found:
        depth = 1
        end = found.end()
        while depth and end < len(inputs):
            depth += (inputs[end] == '{') - (inputs[end] == '}')
            end += 1
        if depth:
            raise ValueError('Unbalanced existing gesture block')
        inputs = inputs[:found.start()] + inputs[end:]
    changes[niri / 'input__custom__.kdl'] = inputs.rstrip() + '\n\n' + (args.adapter / 'tablet/gestures.kdl').read_text()
    for filename in ('config.kdl', 'mocha-tablet.kdl'):
        path = niri / filename
        if path.exists():
            changes[path] = path.read_text().replace('// Keep application title-bar close buttons available to touch.', 'prefer-no-csd')
    base = home / '.config/noctalia/noctalia-config.toml'
    state = home / '.local/state/noctalia/settings.toml'
    text = base.read_text()
    defaults = tomllib.loads(text)['bar']['bar']['start']
    for name, (glyph, tooltip, command) in ITEMS.items():
        text = section(text, 'widget.' + name, {'type': 'custom_button', 'glyph': glyph, 'tooltip': tooltip, 'actions.left': 'exec ' + command})
    removed = {'touch_back', 'touch_home', 'touch_overview'}
    text = section(text, 'bar.bar', {'start': list(dict.fromkeys([item for item in defaults if item not in removed] + list(ITEMS)))})
    tomllib.loads(text)
    changes[base] = text
    if state.exists():
        overrides = state.read_text()
        start = tomllib.loads(overrides).get('bar', {}).get('bar', {}).get('start')
        if start is not None:
            overrides = section(overrides, 'bar.bar', {'start': list(dict.fromkeys([item for item in start if item not in removed] + list(ITEMS)))})
            tomllib.loads(overrides)
            changes[state] = overrides
    with tempfile.TemporaryDirectory(prefix='.touch-nav-', dir=niri.parent) as temporary:
        staging = Path(temporary) / 'niri'
        shutil.copytree(niri, staging, symlinks=True)
        for path, value in changes.items():
            if path.parent == niri:
                (staging / path.name).write_text(value, encoding='utf-8', newline='\n')
        subprocess.run(['niri', 'validate', '-c', str(staging / 'config.kdl')], check=True)
        noctalia_stage = Path(temporary) / 'noctalia.toml'
        noctalia_stage.write_text(text, encoding='utf-8')
        subprocess.run(['noctalia', 'config', 'validate', str(noctalia_stage)], check=True)
    backup = home / '.local/state/nyxuri/touch-backups' / time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    for path, value in changes.items():
        if path.exists():
            shutil.copy2(path, backup / (path.parent.name + '-' + path.name))
        pending = path.with_name(path.name + '.new')
        pending.write_text(value, encoding='utf-8', newline='\n')
        os.replace(pending, path)
    subprocess.run(['niri', 'msg', 'action', 'load-config-file'], check=True)
    print('TOUCH_NAV_INSTALLED backup=' + str(backup))


if __name__ == '__main__':
    main()
