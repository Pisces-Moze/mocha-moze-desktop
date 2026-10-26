#!/usr/bin/env python3
"""Build an isolated ARMv7 FFmpeg Request API runtime; never installs globally."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path, required=True)
parser.add_argument('--patches', type=Path, required=True)
parser.add_argument('--destination', type=Path, required=True)
parser.add_argument('--jobs', type=int, default=2)
args = parser.parse_args()
assert 1 <= args.jobs <= 4
expected = 'de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f'
assert hashlib.file_digest(args.archive.open('rb'), 'sha256').hexdigest() == expected
assert not args.destination.exists(), 'Use a new, dedicated build directory'
args.destination.mkdir(parents=True)
with tarfile.open(args.archive) as archive:
    archive.extractall(args.destination, filter='data')
source = args.destination / 'ffmpeg-7.1.5'
build = args.destination / 'build'
prefix = args.destination / 'runtime'
build.mkdir()
env = dict(os.environ, PKG_CONFIG_LIBDIR='/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig')
records = {}
for name in ['0001-ffmpeg-7.1-request-api-upstream.patch', '0002-ffmpeg-request-three-plane-yuv420.patch', '0005-ffmpeg-request-multiplanar-queue.patch', '0006-ffmpeg-linear-planar-download.patch']:
    patch = (args.patches / name).resolve()
    records[name] = hashlib.file_digest(patch.open('rb'), 'sha256').hexdigest()
    for check in [True, False]:
        subprocess.run(['patch', '-p1', '--fuzz=0', '--batch', *(['--dry-run'] if check else []), '-i', str(patch)], cwd=source, check=True)
configure = [str(source / 'configure'), '--prefix=' + str(prefix),
             '--enable-cross-compile', '--cross-prefix=arm-linux-gnueabihf-',
             '--arch=arm', '--cpu=cortex-a15', '--target-os=linux',
             '--extra-cflags=-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard',
             '--disable-autodetect', '--enable-libdrm', '--enable-libudev',
             '--enable-v4l2-request', '--enable-gnutls', '--enable-shared',
             '--disable-static', '--disable-debug', '--disable-doc',
             '--disable-encoders', '--enable-encoder=rawvideo', '--disable-avdevice',
             '--disable-postproc', '--disable-ffplay']
subprocess.run(configure, cwd=build, env=env, check=True)
config = (build / 'config.h').read_text()
assert '#define CONFIG_V4L2_REQUEST 1' in config
assert '#define CONFIG_LIBDRM 1' in config
subprocess.run(['make', '-j' + str(args.jobs)], cwd=build, env=env, check=True)
subprocess.run(['make', 'install'], cwd=build, env=env, check=True)
manifest = dict(version='7.1.5', request_base_commit='fad85d9c76611c09b561167ab405c667a0dcdeb7',
                source_sha256=expected, patch_sha256=records, configure=configure,
                files={str(p.relative_to(prefix)): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
                       for p in prefix.rglob('*') if p.is_file() and not p.is_symlink()})
(args.destination / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('VDE_FFMPEG_RUNTIME_BUILT_NOT_INSTALLED')
