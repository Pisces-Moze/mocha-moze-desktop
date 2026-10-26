#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install a native-library wrapper without changing mpvpaper's process name.

Official plugin shutdown/pause patterns and the Nyxuri picker use the canonical
mpvpaper executable name. Renaming the ELF breaks those lifecycle operations.
This installs a supplied, already-built ARM binary; it never downloads media.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

RUNTIME = Path('/usr/local/libexec/mocha-mpvpaper-runtime/mpvpaper')
WRAPPER = Path('/usr/local/bin/mpvpaper')
NATIVE = Path('/usr/local/libexec/mocha-native-app')
SELECTOR = RUNTIME.parent / 'select-player-runtime.py'


def atomic_bytes(path, content, mode):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--holder', type=Path, help='Matching mpvpaper-holder for fullscreen release')
    parser.add_argument('--decoder-runtime', type=Path, help='Verified isolated FFmpeg/libmpv runtime directory')
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True).read_bytes()
    if binary[:6] != b'\x7fELF\x01\x01' or int.from_bytes(binary[18:20], 'little') != 40:
        parser.error('Expected a little-endian ELF32 ARM mpvpaper binary')
    holder = None
    if args.holder:
        holder = args.holder.resolve(strict=True).read_bytes()
        if holder[:6] != b'\x7fELF\x01\x01' or int.from_bytes(holder[18:20], 'little') != 40:
            parser.error('Expected a little-endian ELF32 ARM mpvpaper-holder binary')
    decoder = None
    if args.decoder_runtime:
        if holder is None:
            parser.error('An isolated decoder runtime requires the matching holder')
        decoder = args.decoder_runtime.resolve(strict=True)
        manifest = (decoder / 'build-manifest.json').read_bytes()
        records = json.loads(manifest)['runtime_files']
        expected_files = {'build-manifest.json'}
        for record in records:
            name = record['path']
            path = decoder / name
            if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(decoder):
                parser.error('Decoder manifest contains an unbounded path')
            expected_files.add(name)
            if 'symlink' in record:
                if not path.is_symlink() or os.readlink(path) != record['symlink']:
                    parser.error('Decoder symlink mismatch: ' + name)
            elif path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                parser.error('Decoder file hash mismatch: ' + name)
        actual = {str(p.relative_to(decoder)) for p in decoder.rglob('*') if p.is_file() or p.is_symlink()}
        if actual != expected_files:
            parser.error('Decoder runtime contains unmanifested files')
        decoder_target = Path('/usr/local/libexec/mocha-vde-player') / hashlib.sha256(manifest).hexdigest()[:16]
    if not NATIVE.is_file() or not os.access(NATIVE, os.X_OK):
        parser.error('Install the matching mocha-native-app library wrapper first')
    if any(p.is_symlink() for p in [WRAPPER, RUNTIME, RUNTIME.with_name('mpvpaper-holder'), SELECTOR]):
        parser.error('Refusing a symlink at an installation target')
    if WRAPPER.exists():
        previous = WRAPPER.read_bytes()
        if not previous.startswith(b'#!/bin/sh\nexec /usr/local/libexec/mocha-native-app '):
            parser.error('Existing mpvpaper launcher is not the managed native wrapper')
    digest = hashlib.sha256(binary).hexdigest()
    print('mpvpaper ARM SHA256:', digest)
    if args.check:
        print('CHECK_OK; no files changed')
        return
    if os.geteuid() != 0:
        parser.error('Installation requires root')
    backup = args.backup_dir.resolve() / ('mpvpaper-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, path in [('wrapper', WRAPPER), ('mpvpaper', RUNTIME),
                       ('mpvpaper-holder', RUNTIME.with_name('mpvpaper-holder')), ('selector', SELECTOR)]:
        if path.exists():
            shutil.copy2(path, backup / name)
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    WRAPPER.parent.mkdir(parents=True, exist_ok=True)
    if decoder:
        decoder_target.parent.mkdir(parents=True, exist_ok=True)
        if decoder_target.exists():
            # Do not silently reuse a modified version directory.
            for p in decoder.rglob('*'):
                target = decoder_target / p.relative_to(decoder)
                if p.is_symlink():
                    assert target.is_symlink() and os.readlink(target) == os.readlink(p)
                elif p.is_file():
                    assert not target.is_symlink() and target.read_bytes() == p.read_bytes()
        else:
            stage = Path(tempfile.mkdtemp(prefix='.incoming-', dir=decoder_target.parent))
            shutil.copytree(decoder, stage, dirs_exist_ok=True, symlinks=True)
            for p in [stage, *stage.rglob('*')]:
                os.chown(p, 0, 0, follow_symlinks=False)
                if not p.is_symlink():
                    os.chmod(p, 0o755 if p.is_dir() or os.access(p, os.X_OK) else 0o644)
            os.rename(stage, decoder_target)
        # mocha-native-app establishes the matched Mesa path first. Append the
        # isolated codec path afterwards without replacing the Mesa selection.
        selector = '''#!/usr/bin/python3
import os, re, sys
from pathlib import Path
args = sys.argv[1:]
device = Path('/sys/bus/platform/devices/60030000.video-codec/driver')
active = device.is_symlink() and device.resolve().name in ('tegra-vde', 'mocha-vde-candidate')
active = active and any(p.read_text().strip() == 'tegra-vde' and Path('/dev', p.parent.name).is_char_device()
                        for p in Path('/sys/class/video4linux').glob('video*/name'))
if active:
    os.environ['LD_LIBRARY_PATH'] = DECODER_LIB + ':' + os.environ.get('LD_LIBRARY_PATH', '')
else:
    # Stock libmpv does not know Request backend names. Keep default boot usable.
    for i in range(1, len(args)):
        if args[i-1] in ('-o', '--mpv-options'):
            args[i] = re.sub(r'(?<!\\S)hwdec=v4l2request(?:-copy)?(?=\\s|$)', 'hwdec=auto', args[i])
os.execv(PLAYER, [PLAYER, *args])
'''.replace('DECODER_LIB', repr(str(decoder_target / 'lib'))).replace('PLAYER', repr(str(RUNTIME)))
        atomic_bytes(SELECTOR, selector.encode(), 0o755)
    if holder:
        atomic_bytes(RUNTIME.with_name('mpvpaper-holder'), holder, 0o755)
    atomic_bytes(RUNTIME, binary, 0o755)
    launcher = SELECTOR if decoder else RUNTIME
    atomic_bytes(WRAPPER, ('#!/bin/sh\nexec ' + str(NATIVE) + ' ' + str(launcher) + ' "$@"\n').encode(), 0o755)
    assert hashlib.sha256(RUNTIME.read_bytes()).hexdigest() == digest
    print('INSTALLED; backup:', backup)
    print('Reload only the mpvpaper plugin while the desktop is unlocked; verify one player remains.')


if __name__ == '__main__':
    main()
