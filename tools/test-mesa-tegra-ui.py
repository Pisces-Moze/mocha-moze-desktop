#!/usr/bin/env python3
"""Exercise the real Tegra reset wrappers and scissor forwarding from Mesa 25.0.7."""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

def function(source, name):
    match = re.search(r"static (?:void|enum pipe_reset_status)\n" + name + r"\(.*?\n\{.*?\n\}", source, re.S)
    if match is None:
        raise ValueError("Missing function: " + name)
    return match.group()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = (args.source / "src/gallium/drivers/tegra/tegra_context.c").read_text()
    registration = source.split("context->base.invalidate_resource = tegra_invalidate_resource;", 1)[1].split("context->base.dump_debug_state =", 1)[0]
    code = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
struct pipe_scissor_state { unsigned minx, miny, maxx, maxy; };
union pipe_color_union { float f[4]; };
enum pipe_reset_status { PIPE_NO_RESET, PIPE_GUILTY_CONTEXT_RESET };
struct pipe_device_reset_callback { unsigned serial; };
struct pipe_context {
 void (*clear)(struct pipe_context *, unsigned, const struct pipe_scissor_state *, const union pipe_color_union *, double, unsigned);
 enum pipe_reset_status (*get_device_reset_status)(struct pipe_context *);
 void (*set_device_reset_callback)(struct pipe_context *, const struct pipe_device_reset_callback *);
};
struct tegra_context { struct pipe_context base; struct pipe_context *gpu; };
static struct tegra_context *to_tegra_context(struct pipe_context *p) { return (struct tegra_context *)p; }
"""
    for name in ("tegra_clear", "tegra_get_device_reset_status", "tegra_set_device_reset_callback"):
        code += function(source, name) + "\n"
    code += "static void register_reset(struct tegra_context *context) {" + registration + "}\n"
    code += r"""
static struct pipe_context *expected_gpu;
static const struct pipe_scissor_state *expected_scissor;
static union pipe_color_union color = { .f = { 0.25f, 0.5f, 0.75f, 1 } };
static unsigned clear_calls, reset_calls;
static void gpu_clear(struct pipe_context *gpu, unsigned buffers, const struct pipe_scissor_state *scissor, const union pipe_color_union *c, double depth, unsigned stencil) {
 assert(gpu == expected_gpu); assert(buffers == 5); assert(scissor == expected_scissor);
 assert(c == &color); assert(depth == 0.25); assert(stencil == 7); ++clear_calls;
}
static enum pipe_reset_status gpu_status(struct pipe_context *gpu) {
 assert(gpu == expected_gpu); return PIPE_GUILTY_CONTEXT_RESET;
}
static void gpu_callback(struct pipe_context *gpu, const struct pipe_device_reset_callback *cb) {
 assert(gpu == expected_gpu); assert(cb->serial == 17); ++reset_calls;
}
int main(void) {
 for (unsigned mask = 0; mask < 4; ++mask) {
   struct pipe_context gpu = { .clear = gpu_clear };
   struct tegra_context context = { .gpu = &gpu };
   expected_gpu = &gpu;
   if (mask & 1) gpu.get_device_reset_status = gpu_status;
   if (mask & 2) gpu.set_device_reset_callback = gpu_callback;
   register_reset(&context);
   assert(!!context.base.get_device_reset_status == !!(mask & 1));
   assert(!!context.base.set_device_reset_callback == !!(mask & 2));
   if (context.base.get_device_reset_status)
     assert(context.base.get_device_reset_status(&context.base) == PIPE_GUILTY_CONTEXT_RESET);
   reset_calls = 0;
   if (context.base.set_device_reset_callback) {
     struct pipe_device_reset_callback cb = { .serial = 17 };
     context.base.set_device_reset_callback(&context.base, &cb);
   }
   assert(reset_calls == !!(mask & 2));
   struct pipe_scissor_state rectangle = { 12, 24, 48, 96 };
   clear_calls = 0;
   expected_scissor = &rectangle;
   tegra_clear(&context.base, 5, &rectangle, &color, 0.25, 7);
   expected_scissor = NULL;
   tegra_clear(&context.base, 5, NULL, &color, 0.25, 7);
   assert(clear_calls == 2);
 }
 puts("MESA_TEGRA_RESET_AND_SCISSOR=PASS (4 callback combinations)");
}
"""
    with tempfile.TemporaryDirectory(prefix="mocha-mesa-ui-") as temporary:
        directory = Path(temporary)
        cfile, executable = directory / "test.c", directory / "test"
        cfile.write_text(code)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)

if __name__ == "__main__":
    main()
