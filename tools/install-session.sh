#!/bin/bash
set -euo pipefail
user=${1:-mocha};repo=$(cd "$(dirname "$0")/.." && pwd)
test "$EUID" = 0;id "$user" >/dev/null
home=$(getent passwd "$user" | cut -d: -f6)
test -x /usr/local/bin/niri;test -x /usr/local/bin/noctalia
test -f /usr/local/lib/systemd/user/niri.service
test -f /usr/local/lib/systemd/user/niri-shutdown.target
install -d -o "$user" -g "$user" "$home/.config/niri" "$home/.config/noctalia" "$home/Pictures/Wallpapers"
install -o "$user" -g "$user" -m644 "$repo/config/niri.kdl" "$home/.config/niri/config.kdl"
install -o "$user" -g "$user" -m644 "$repo/config/noctalia.toml" "$home/.config/noctalia/config.toml"
usermod -aG video,render,input "$user"
cat >> "$home/.config/noctalia/config.toml" <<EOF

[wallpaper]
directory = "$home/Pictures/Wallpapers"

[brightness]
minimum_brightness = 0.03
enable_ddcutil = false

[brightness.monitor.Unknown-1]
backend = "backlight"
backlight_device = "mocha-miui-backlight"
EOF
if test -f /usr/local/share/noctalia/assets/noctalia-wallpaper.png;then
 install -o "$user" -g "$user" -m644 /usr/local/share/noctalia/assets/noctalia-wallpaper.png "$home/Pictures/Wallpapers/Noctalia.png"
fi
install -d /etc/udev/rules.d
cat > /etc/udev/rules.d/90-mocha-backlight.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="backlight", KERNEL=="mocha-miui-backlight", RUN+="/bin/chgrp video /sys/class/backlight/%k/brightness", RUN+="/bin/chmod g+w /sys/class/backlight/%k/brightness"
EOF
udevadm control --reload-rules
udevadm trigger --subsystem-match=backlight
systemctl enable NetworkManager.service bluetooth.service
cat > /etc/systemd/system/mocha-desktop-hardware.service <<'EOF'
[Unit]
Description=Mocha GPU and backlight before console session
After=local-fs.target systemd-udev-trigger.service
Before=getty@tty1.service
[Service]
Type=oneshot
ExecStart=/sbin/modprobe nouveau
ExecStart=/sbin/modprobe mocha_miui_backlight
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl enable mocha-desktop-hardware.service
# Autologin/session startup is an explicit developer installation choice.
install -d /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/mocha.conf <<EOF
[Unit]
Requires=mocha-desktop-hardware.service
After=mocha-desktop-hardware.service
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $user --noreset --noclear %I linux
EOF
if test -e "$home/.profile";then cp -p "$home/.profile" "$home/.profile.before-mocha";fi
cat >> "$home/.profile" <<'EOF'

# Mocha graphical session starts only on the physical first VT.
if [ "$(tty)" = /dev/tty1 ] && [ -z "${WAYLAND_DISPLAY:-}" ];then
  export XDG_SESSION_TYPE=wayland
  exec /usr/local/bin/niri --session
fi
EOF
chown "$user:$user" "$home/.profile"
systemctl daemon-reload
echo 'Session installed; check render node and Noctalia data path before reboot.'
