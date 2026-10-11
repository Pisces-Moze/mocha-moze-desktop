#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
src=$(realpath "${1:?unpacked Noctalia 5.2.1 source}")
stage=$(realpath -m "${2:?package staging directory}")
test "$(cat "$src/VERSION")" = 5.2.1
test ! -e "$stage"
patch_file="$repo/patches/0010-noctalia-optional-egl-robustness.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match optional robustness patch' >&2; exit 1
fi
meson setup "$src/build-moze-armhf" "$src" \
  --cross-file "$repo/noctalia-armhf-cross.ini" --buildtype=release \
  --prefix=/usr/local -Dtests=disabled -Djemalloc=disabled -Dnative_optimizations=false
ninja -j"${JOBS:-4}" -C "$src/build-moze-armhf" noctalia
DESTDIR="$stage" meson install --no-rebuild -C "$src/build-moze-armhf"
arm-linux-gnueabihf-strip --strip-unneeded "$stage/usr/local/bin/noctalia"
arm-linux-gnueabihf-readelf -d "$stage/usr/local/bin/noctalia" | grep NEEDED
