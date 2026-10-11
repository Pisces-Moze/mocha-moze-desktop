#!/bin/sh
set -eu
mode=${1:-baseline}
case "$mode" in baseline|native-sync) ;; *) exit 2;; esac
candidate=${MOCHA_CANDIDATE:-/srv/mocha-data/codex-debian-desktop/native-performance-20261011}
profile_binary=${MOCHA_PROFILE_NIRI:-/tmp/niri-frame-profile}
test "$(id -u)" = 0
# Existing prototype layout only; see the handoff before running.
unitdir=/run/user/1000/systemd/user/niri.service.d
userctl() {
    runuser -u mocha -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user "$@"
}
restore() {
    rm -f "$unitdir/zzzz-frame-profile.conf"
    userctl daemon-reload
    userctl restart niri.service
}
trap restore EXIT
mkdir -p "$unitdir"
cat > /tmp/profile-niri-entry <<EOF
#!/bin/sh
set -eu
unset SMITHAY_USE_LEGACY
export MOCHA_FRAME_PROFILE=1
export RUST_LOG=info,smithay::backend::drm::compositor=debug
export MESA_LOADER_DRIVER_OVERRIDE=tegra MESA_DRI_DRIVER_OVERRIDE=tegra
export LD_LIBRARY_PATH=$candidate/mesa/lib/arm-linux-gnueabihf
export LIBGL_DRIVERS_PATH=$candidate/mesa/dri
export GBM_BACKENDS_PATH=$candidate/mesa/lib/arm-linux-gnueabihf/gbm
exec $profile_binary --config $candidate/niri.kdl "\$@"
EOF
if [ "$mode" = native-sync ]; then
    sed -i "s|export LD_LIBRARY_PATH=.*|export LD_LIBRARY_PATH=/tmp/native-sync-stage/lib/arm-linux-gnueabihf:$candidate/mesa/lib/arm-linux-gnueabihf|; s|export LIBGL_DRIVERS_PATH=.*|export LIBGL_DRIVERS_PATH=/tmp/native-sync-stage/dri|" /tmp/profile-niri-entry
    sed -i '/^exec /i export MOCHA_NATIVE_FENCE=1' /tmp/profile-niri-entry
fi
sh -n /tmp/profile-niri-entry
chmod 755 /tmp/profile-niri-entry "$profile_binary"
cat > "$unitdir/zzzz-frame-profile.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=/tmp/profile-niri-entry --session
EOF
start=$(date --iso-8601=seconds)
userctl daemon-reload
userctl restart niri.service
sleep 7
p=$(pidof "$(basename "$profile_binary")")
test -n "$p"
socket=$(find /run/user/1000 -maxdepth 1 -name 'niri.wayland-*.sock' | head -n 1)
test -n "$socket"
cat > /tmp/exercise-internal-ui.sh <<EOF
set -eu
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 NIRI_SOCKET=$socket
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
for i in 1 2 3 4 5 6; do
    $candidate/noctalia msg panel-toggle control-center
    sleep 1
    $candidate/noctalia msg panel-toggle control-center
    $profile_binary msg action toggle-overview
    sleep 1
    $profile_binary msg action toggle-overview
    sleep 1
done
EOF
runuser -u mocha -- sh /tmp/exercise-internal-ui.sh
if [ "${MOCHA_PROFILE_BENCH_FRAMES:-0}" -gt 0 ]; then
    runuser -u mocha -- env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 \
        MESA_LOADER_DRIVER_OVERRIDE=tegra MESA_DRI_DRIVER_OVERRIDE=tegra \
        LD_LIBRARY_PATH="$candidate/mesa/lib/arm-linux-gnueabihf" \
        LIBGL_DRIVERS_PATH="$candidate/mesa/dri" \
        GBM_BACKENDS_PATH="$candidate/mesa/lib/arm-linux-gnueabihf/gbm" \
        MOCHA_BENCH_FRAMES="$MOCHA_PROFILE_BENCH_FRAMES" \
        timeout 75s /tmp/native-frame-timing
fi
journalctl _UID=1000 _SYSTEMD_USER_UNIT=niri.service --since="$start" -o cat --no-pager | grep 'KMS explicit fence capability' || true
journalctl _UID=1000 _SYSTEMD_USER_UNIT=niri.service --since="$start" -o cat --no-pager | grep 'MOCHA_FRAME ' > "/tmp/profile-$mode.log"
wc -l "/tmp/profile-$mode.log"
tail -n 4 "/tmp/profile-$mode.log"
restore
trap - EXIT
echo RESTORED_NORMAL_DESKTOP
