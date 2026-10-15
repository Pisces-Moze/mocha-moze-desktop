#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Test the real Tegra modifier converters against DRM's layout equivalence."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
args = parser.parse_args()
source = (args.source / "src/gallium/drivers/tegra/tegra_screen.c").read_text()
functions = []
for name in ("tegra_screen_scanout_modifier", "tegra_screen_gpu_modifier"):
    match = re.search(r"static uint64_t\n" + name + r"\(.*?\n\{.*?\n\}", source, re.S)
    if match is None:
        raise ValueError("Missing source function: " + name)
    functions.append(match.group())
code = '#include <stdint.h>\n#include <assert.h>\n#include <stdio.h>\n#include <drm_fourcc.h>\n'
code += '\n'.join(functions)
code += r'''
int main(void) {
    unsigned tested = 0;
    for (unsigned h = 0; h <= 5; ++h) {
        uint64_t legacy = DRM_FORMAT_MOD_NVIDIA_16BX2_BLOCK(h);
        uint64_t canonical = drm_fourcc_canonicalize_nvidia_format_mod(legacy);
        assert(tegra_screen_gpu_modifier(legacy) == canonical);
        assert(tegra_screen_gpu_modifier(canonical) == canonical);
        assert(tegra_screen_scanout_modifier(canonical) == legacy);
        assert(tegra_screen_scanout_modifier(legacy) == legacy);
    }
    const unsigned kinds[] = { 0, 1, 0xfe, 0xff };
    for (unsigned c = 0; c < 8; c++)
    for (unsigned s = 0; s < 2; s++)
    for (unsigned g = 0; g < 4; g++)
    for (unsigned k = 0; k < 4; k++)
    for (unsigned h = 0; h < 16; h++) {
        uint64_t m = DRM_FORMAT_MOD_NVIDIA_BLOCK_LINEAR_2D(c,s,g,kinds[k],h);
        if (c == 0 && s == 0 && g == 0 && h <= 5 && (kinds[k] == 0 || kinds[k] == 0xfe))
            continue;
        assert(tegra_screen_gpu_modifier(m) == m);
        assert(tegra_screen_scanout_modifier(m) == m);
        ++tested;
    }
    const uint64_t other[] = { DRM_FORMAT_MOD_LINEAR, DRM_FORMAT_MOD_INVALID,
        DRM_FORMAT_MOD_NVIDIA_TEGRA_TILED, fourcc_mod_code(INTEL, 0xfe014) };
    for (unsigned i = 0; i < sizeof(other)/sizeof(other[0]); i++) {
        assert(tegra_screen_gpu_modifier(other[i]) == other[i]);
        assert(tegra_screen_scanout_modifier(other[i]) == other[i]);
    }
    printf("MESA_TEGRA_MODIFIER_ALIASES=PASS (6 round trips, %u other layouts preserved)\n",tested);
}
'''
with tempfile.TemporaryDirectory(prefix="mocha-modifiers-") as temporary:
    directory = Path(temporary)
    c_file = directory / "test.c"
    executable = directory / "test"
    c_file.write_text(code)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I/usr/include/libdrm", str(c_file), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
