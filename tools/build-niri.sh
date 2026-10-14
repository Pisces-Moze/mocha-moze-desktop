#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
src=$(realpath "${1:?unpacked Niri26.04 tree}")
test -f "$src/vendor/smithay/.cargo-checksum.json"
test -f "$src/.cargo/config.toml"
cmp "$repo/Cargo.lock" "$src/Cargo.lock"
apply_patch() {
 local dir=$1 patch_file=$2
 if patch --batch --forward --dry-run -d "$dir" -p1 < "$patch_file" >/dev/null; then
  patch --batch --forward -d "$dir" -p1 < "$patch_file"
 elif patch --batch --reverse --dry-run -d "$dir" -p1 < "$patch_file" >/dev/null; then
  echo "Already applied: $(basename "$patch_file")"
 else
  echo "Source does not match $(basename "$patch_file")" >&2; exit 1
 fi
}
apply_patch "$src/vendor/smithay" "$repo/patches/0003-smithay-complete-rotated-damage.patch"
if [ "${MOCHA_TEGRA_EXPLICIT_FENCE:-0}" = 1 ]; then
 apply_patch "$src/vendor/smithay" "$repo/patches/0009-smithay-tegra-explicit-fence.patch"
fi
if [ "${MOCHA_FRAME_PROFILE_BUILD:-0}" = 1 ]; then
 apply_patch "$src" "$repo/patches/0011-niri-frame-profile.patch"
fi
if [ "${MOCHA_TABLET_GESTURES:-0}" = 1 ]; then
 # Verify the upstream-authored, GPL-3.0 tablet patches before applying in order.
 python3 - "$repo/patches/tablet" <<'PY'
import hashlib, json, sys
from pathlib import Path
p = Path(sys.argv[1])
for entry in json.loads((p / 'source.json').read_text())['patches']:
    assert hashlib.sha256((p / entry['path']).read_bytes()).hexdigest() == entry['sha256'], entry['path']
PY
 for patch_file in "$repo"/patches/tablet/*.patch; do
  apply_patch "$src" "$patch_file"
 done
fi
python3 - "$src/vendor/smithay" <<'PY'
import sys,json,hashlib
from pathlib import Path
p=Path(sys.argv[1]);f=p/'.cargo-checksum.json';d=json.loads(f.read_text())
key='src/backend/drm/compositor/mod.rs';d['files'][key]=hashlib.sha256((p/key).read_bytes()).hexdigest();f.write_text(json.dumps(d,separators=(',',':')))
PY
cd "$src"
export CARGO_TARGET_ARMV7_UNKNOWN_LINUX_GNUEABIHF_LINKER=arm-linux-gnueabihf-gcc
export PKG_CONFIG_ALLOW_CROSS=1
export PKG_CONFIG_LIBDIR=/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig
export BINDGEN_EXTRA_CLANG_ARGS='--target=arm-linux-gnueabihf -I/usr/include/arm-linux-gnueabihf'
export CARGO_PROFILE_RELEASE_LTO=false CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
# Vendored source changes do not reliably invalidate Cargo's release cache.
cargo clean --offline --release -p smithay --target armv7-unknown-linux-gnueabihf
cargo build --locked --offline --release -j"${JOBS:-4}" --target armv7-unknown-linux-gnueabihf --no-default-features --features dbus,systemd
sync
