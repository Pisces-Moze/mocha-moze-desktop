#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Minimal Mesa cross-build dependencies for a Debian 13 amd64 build host.
set -euo pipefail
test "$EUID" = 0
. /etc/os-release
test "$ID" = debian && test "$VERSION_CODENAME" = trixie
test "$(dpkg --print-architecture)" = amd64
dpkg --add-architecture armhf
apt-get update
apt-get -o DPkg::Lock::Timeout=600 -y --no-install-recommends install \
  ca-certificates curl xz-utils git patch build-essential pkg-config meson ninja-build \
  python3-mako python3-yaml python3-packaging bison flex \
  g++-arm-linux-gnueabihf libwayland-bin wayland-protocols \
  libwayland-dev:armhf libwayland-egl-backend-dev:armhf libglvnd-dev:armhf \
  libdrm-dev:armhf libudev-dev:armhf libexpat1-dev:armhf libelf-dev:armhf \
  libzstd-dev:armhf zlib1g-dev:armhf
