#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
src=$(realpath "${1:?unpacked Noctalia 5.2.1 source}")
stage=$(realpath -m "${2:?package staging directory}")
test "$(cat "$src/VERSION")" = 5.2.1
test ! -e "$stage"
patch_file="$repo/patches/0019-noctalia-bluetooth-agent-lifecycle.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match Bluetooth agent lifecycle patch' >&2; exit 1
fi
patch_file="$repo/patches/0020-noctalia-bluetooth-pair-completion.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match Bluetooth pairing completion patch' >&2; exit 1
fi
python3 "$repo/tools/test-bluetooth-pair-completion.py" "$src"
patch_file="$repo/patches/0021-noctalia-touch-keyboard-input-region.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match touch keyboard input region patch' >&2; exit 1
fi
python3 "$repo/tools/test-touch-keyboard-exclusion.py" "$src"
patch_file="$repo/patches/0014-noctalia-native-dock-icons.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match native Dock icon patch' >&2; exit 1
fi
patch_file="$repo/patches/0013-noctalia-arm-luau-alignment.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match ARM Luau alignment patch' >&2; exit 1
fi
patch_file="$repo/patches/0010-noctalia-optional-egl-robustness.patch"
if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 patch --batch --forward -d "$src" -p1 < "$patch_file"
elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
 echo 'Noctalia source does not match optional robustness patch' >&2; exit 1
fi
if [ "${MOCHA_TOUCH_LOCK_KEYBOARD_BUILD:-0}" = 1 ]; then
 patch_file="$repo/patches/0012-noctalia-touch-lock-keyboard.patch"
 if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
  patch --batch --forward -d "$src" -p1 < "$patch_file"
 elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
  echo 'Noctalia source does not match touch lock keyboard patch' >&2; exit 1
 fi
fi
if [ "${MOCHA_HIDDEN_SPECTRUM_IDLE_BUILD:-0}" = 1 ]; then
 patch_file="$repo/patches/0018-noctalia-hidden-spectrum-idle.patch"
 if patch --batch --forward --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
  patch --batch --forward -d "$src" -p1 < "$patch_file"
 elif ! patch --batch --reverse --dry-run -d "$src" -p1 < "$patch_file" >/dev/null; then
  echo 'Noctalia source does not match hidden spectrum idle patch' >&2; exit 1
 fi
 python3 "$repo/tools/test-noctalia-hidden-spectrum.py" "$src"
fi
meson setup "$src/build-moze-armhf" "$src" \
  --cross-file "$repo/noctalia-armhf-cross.ini" --buildtype=release \
  --prefix=/usr/local -Dtests=disabled -Djemalloc=disabled -Dnative_optimizations=false
ninja -j"${JOBS:-4}" -C "$src/build-moze-armhf" noctalia
DESTDIR="$stage" meson install --no-rebuild -C "$src/build-moze-armhf"
arm-linux-gnueabihf-strip --strip-unneeded "$stage/usr/local/bin/noctalia"
arm-linux-gnueabihf-readelf -d "$stage/usr/local/bin/noctalia" | grep NEEDED
