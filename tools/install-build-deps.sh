#!/bin/bash
# Run on a Debian 13 amd64 build host, not in the tablet's small APP filesystem.
set -euo pipefail
test "$EUID" = 0
. /etc/os-release
test "$ID" = debian && test "$VERSION_CODENAME" = trixie
dpkg --add-architecture armhf
cat > /etc/apt/sources.list.d/mocha-build-backports.sources <<'EOF'
Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie-backports
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
apt-get update
apt-get -o DPkg::Lock::Timeout=600 -y --no-install-recommends install \
  git curl python3 patch clang libclang-dev meson ninja-build pkg-config cmake \
  g++-arm-linux-gnueabihf wayland-protocols libwayland-bin \
  libsdbus-c++-dev:armhf libwayland-dev:armhf libfreetype-dev:armhf \
  libfontconfig-dev:armhf libcairo2-dev:armhf libpango1.0-dev:armhf \
  libharfbuzz-dev:armhf librsvg2-dev:armhf libxkbcommon-dev:armhf \
  libglib2.0-dev:armhf libsecret-1-dev:armhf libsodium-dev:armhf \
  libpolkit-agent-1-dev:armhf libpolkit-gobject-1-dev:armhf \
  libpipewire-0.3-dev:armhf libwireplumber-0.5-dev:armhf libcurl4-gnutls-dev:armhf \
  libqalculate-dev:armhf libxml2-dev:armhf libmd4c-dev:armhf \
  nlohmann-json3-dev libtomlplusplus-dev:armhf libical-dev:armhf \
  libegl-dev:armhf libgles-dev:armhf libepoxy-dev:armhf \
  libwebp-dev:armhf libjxl-dev:armhf libsndfile1-dev:armhf \
  libudev-dev:armhf libgbm-dev:armhf libinput-dev:armhf libseat-dev:armhf \
  libdisplay-info-dev:armhf libliftoff-dev:armhf libsystemd-dev:armhf libdbus-1-dev:armhf
apt-get -o DPkg::Lock::Timeout=600 -y --no-install-recommends \
  -t trixie-backports install rustc cargo libstd-rust-dev:armhf
