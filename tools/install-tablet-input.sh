#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Install the offline IM framework; the touch keyboard is deliberately manual.
set -euo pipefail
test "$(id -u)" = 0
repo=$(cd "$(dirname "$0")/.." && pwd)
account=${MOCHA_ACCOUNT:-mocha}
home_dir=$(getent passwd "$account" | cut -d: -f6)
uid=$(id -u "$account")
test -d "$home_dir"
command -v fcitx5 >/dev/null
command -v wtype >/dev/null
python3 -c "import gi; gi.require_version('Gtk', '3.0'); gi.require_version('GtkLayerShell', '0.1')"
userctl() { runuser -u "$account" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user "$@"; }
# Fcitx saves its live profile when exiting. Stop it before replacing the file.
userctl stop mocha-input-method.service || true
runuser -u "$account" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" fcitx5-remote -e || true
for attempt in {1..30}; do
    pgrep -u "$uid" -x fcitx5 >/dev/null || break
    sleep 0.1
done
if pgrep -u "$uid" -x fcitx5 >/dev/null; then echo 'Existing input method has not exited' >&2; exit 1; fi
backup="$home_dir/.local/state/mocha-backups/input-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup" "$home_dir/.config/fcitx5/conf" "$home_dir/.config/systemd/user" "$home_dir/.config/environment.d" "$home_dir/.local/share/applications"
for path in .config/fcitx5/profile .config/fcitx5/config .config/fcitx5/conf/classicui.conf .config/environment.d/80-mocha-input.conf; do
    if [ -f "$home_dir/$path" ]; then mkdir -p "$backup/$(dirname "$path")"; cp -a "$home_dir/$path" "$backup/$path"; fi
done
install -m 644 "$repo/tablet/fcitx5-profile" "$home_dir/.config/fcitx5/profile"
install -m 644 "$repo/tablet/fcitx5-config" "$home_dir/.config/fcitx5/config"
install -m 644 "$repo/tablet/fcitx5-classicui.conf" "$home_dir/.config/fcitx5/conf/classicui.conf"
cat > "$home_dir/.config/environment.d/80-mocha-input.conf" <<'EOF'
XMODIFIERS=@im=fcitx
QT_IM_MODULE=fcitx
SDL_IM_MODULE=fcitx
EOF
# GTK Wayland applications use native text-input-v3, not a global GTK override.
install -m 755 "$repo/tablet/mocha-touch-keyboard.py" /usr/local/libexec/mocha-touch-keyboard.py
install -m 755 "$repo/tablet/mocha-session-exec" /usr/local/libexec/mocha-session-exec
install -m 755 "$repo/tablet/mocha-touch-nav" /usr/local/bin/mocha-touch-nav
install -m 755 "$repo/tablet/mocha-touch-key-lights.py" /usr/local/libexec/mocha-touch-key-lights.py
install -m 644 "$repo/tablet/mocha-touch-key-lights.service" /etc/systemd/system/
install -m 644 "$repo/tablet/mocha-backlight-access.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mocha-backlight-access.service
systemctl enable --now mocha-touch-key-lights.service
for name in mocha-input-method mocha-keyboard; do
    install -m 755 "$repo/tablet/$name" "/usr/local/bin/$name"
    install -m 644 "$repo/tablet/$name.service" "$home_dir/.config/systemd/user/"
    install -m 644 "$repo/tablet/$name.desktop" "$home_dir/.local/share/applications/"
done
chown -R "$account:$(id -gn "$account")" "$home_dir/.config/fcitx5" "$backup"
chown "$account:$(id -gn "$account")" "$home_dir/.config/environment.d/80-mocha-input.conf" "$home_dir/.config/systemd/user/"mocha-{input-method,keyboard}.service "$home_dir/.local/share/applications/"mocha-{input-method,keyboard}.desktop
userctl daemon-reload
userctl set-environment XMODIFIERS=@im=fcitx QT_IM_MODULE=fcitx SDL_IM_MODULE=fcitx
userctl enable --now mocha-input-method.service
printf 'Input method installed; manual keyboard launcher installed. Backup: %s\n' "$backup"
