#!/bin/sh
set -eu
mode=${1:-baseline}
case "$mode" in baseline|native-sync) ;; *) exit 2;; esac
candidate=${MOCHA_CANDIDATE:-/srv/mocha-data/codex-debian-desktop/native-performance-20261011}
profile_binary=${MOCHA_PROFILE_NIRI:-/tmp/niri-frame-profile}
sync_stage=${MOCHA_NATIVE_SYNC_STAGE:-/tmp/native-sync-stage}
bench_binary=${MOCHA_PROFILE_BENCH:-/tmp/native-frame-timing}
frames=${MOCHA_PROFILE_BENCH_FRAMES:-0}
log_frames=${MOCHA_PROFILE_FRAMES:-1}
fail() { echo "$*" >&2; exit 1; }
case "$log_frames" in 0|1) ;; *) fail 'MOCHA_PROFILE_FRAMES must be 0 or 1';; esac
test "$(id -u)" = 0 || fail 'root required'
case "$frames" in ''|*[!0-9]*) fail 'invalid benchmark frame count';; esac
test "$frames" -eq 0 || { test "$frames" -ge 120 && test "$frames" -le 36000; } || fail 'benchmark frames must be 0 or 120..36000'
# Refuse the fallback simpledrm system before changing service configuration.
case "$(uname -r)" in *-native) ;; *) fail 'temporary native kernel required';; esac
grep -qw 'mocha_native_performance=1' /proc/cmdline || fail 'temporary native performance boot required'
enabled=false
for output in /sys/class/drm/card*-DSI-*; do
    if test -r "$output/enabled" && test "$(cat "$output/enabled")" = enabled && test "$(cat "$output/status")" = connected; then enabled=true; fi
done
test "$enabled" = true || fail 'connected and enabled native DSI required'
profile_binary=$(realpath "$profile_binary")
candidate=$(realpath "$candidate")
test -x "$profile_binary" && test -r "$candidate/niri.kdl" && test -x "$candidate/noctalia" || fail 'candidate binary/configuration missing'
grep -aq 'MOCHA_FRAME' "$profile_binary" && grep -aq 'KMS explicit fence capability' "$profile_binary" || fail 'profile/fencing build markers missing'
lib="$candidate/mesa/lib/arm-linux-gnueabihf"
dri="$candidate/mesa/dri"
native_fence=0
if test "$mode" = native-sync; then
    sync_stage=$(realpath "$sync_stage")
    lib="$sync_stage/lib/arm-linux-gnueabihf:$lib"
    dri="$sync_stage/dri"
    native_fence=1
fi
primary_lib=${lib%%:*}
test -r "$primary_lib/libgallium-25.0.7.so" && test -r "$dri/tegra_dri.so" || fail 'candidate Mesa missing'
test "$frames" -eq 0 || test -x "$bench_binary" || fail 'benchmark binary missing'
unitdir=/run/user/1000/systemd/user/niri.service.d
override="$unitdir/zzzz-frame-profile.conf"
userctl() {
    runuser -u mocha -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user "$@"
}
userctl is-active --quiet niri.service || fail 'normal desktop must be active before profiling'
exec 9>/run/lock/mocha-niri-profile.lock
flock -n 9 || fail 'another profile is running'
test ! -e "$override" && test ! -L "$override" || fail 'profile override already exists'
work=$(mktemp -d /run/user/1000/mocha-profile.XXXXXX)
result=$(mktemp -d "/tmp/mocha-profile-$mode.XXXXXX")
installed=false
start=
restore() {
    status=$?
    trap - EXIT HUP INT TERM
    set +e
    if test -n "$start"; then journalctl _UID=1000 _SYSTEMD_USER_UNIT=niri.service --since="$start" -o cat --no-pager > "$result/journal.log"; fi
    if test "$override" -ef "$work/service.conf"; then
        rm -f "$override"
        userctl daemon-reload && userctl restart niri.service && userctl is-active --quiet niri.service
        if test "$?" -ne 0; then
            echo 'desktop restoration failed; inspect niri.service' >&2
            status=1
        else echo RESTORED_NORMAL_DESKTOP; fi
    elif test "$installed" = true; then
        echo 'profile override changed externally; original configuration was not overwritten' >&2
        status=1
    fi
    rm -rf "$work"
    echo "PROFILE_RESULTS=$result"
    exit "$status"
}
trap restore EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
chmod 755 "$work"
# Keep the real compositor name for the installed GPU policy's pidof check.
# /proc/PID/exe still resolves to the verified candidate binary.
ln -s "$profile_binary" "$work/niri"
# One quoted environment file is shared by compositor and benchmark.
quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
assignment() { printf 'export %s=' "$1"; quote "$2"; printf '\n'; }
{
    echo 'unset SMITHAY_USE_LEGACY MOCHA_NATIVE_FENCE'
    assignment LD_LIBRARY_PATH "$lib"
    assignment LIBGL_DRIVERS_PATH "$dri"
    assignment GBM_BACKENDS_PATH "$primary_lib/gbm"
    echo 'export MESA_LOADER_DRIVER_OVERRIDE=tegra MESA_DRI_DRIVER_OVERRIDE=tegra'
    test "$native_fence" = 0 || echo 'export MOCHA_NATIVE_FENCE=1'
} > "$work/library-env"
{
    echo '#!/bin/sh'
    echo 'set -eu'
    printf '. '; quote "$work/library-env"; printf '\n'
    if test "$log_frames" = 1; then echo 'export MOCHA_FRAME_PROFILE=1'; else echo 'unset MOCHA_FRAME_PROFILE'; fi
    echo 'export RUST_LOG=info,smithay::backend::drm::compositor=debug'
    printf 'exec '; quote "$work/niri"; printf ' --config '; quote "$candidate/niri.kdl"; printf ' "$@"\n'
} > "$work/niri-entry"
sh -n "$work/library-env"
sh -n "$work/niri-entry"
chmod 755 "$work/niri-entry"
runuser -u mocha -- test -x "$profile_binary" || fail 'profile binary is not executable by mocha'
sha256sum "$profile_binary" "$primary_lib/libgallium-25.0.7.so" "$dri/tegra_dri.so" > "$result/SHA256SUMS"
cp "$work/library-env" "$result/library-env"
uname -r > "$result/kernel.txt"
mkdir -p "$unitdir"
printf '[Service]\nExecStart=\nExecStart=%s --session\n' "$work/niri-entry" > "$work/service.conf"
ln "$work/service.conf" "$override"
installed=true
start=$(date --iso-8601=seconds)
userctl daemon-reload
userctl restart niri.service
sleep 7
p=$(userctl show niri.service --property=MainPID --value)
case "$p" in ''|0|*[!0-9]*) fail 'profile service has no MainPID';; esac
test "$(readlink -f "/proc/$p/exe")" = "$profile_binary" || fail 'service is not running the requested binary'
cp "/proc/$p/maps" "$result/niri-maps.txt"
grep -F "$primary_lib/libgallium-25.0.7.so" "$result/niri-maps.txt" >/dev/null || fail 'candidate Gallium is not mapped'
session=$(userctl show-environment)
wayland=$(printf '%s\n' "$session" | sed -n 's/^WAYLAND_DISPLAY=//p')
socket=$(printf '%s\n' "$session" | sed -n 's/^NIRI_SOCKET=//p')
case "$wayland" in wayland-*[!0-9]*|'') fail 'invalid Wayland display';; wayland-*) ;; *) fail 'invalid Wayland display';; esac
case "$socket" in /run/user/1000/niri."$wayland"."$p".sock) ;; *) fail 'stale or unexpected Niri socket';; esac
test -S "/run/user/1000/$wayland" && test -S "$socket" || fail 'session sockets missing'
printf 'MainPID=%s\nWAYLAND_DISPLAY=%s\nNIRI_SOCKET=%s\n' "$p" "$wayland" "$socket" > "$result/session.txt"
runuser -u mocha -- env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY="$wayland" NIRI_SOCKET="$socket" DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
    sh -c 'set -eu; for i in 1 2 3 4 5 6; do "$1" msg panel-toggle control-center; sleep 1; "$1" msg panel-toggle control-center; "$2" msg action toggle-overview; sleep 1; "$2" msg action toggle-overview; sleep 1; done' sh "$candidate/noctalia" "$profile_binary"
if test "$frames" -gt 0; then
    runuser -u mocha -- env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY="$wayland" MOCHA_BENCH_FRAMES="$frames" \
        sh -c 'set -eu; . "$1"; exec timeout 75s "$2"' sh "$work/library-env" "$bench_binary" > "$result/benchmark.log"
    test "$(grep -c "^NATIVE_COLOR_FRAMES=$frames WARMUP=120 " "$result/benchmark.log" || true)" = 1 || fail 'benchmark did not report the requested complete frame count'
    cat "$result/benchmark.log"
fi
journalctl _UID=1000 _SYSTEMD_USER_UNIT=niri.service --since="$start" -o cat --no-pager > "$result/journal.log"
grep 'KMS explicit fence capability' "$result/journal.log" > "$result/capability.log" || fail 'no fencing capability evidence'
cat "$result/capability.log"
if test "$log_frames" = 1; then
    grep 'MOCHA_FRAME ' "$result/journal.log" > "$result/profile-$mode.log" || fail 'no frame profile evidence'
    wc -l "$result/profile-$mode.log"
    tail -n 4 "$result/profile-$mode.log"
else
    echo FRAME_PROFILE_DISABLED
fi
