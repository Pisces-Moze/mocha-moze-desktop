#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise source-prefix upgrades and conflict refusal using an owned fixture.

Fixture contains the five sources after patches 0010/0011. Tests use temporary
copies only; they never touch a running desktop or select a wallpaper.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    patches = root/'patches/vde'
    names = ['0010-noctalia-picker-managed-video.patch',
             '0011-nyxuri-picker-plugin-lifecycle.patch',
             '0012-wallpaper-static-handover.patch',
             '0013-wallpaper-resource-pressure.patch',
             '0015-wallpaper-pressure-reconfigure.patch',
             '0017-noctalia-wallpaper-occlusion.patch',
             '0019-noctalia-workarea-coverage.patch']
    files = ['mpvpaper_service.luau', 'plugin.toml', 'translations/en.json',
             'translations/zh-Hans.json', 'config/noctalia/tools/wallpaper_picker/backend.py']
    with tempfile.TemporaryDirectory(prefix='wallpaper-installer-test-') as directory:
        base = Path(directory)
        fixture = base/'fixture'
        fixture.mkdir()
        for name in files:
            target = fixture/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.fixture/name, target)

        def apply(stage, index, reverse=False):
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1',
                            '--reverse' if reverse else '--forward',
                            '-i', str(patches/names[index])], cwd=stage,
                           check=True, capture_output=True)

        apply(fixture, 1, True)
        apply(fixture, 0, True)
        expected = None
        for count in range(len(names)+1):
            stage = base/str(count)
            shutil.copytree(fixture, stage)
            for index in range(count):
                apply(stage, index)
            command = [sys.executable, str(root/'tools/install-nyxuri-wallpaper-bridge.py'),
                       '--config', str(stage/'config/noctalia'), '--plugin', str(stage),
                       '--patches', str(patches), '--backup', str(base/('backup-'+str(count)))]
            before = {name: (stage/name).read_bytes() for name in files}
            result = subprocess.run(command+['--check'], capture_output=True, text=True)
            assert result.returncode == 0, result.stdout+result.stderr
            assert before == {name: (stage/name).read_bytes() for name in files}
            subprocess.run(command, check=True, capture_output=True)
            after = {name: (stage/name).read_bytes() for name in files}
            if expected is None:
                expected = after
            assert after == expected, f'Prefix {count} produces different sources'
            assert before == {name: (base/('backup-'+str(count))/name).read_bytes() for name in files}
            subprocess.run(command+['--check'], check=True, capture_output=True)
        conflict = base/'conflict'
        shutil.copytree(fixture, conflict)
        (conflict/'mpvpaper_service.luau').write_text('-- incompatible upstream source\n')
        before = {name: (conflict/name).read_bytes() for name in files}
        command = [sys.executable, str(root/'tools/install-nyxuri-wallpaper-bridge.py'),
                   '--config', str(conflict/'config/noctalia'), '--plugin', str(conflict),
                   '--patches', str(patches), '--backup', str(base/'conflict-backup')]
        result = subprocess.run(command, capture_output=True)
        assert result.returncode != 0 and not (base/'conflict-backup').exists()
        assert before == {name: (conflict/name).read_bytes() for name in files}
    print('EIGHT_PATCH_PREFIXES_IDEMPOTENT_CHECK_BACKUP_AND_CONFLICT_REFUSAL_PASSED')


if __name__ == '__main__':
    main()
