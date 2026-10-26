#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the actual command-ring flag policy and exercise device/domain gates."""
from pathlib import Path
import os, subprocess, sys, tempfile

source = (Path(sys.argv[1])/'src/gallium/winsys/nouveau/drm/nouveau.c').read_text()
start = source.index('   nvpb->type |= NOUVEAU_BO_MAP;', source.index('nouveau_pushbuf_new('))
end = source.index('   for (nvpb->bo_nr', start)
policy = source[start:end]
assert 'NOUVEAU_BO_COHERENT' in policy
# Ring growth must inherit the stored type as well as the initial allocation.
assert source.count('nouveau_bo_new(client->device, nvpb->type,') == 2
program = r'''
#include <assert.h>
#include <stdint.h>
#define NOUVEAU_BO_GART 2
#define NOUVEAU_BO_MAP 0x80000000u
#define NOUVEAU_BO_COHERENT 0x10000000u
struct device {unsigned chipset;};
struct client {struct device *device;};
struct drm {unsigned version;};
struct push {unsigned type;};
static unsigned flags(unsigned chipset,unsigned version,unsigned input) {
 struct device device={chipset};struct client c={&device};
 struct drm d={version};struct push p={input};
 struct client *client=&c;struct drm *drm=&d;struct push *nvpb=&p;
 POLICY
 return p.type;
}
int main(void) {
 unsigned map=NOUVEAU_BO_MAP,coherent=NOUVEAU_BO_COHERENT,gart=NOUVEAU_BO_GART;
 assert(flags(0xea,0x01000301,gart)==(gart|map|coherent));
 assert(flags(0xea,0x01000202,gart)==(gart|map|coherent));
 assert(flags(0xea,0x01000201,gart)==(gart|map));
 assert(flags(0x12b,0x01000301,gart)==(gart|map));
 assert(flags(0xe4,0x01000301,gart)==(gart|map));
 assert(flags(0xea,0x01000301,1)==(1|map));
 assert(flags(0xea,0x01000301,gart|0x40)==(gart|0x40|map|coherent));
 assert(flags(0xea,0x01000301,gart|coherent)==(gart|map|coherent));
 return 0;
}
'''.replace('POLICY', policy)
with tempfile.TemporaryDirectory(prefix='mesa-command-upload-') as directory:
    p=Path(directory);(p/'test.c').write_text(program)
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
print('MESA_COMMAND_UPLOAD_8_POLICY_CASES_PASSED')
