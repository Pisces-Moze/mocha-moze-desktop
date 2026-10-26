#!/bin/sh
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:?output directory}
mkdir -p "$out"
protocols=$(pkg-config --variable=pkgdatadir wayland-protocols)
wayland-scanner client-header "$protocols/stable/xdg-shell/xdg-shell.xml" "$out/xdg-shell-client-protocol.h"
wayland-scanner private-code "$protocols/stable/xdg-shell/xdg-shell.xml" "$out/xdg-shell-protocol.c"
# pkg-config emits compiler arguments from the selected build sysroot.
${CC:-cc} -O2 -Wall -Wextra -Werror -I"$out" "$src/occlusion-test-window.c" \
    "$out/xdg-shell-protocol.c" $(pkg-config --cflags --libs wayland-client) -o "$out/occlusion-test-window"
