#!/usr/bin/env python3
"""Build mpv 0.40.0 against the isolated Request API FFmpeg runtime."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
for name in ['archive', 'patches', 'destination', 'ffmpeg-prefix', 'deps-sysroot', 'cross-file']:
    parser.add_argument('--' + name, type=Path, required=True)
args = parser.parse_args()
sha = '10a0f4654f62140a6dd4d380dcf0bbdbdcf6e697556863dc499c296182f081a3'
assert hashlib.file_digest(args.archive.open('rb'), 'sha256').hexdigest() == sha
assert not args.destination.exists()
assert (args.ffmpeg_prefix / 'lib/pkgconfig/libavutil.pc').is_file()
args.destination.mkdir(parents=True)
with tarfile.open(args.archive) as archive:
    archive.extractall(args.destination, filter='data')
source = args.destination / 'mpv-0.40.0'
patch = args.patches / '0003-mpv-request-api-upstream.patch'
# The PR predates the options-file rename and a neighboring Vulkan option's
# removal. Backport this one option explicitly; apply every C/meson code hunk.
adapted = args.destination / 'request-mpv040.patch'
parts = patch.read_text().split('diff --git ')
assert len([p for p in parts if p.startswith('a/meson_options.txt ')]) == 1
code_patch = ''.join('diff --git ' + p for p in parts[1:] if not p.startswith('a/meson_options.txt '))
check = "cc.has_header_symbol('libavutil/hwcontext.h', 'AV_HWDEVICE_TYPE_V4L2REQUEST')"
assert code_patch.count(check) == 1
# An isolated FFmpeg prefix is supplied by pkg-config, not a system header.
code_patch = code_patch.replace(check, check[:-1] + ', dependencies: libavutil)')
options = (source / 'meson.options').read_text()
anchor = "option('ios-gl', type: 'feature', value: 'auto', description: 'iOS OpenGL ES interop support')\n"
assert options.count(anchor) == 1
updated = options.replace(anchor, anchor + "option('v4l2request', type: 'feature', value: 'disabled', description: 'V4L2 Request API hwaccel')\n")
option_patch = ''.join(difflib.unified_diff(options.splitlines(True), updated.splitlines(True), fromfile='a/meson.options', tofile='b/meson.options'))
adapted.write_text(code_patch + option_patch)
for check in [True, False]:
    subprocess.run(['patch', '-p1', '--fuzz=0', '--batch', *(['--dry-run'] if check else []), '-i', str(adapted.resolve())], cwd=source, check=True)
env = dict(os.environ,
           PKG_CONFIG_PATH=str(args.ffmpeg_prefix / 'lib/pkgconfig') + ':' + str(args.deps_sysroot / 'usr/lib/arm-linux-gnueabihf/pkgconfig'),
           PKG_CONFIG_LIBDIR='/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig')
command = ['meson', 'setup', str(args.destination / 'build'), str(source),
           '--cross-file', str(args.cross_file), '--prefix', str(args.ffmpeg_prefix),
           '--libdir=lib', '--buildtype=release', '--wrap-mode=nofallback',
           '-Dauto_features=disabled', '-Dlua=lua52', '-Dv4l2request=enabled',
           '-Dgl=enabled', '-Dplain-gl=enabled', '-Ddrm=enabled', '-Degl=enabled',
           '-Dwayland=enabled', '-Degl-wayland=enabled', '-Dpipewire=enabled',
           '-Dc_args=-I' + str(args.deps_sysroot / 'usr/include/arm-linux-gnueabihf'),
           '-Dlibmpv=true', '-Dcplayer=true', '-Dc_link_args=-Wl,--allow-shlib-undefined']
subprocess.run(command, env=env, check=True)
subprocess.run(['ninja', '-C', str(args.destination / 'build'), '-j2'], env=env, check=True)
subprocess.run(['meson', 'install', '-C', str(args.destination / 'build')], env=env, check=True)
record = dict(version='0.40.0', archive_sha256=sha, upstream_pr='https://github.com/mpv-player/mpv/pull/14511',
              upstream_patch_sha256=hashlib.file_digest(patch.open('rb'), 'sha256').hexdigest(),
              applied_patch_sha256=hashlib.file_digest(adapted.open('rb'), 'sha256').hexdigest(), meson=command,
              files={str(p.relative_to(args.ffmpeg_prefix)): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
                     for p in args.ffmpeg_prefix.rglob('*') if p.is_file() and not p.is_symlink()})
(args.destination / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
print('VDE_MPV_RUNTIME_BUILT_NOT_INSTALLED')
