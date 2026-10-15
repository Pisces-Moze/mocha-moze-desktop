#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Keep large font data on the data volume; preserve package licenses.
set -euo pipefail
account=${MOCHA_ACCOUNT:-mocha}
home_dir=$(getent passwd "$account" | cut -d: -f6)
stage=/srv/mocha-data/codex-debian-desktop/tablet-font-packages
mkdir -p "$stage" "$home_dir/.local/share/fonts/mocha-tablet"
cd "$stage"
apt-get download fonts-noto-core fonts-noto-color-emoji
for package in fonts-noto-{core,color-emoji}_*.deb; do
    mkdir -p "${package%.deb}"
    dpkg-deb -x "$package" "${package%.deb}"
done
for name in NotoSansSymbols-Regular.ttf NotoSansSymbols2-Regular.ttf NotoColorEmoji.ttf; do
    font=$(find "$stage" -type f -name "$name" -print -quit)
    test -n "$font"
    install -m 644 "$font" "$home_dir/.local/share/fonts/mocha-tablet/$name"
done
chown -R "$account:$(id -gn "$account")" "$home_dir/.local/share/fonts/mocha-tablet"
runuser -u "$account" -- fc-cache -f "$home_dir/.local/share/fonts/mocha-tablet"
printf 'Keyboard symbols and emoji fonts installed on data volume. Licenses: %s\n' "$stage"
