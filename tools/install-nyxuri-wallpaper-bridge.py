#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install the managed picker, static handover and resource-pressure policies.

The plugin must already include patch 0007's decoder/fullscreen settings.
This does not change wallpaper selection, launch players or restart the shell.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

PATCH_NAMES = [
    '0010-noctalia-picker-managed-video.patch',
    '0011-nyxuri-picker-plugin-lifecycle.patch',
    '0012-wallpaper-static-handover.patch',
    '0013-wallpaper-resource-pressure.patch',
    '0015-wallpaper-pressure-reconfigure.patch',
    '0017-noctalia-wallpaper-occlusion.patch',
    '0019-noctalia-workarea-coverage.patch',
]


def stage_patches(stage, patches):
    """Normalize an installed prefix before replaying the complete patch stack.

    A later patch can change the context of an earlier one, so checking each
    earlier patch in isolation cannot recognize an already updated source.
    All reverse operations happen only in the disposable staging directory.
    """
    commands = [
        ['patch', '--batch', '--force', '--fuzz=0', '-p1', '-i', str((patches/name).resolve())]
        for name in PATCH_NAMES
    ]
    for command in reversed(commands):
        result = subprocess.run(command+['--reverse', '--dry-run'], cwd=stage,
                                capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(command+['--reverse'], cwd=stage, check=True, capture_output=True)
    for name, command in zip(PATCH_NAMES, commands):
        result = subprocess.run(command+['--forward', '--dry-run'], cwd=stage,
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f'Source does not match {name}: {result.stdout} {result.stderr}')
        subprocess.run(command+['--forward'], cwd=stage, check=True, capture_output=True)


def atomic_write(path, data, info):
    temporary = path.with_name(path.name + '.mocha-incoming-' + str(os.getpid()))
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(info.st_mode & 0o777)
        if os.geteuid() == 0:
            os.chown(temporary, info.st_uid, info.st_gid)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Noctalia config directory')
    parser.add_argument('--plugin', type=Path, required=True, help='Official mpvpaper plugin directory')
    parser.add_argument('--patches', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True, help='New backup directory')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    paths = {Path('mpvpaper_service.luau'): args.plugin/'mpvpaper_service.luau',
             Path('plugin.toml'): args.plugin/'plugin.toml',
             Path('translations/en.json'): args.plugin/'translations/en.json',
             Path('translations/zh-Hans.json'): args.plugin/'translations/zh-Hans.json',
             Path('config/noctalia/tools/wallpaper_picker/backend.py'): args.config/'tools/wallpaper_picker/backend.py'}
    originals = {}
    with tempfile.TemporaryDirectory(prefix='nyxuri-wallpaper-bridge-') as temporary:
        stage = Path(temporary)
        for relative, path in paths.items():
            if not path.is_file() or path.is_symlink():
                raise ValueError(f'Expected a regular source file: {path}')
            originals[relative] = (path.read_bytes(), path.stat())
            target = stage/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(originals[relative][0])
        stage_patches(stage, args.patches)
        after = {relative: (stage/relative).read_bytes() for relative in paths}
        if args.check:
            print('NYXURI_WALLPAPER_BRIDGE_SOURCES_CHECKED_NOT_INSTALLED')
            return
        args.backup.mkdir(parents=True, exist_ok=False)
        for relative, (data, _) in originals.items():
            target = args.backup/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        changed = []
        try:
            for relative, path in paths.items():
                data, info = originals[relative]
                if path.read_bytes() != data:
                    raise RuntimeError(f'Source changed during staging: {path}')
                if data != after[relative]:
                    atomic_write(path, after[relative], info)
                    changed.append(relative)
        except BaseException:
            for relative in reversed(changed):
                data, info = originals[relative]
                atomic_write(paths[relative], data, info)
            raise
        report = [{'file': str(relative), 'before_sha256': hashlib.sha256(originals[relative][0]).hexdigest(),
                   'after_sha256': hashlib.sha256(after[relative]).hexdigest()} for relative in paths]
        (args.backup/'installed.json').write_text(json.dumps(report, indent=2)+'\n')
        print('NYXURI_WALLPAPER_BRIDGE_INSTALLED_RELOAD_PLUGIN_TO_ACTIVATE')


if __name__ == '__main__':
    main()
