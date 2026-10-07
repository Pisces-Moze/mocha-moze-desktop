#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd);mkdir -p "$repo/build"
export PKG_CONFIG_LIBDIR=/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig
arm-linux-gnueabihf-gcc -O2 -Wall -Wextra "$repo/charging/mocha-charger-ui.c" \
 $(pkg-config --cflags --libs cairo) -lm -o "$repo/build/mocha-charger-ui"
