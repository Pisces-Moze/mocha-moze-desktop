#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Build a staged candidate only; never replace the tablet's system Mesa.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
src=$(realpath "${1:?unpacked Mesa 25.0.7 source tree}")
out=$(realpath -m "${2:?new output directory}")
test "$(tr -d '\r\n' < "$src/VERSION")" = 25.0.7
case "$out/" in "$src/"*) echo 'Output must be outside the Mesa source tree' >&2; exit 1;; esac
test ! -e "$out/build" && test ! -e "$out/stage"
patch_file="$repo/patches/0004-mesa-tegra-optional-fence-callbacks.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Mesa fence patch already applied'
else
 echo 'Mesa source does not match patch 0004' >&2; exit 1
fi
# This host test compiles the actual wrapper snippets, not a second implementation.
python3 "$repo/tools/test-mesa-fence-callbacks.py" "$src"
mkdir -p "$out"
meson setup "$out/build" "$src" \
 --cross-file "$repo/mesa-armhf-cross.ini" --buildtype=release \
 --prefix=/opt/mocha-mesa-candidate --libdir=lib/arm-linux-gnueabihf \
 -Dgallium-drivers=nouveau,tegra -Dvulkan-drivers=[] \
 -Dplatforms=wayland -Dglx=disabled -Dglvnd=enabled -Degl=enabled -Dgbm=enabled \
 -Dgles1=disabled -Dgles2=enabled -Dopengl=true -Dllvm=disabled \
 -Dgallium-vdpau=disabled -Dgallium-va=disabled \
 -Dgallium-opencl=disabled -Dvideo-codecs=[] -Dtools=[]
ninja -C "$out/build" -j"${JOBS:-4}"
DESTDIR="$out/stage" meson install -C "$out/build" --no-rebuild
# Mesa installs the combined Gallium DRI target as libgallium-25.0.7.so.
# The loader still looks for a driver-specific *_dri.so entry point; without
# these links EGL silently falls back to llvmpipe or fails eglInitialize.
dri_dir="$out/stage/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf/dri"
gallium="$out/stage/opt/mocha-mesa-candidate/lib/arm-linux-gnueabihf/libgallium-25.0.7.so"
test -s "$gallium"
mkdir -p "$dri_dir"
ln -s ../libgallium-25.0.7.so "$dri_dir/tegra_dri.so"
ln -s ../libgallium-25.0.7.so "$dri_dir/nouveau_dri.so"
(cd "$out/stage"; find . -type f -print0 | sort -z | xargs -0 sha256sum > "$out/SHA256SUMS")
printf '%s\n' 'Staged candidate built; full native desktop/panel acceptance is still required.'
