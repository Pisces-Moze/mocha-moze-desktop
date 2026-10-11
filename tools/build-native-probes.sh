#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
out=$(realpath -m "${1:?artifact output directory}")
mkdir -p "$out"
export PKG_CONFIG_LIBDIR=/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig
export PKG_CONFIG_ALLOW_CROSS=1
cc=${CC:-arm-linux-gnueabihf-gcc}
wayland-scanner client-header /usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml "$out/xdg-shell.h"
wayland-scanner private-code /usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml "$out/xdg-shell.c"
"$cc" -O2 -I"$out" "$repo/performance/native-frame-timing.c" "$out/xdg-shell.c" -o "$out/native-frame-timing" $(pkg-config --cflags --libs egl glesv2 wayland-client wayland-egl)
"$cc" -O2 "$repo/performance/native-fence-test.c" -o "$out/native-fence-test" $(pkg-config --cflags --libs egl glesv2 gbm)
"$cc" -O2 "$repo/performance/atomic-fence-scanout.c" -o "$out/atomic-fence-scanout" $(pkg-config --cflags --libs egl glesv2 gbm libdrm)
(cd "$out"; sha256sum native-frame-timing native-fence-test atomic-fence-scanout > SHA256SUMS)
