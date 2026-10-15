#!/usr/bin/env python3
"""Compile and exercise Mesa's actual optional-fence wrapper code in isolation.

Run against an unpacked Mesa 25.0.7 tree before and after patch 0004.
The unpatched tree must fail; the patched tree must pass. This checks callback
registration and argument forwarding, not the complete Mesa build or hardware.
SPDX-License-Identifier: GPL-2.0-only
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def function(source, name):
    match = re.search(r'static (?:void|int)\n' + name + r'\([^\n]*(?:\n[^{}]*)?\n\{.*?\n\}', source, re.S)
    if not match:
        raise ValueError('Cannot locate Mesa function: ' + name)
    return match.group()


def between(source, start, end):
    return source.split(start, 1)[1].split(end, 1)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--cc', default='cc', help='C compiler executable, or cl for MSVC')
    args = parser.parse_args()
    if (args.source / 'VERSION').read_text(encoding='utf-8').strip() != '25.0.7':
        parser.error('Expected Mesa 25.0.7')
    directory = args.source / 'src/gallium/drivers/tegra'
    context = (directory / 'tegra_context.c').read_text(encoding='utf-8')
    screen = (directory / 'tegra_screen.c').read_text(encoding='utf-8')
    context_registration = between(context, 'context->base.flush = tegra_flush;', 'context->base.create_sampler_view =')
    screen_registration = between(screen, 'screen->base.fence_finish = tegra_screen_fence_finish;', 'screen->base.get_driver_query_info =')
    code = r'''
#include <stdio.h>
#include <stdlib.h>
struct pipe_fence_handle { int value; };
enum pipe_fd_type { PIPE_FD_TYPE_NATIVE_SYNC };
struct pipe_context {
   void (*create_fence_fd)(struct pipe_context *, struct pipe_fence_handle **, int, enum pipe_fd_type);
   void (*fence_server_sync)(struct pipe_context *, struct pipe_fence_handle *);
};
struct pipe_screen { int (*fence_get_fd)(struct pipe_screen *, struct pipe_fence_handle *); };
struct tegra_context { struct pipe_context base; struct pipe_context *gpu; };
struct tegra_screen { struct pipe_screen base; struct pipe_screen *gpu; };
static struct tegra_context *to_tegra_context(struct pipe_context *p) { return (struct tegra_context *)p; }
static struct tegra_screen *to_tegra_screen(struct pipe_screen *p) { return (struct tegra_screen *)p; }
#define assert(x) do { if (!(x)) { fprintf(stderr, "FAIL: %s at line %d\n", #x, __LINE__); exit(1); } } while (0)
'''
    code += function(context, 'tegra_create_fence_fd') + '\n'
    code += function(context, 'tegra_fence_server_sync') + '\n'
    code += function(screen, 'tegra_screen_fence_get_fd') + '\n'
    code += '\nstatic void register_context(struct tegra_context *context) {' + context_registration + '}\n'
    code += '\nstatic void register_screen(struct tegra_screen *screen) {' + screen_registration + '}\n'
    code += r'''
static struct pipe_context *expected_context;
static struct pipe_screen *expected_screen;
static struct pipe_fence_handle expected_fence = { 7 };
static int sync_calls, import_calls, export_calls;
static void gpu_sync(struct pipe_context *p, struct pipe_fence_handle *f) {
   assert(p == expected_context); assert(f == &expected_fence); ++sync_calls;
}
static void gpu_import(struct pipe_context *p, struct pipe_fence_handle **f, int fd, enum pipe_fd_type type) {
   assert(p == expected_context); assert(fd == 17); assert(type == PIPE_FD_TYPE_NATIVE_SYNC);
   *f = &expected_fence; ++import_calls;
}
static int gpu_export(struct pipe_screen *p, struct pipe_fence_handle *f) {
   assert(p == expected_screen); assert(f == &expected_fence); ++export_calls; return 23;
}
int main(void) {
   for (unsigned mask = 0; mask < 8; ++mask) {
      struct pipe_context gpu_context = { 0 };
      struct pipe_screen gpu_screen = { 0 };
      struct tegra_context context = { { 0 }, &gpu_context };
      struct tegra_screen screen = { { 0 }, &gpu_screen };
      struct pipe_fence_handle *imported = NULL;
      expected_context = &gpu_context; expected_screen = &gpu_screen;
      sync_calls = import_calls = export_calls = 0;
      if (mask & 1) gpu_context.fence_server_sync = gpu_sync;
      if (mask & 2) gpu_context.create_fence_fd = gpu_import;
      if (mask & 4) gpu_screen.fence_get_fd = gpu_export;
      register_context(&context); register_screen(&screen);
      assert(!!context.base.fence_server_sync == !!(mask & 1));
      assert(!!context.base.create_fence_fd == !!(mask & 2));
      assert(!!screen.base.fence_get_fd == !!(mask & 4));
      if (context.base.fence_server_sync) context.base.fence_server_sync(&context.base, &expected_fence);
      if (context.base.create_fence_fd) {
         context.base.create_fence_fd(&context.base, &imported, 17, PIPE_FD_TYPE_NATIVE_SYNC);
         assert(imported == &expected_fence);
      }
      if (screen.base.fence_get_fd) assert(screen.base.fence_get_fd(&screen.base, &expected_fence) == 23);
      assert(sync_calls == !!(mask & 1)); assert(import_calls == !!(mask & 2)); assert(export_calls == !!(mask & 4));
   }
   puts("MESA_OPTIONAL_FENCE_CALLBACKS=PASS (8 combinations)");
   return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='mocha-mesa-fence-') as temporary:
        directory = Path(temporary)
        source, executable = directory / 'test.c', directory / 'test.exe'
        source.write_text(code, encoding='utf-8')
        if Path(args.cc).name.lower() in ('cl', 'cl.exe'):
            command = [args.cc, '/nologo', '/std:c11', '/W4', '/WX', str(source), '/Fe:' + str(executable)]
        else:
            command = [args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(executable)]
        subprocess.run(command, check=True, cwd=directory)
        subprocess.run([str(executable)], check=True, cwd=directory)


if __name__ == '__main__':
    main()
