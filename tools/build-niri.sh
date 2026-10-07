#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd);src=$(realpath "${1:?unpacked Niri26.04 tree}")
test -f "$src/vendor/smithay/.cargo-checksum.json"
test -f "$src/.cargo/config.toml"
cmp "$repo/Cargo.lock" "$src/Cargo.lock"
patch --directory="$src/vendor/smithay" -p1 < "$repo/patches/0003-smithay-complete-rotated-damage.patch"
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
cargo clean --offline -p smithay --target armv7-unknown-linux-gnueabihf
cargo build --locked --offline --release -j"${JOBS:-4}" --target armv7-unknown-linux-gnueabihf --no-default-features --features dbus,systemd
