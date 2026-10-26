#!/usr/bin/env python3
"""Build canonical mpvpaper and holder with focused-fullscreen resource release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
for name in ['archive', 'patch', 'destination', 'mpv-pkgconfig', 'cross-file']:
    parser.add_argument('--' + name, type=Path, required=True)
args = parser.parse_args()
fractional_patch = args.patch.with_name('0009-mpvpaper-fractional-scale.patch')
render_update_patch = args.patch.with_name('0014-mpvpaper-render-update-flags.patch')
sha = '6de941b54941cfd5d00bac62d10ef47c1338f237dac4c78a7185d0f8d30cd4d1'
assert hashlib.file_digest(args.archive.open('rb'), 'sha256').hexdigest() == sha
assert not args.destination.exists()
args.destination.mkdir(parents=True)
with tarfile.open(args.archive) as archive:
    archive.extractall(args.destination, filter='data')
source = args.destination / 'mpvpaper-1.9'
for check in [True, False]:
    subprocess.run(['patch', '-p1', '--fuzz=0', '--batch', *(['--dry-run'] if check else []), '-i', str(args.patch.resolve())], cwd=source, check=True)
for optional_patch in [fractional_patch, render_update_patch]:
    if optional_patch.is_file():
        for check in [True, False]:
            subprocess.run(['patch', '-p1', '--fuzz=0', '--batch', *(['--dry-run'] if check else []), '-i', str(optional_patch.resolve())], cwd=source, check=True)
env = dict(os.environ, PKG_CONFIG_PATH=str(args.mpv_pkgconfig),
           PKG_CONFIG_LIBDIR='/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig')
build = args.destination / 'build'
subprocess.run(['meson', 'setup', str(build), str(source), '--cross-file', str(args.cross_file),
                '--buildtype=release', '-Dc_link_args=-Wl,--allow-shlib-undefined'], env=env, check=True)
subprocess.run(['ninja', '-C', str(build), '-j2'], env=env, check=True)
files = {}
for name in ['mpvpaper', 'mpvpaper-holder']:
    subprocess.run(['arm-linux-gnueabihf-strip', str(build / name)], check=True)
    files[name] = hashlib.file_digest((build / name).open('rb'), 'sha256').hexdigest()
(args.destination / 'build.json').write_text(json.dumps(dict(source_sha256=sha,
    patch_sha256=hashlib.file_digest(args.patch.open('rb'), 'sha256').hexdigest(),
    fractional_patch_sha256=hashlib.file_digest(fractional_patch.open('rb'), 'sha256').hexdigest() if fractional_patch.is_file() else None,
    render_update_patch_sha256=hashlib.file_digest(render_update_patch.open('rb'), 'sha256').hexdigest() if render_update_patch.is_file() else None,
    files=files), indent=2) + '\n')
print('MPVPAPER_FULLSCREEN_BUILT_NOT_INSTALLED')
