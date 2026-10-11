"""Exercise profile service transitions with isolated fake systemd/proc/sysfs.

Run on Linux with Python 3. No real service or display is changed.
"""
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'performance/profile-installed-prototype.sh'
MOCK = r'''#!/bin/sh
set -eu
name=$(basename "$0")
case "$name" in
id) echo 0;;
uname) echo "${TEST_KERNEL:-6.12.111-moze.1-native}";;
runuser) shift 3; exec "$@";;
sleep)
    if test "${TEST_FAIL:-}" = signal && test "$1" = 7; then kill -TERM "$PPID"; fi
    ;;
systemctl)
    shift
    echo "$*" >> "$TEST_ROOT/service-calls"
    case "$1" in
    is-active|daemon-reload) ;;
    restart)
        if test -e "$TEST_OVERRIDE"; then
            test "${TEST_FAIL:-}" != restart || exit 1
            entry=$(sed -n 's/^ExecStart=\(.*\) --session$/\1/p' "$TEST_OVERRIDE")
            "$entry" --session
        fi
        ;;
    show) echo 4242;;
    show-environment)
        echo WAYLAND_DISPLAY=wayland-7
        if test "${TEST_FAIL:-}" = stale; then pid=111; else pid=4242; fi
        echo "NIRI_SOCKET=$TEST_RUNTIME/niri.wayland-7.$pid.sock"
        ;;
    *) exit 2;;
    esac
    ;;
journalctl)
    echo 'KMS explicit fence capability driver=tegra supports_fencing=true legacy=false'
    echo 'MOCHA_FRAME elements_ms=0.1 render_ms=0.2 wait_ms=0.0 queue_ms=0.1 total_ms=0.4 needs_sync=false elements=3'
    ;;
esac
'''
BINARY = r'''#!/bin/sh
# MOCHA_FRAME / KMS explicit fence capability
if test "${1:-}" = --config; then
    printf '%s\n' "$0" > "$TEST_ROOT/compositor-executable"
    printf '%s\n' "$LD_LIBRARY_PATH" "$LIBGL_DRIVERS_PATH" "$GBM_BACKENDS_PATH" "${MOCHA_NATIVE_FENCE:-unset}" > "$TEST_ROOT/compositor-env"
    printf '%s\n' "$@" > "$TEST_ROOT/compositor-args"
fi
'''
BENCH = r'''#!/bin/sh
printf '%s\n' "$LD_LIBRARY_PATH" "$LIBGL_DRIVERS_PATH" "$GBM_BACKENDS_PATH" "${MOCHA_NATIVE_FENCE:-unset}" > "$TEST_ROOT/benchmark-env"
test "$WAYLAND_DISPLAY" = wayland-7
test "${TEST_FAIL:-}" != benchmark || exit 1
if test "${TEST_FAIL:-}" = incomplete; then echo 'GPU=fixture'; exit 0; fi
if test "${TEST_FAIL:-}" = short; then echo 'NATIVE_COLOR_FRAMES=120 WARMUP=120 SECONDS=2'; exit 0; fi
echo "NATIVE_COLOR_FRAMES=$MOCHA_BENCH_FRAMES WARMUP=120 SECONDS=10 FPS=60 P50_MS=16.6 P95_MS=17 P99_MS=18 OVER_25MS=0"
'''


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


@unittest.skipUnless(os.name == 'posix', 'Linux shell and Unix sockets required')
class InstalledProfileTest(unittest.TestCase):
    def run_case(self, mode='native-sync', fail='', old_override=False, kernel=None):
        with tempfile.TemporaryDirectory(prefix='mocha-profile-test-') as directory:
            root = Path(directory)
            runtime = root / 'run'
            unitdir = runtime / 'systemd/user/niri.service.d'
            unitdir.mkdir(parents=True)
            override = unitdir / 'zzzz-frame-profile.conf'
            if old_override:
                override.write_text('existing override\n')
            (root / 'results').mkdir()
            proc = root / 'proc'
            (proc / '4242').mkdir(parents=True)
            (proc / 'cmdline').write_text('mocha_native_performance=1\n')
            drm = root / 'drm/card0-DSI-1'
            drm.mkdir(parents=True)
            (drm / 'enabled').write_text('enabled\n')
            (drm / 'status').write_text('connected\n')
            candidate = root / "candidate with ' quote"
            lib = candidate / 'mesa/lib/arm-linux-gnueabihf'
            dri = candidate / 'mesa/dri'
            sync = root / "sync with ' quote"
            for folder in (lib, dri, sync / 'lib/arm-linux-gnueabihf', sync / 'dri'):
                folder.mkdir(parents=True)
                (folder / ('tegra_dri.so' if folder.name == 'dri' else 'libgallium-25.0.7.so')).write_text('fixture')
            (candidate / 'niri.kdl').write_text('fixture')
            executable(candidate / 'noctalia', '#!/bin/sh\nexit 0\n')
            binary = root / "niri with ' quote"
            executable(binary, BINARY)
            bench = root / 'benchmark'
            executable(bench, BENCH)
            (proc / '4242/exe').symlink_to(binary)
            mapped = (sync / 'lib/arm-linux-gnueabihf' if mode == 'native-sync' else lib)
            (proc / '4242/maps').write_text(str(mapped / 'libgallium-25.0.7.so') + '\n')
            mocks = root / 'bin'
            mocks.mkdir()
            for name in ('id', 'uname', 'runuser', 'sleep', 'systemctl', 'journalctl'):
                executable(mocks / name, MOCK)
            # Relocate only platform paths; do not bypass production checks.
            script = SOURCE.read_text().replace('/tmp/mocha-profile-', str(root / 'results/mocha-profile-'))
            script = script.replace('/run/user/1000', str(runtime))
            script = script.replace('/run/lock/mocha-niri-profile.lock', str(root / 'profile.lock'))
            script = script.replace('/sys/class/drm', str(root / 'drm'))
            script = script.replace('/proc/', str(proc) + '/')
            runner = root / 'profile.sh'
            runner.write_text(script)
            env = {**os.environ, 'PATH': str(mocks) + ':' + os.environ['PATH'],
                   'TEST_ROOT': str(root), 'TEST_RUNTIME': str(runtime),
                   'TEST_OVERRIDE': str(override), 'TEST_FAIL': fail,
                   'MOCHA_CANDIDATE': str(candidate), 'MOCHA_PROFILE_NIRI': str(binary),
                   'MOCHA_NATIVE_SYNC_STAGE': str(sync), 'MOCHA_PROFILE_BENCH': str(bench),
                   'MOCHA_PROFILE_BENCH_FRAMES': '600', 'MOCHA_NATIVE_FENCE': 'stale-inherited-value'}
            if kernel:
                env['TEST_KERNEL'] = kernel
            sockets = []
            try:
                for name in ('wayland-7', 'niri.wayland-7.4242.sock'):
                    sock = socket.socket(socket.AF_UNIX)
                    sock.bind(str(runtime / name))
                    sockets.append(sock)
                result = subprocess.run(['sh', str(runner), mode], env=env, capture_output=True, text=True, timeout=15)
            finally:
                for sock in sockets:
                    sock.close()
            calls = (root / 'service-calls').read_text() if (root / 'service-calls').exists() else ''
            if kernel or old_override:
                self.assertNotIn('restart', calls)
                if old_override:
                    self.assertEqual(override.read_text(), 'existing override\n')
                self.assertNotEqual(result.returncode, 0)
                return
            self.assertFalse(override.exists(), result.stderr)
            self.assertEqual(calls.count('restart niri.service'), 2, result.stdout + result.stderr)
            self.assertIn('RESTORED_NORMAL_DESKTOP', result.stdout)
            self.assertFalse(list(runtime.glob('mocha-profile.*')))
            if fail:
                self.assertNotEqual(result.returncode, 0)
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(Path((root / 'compositor-executable').read_text().strip()).name, 'niri')
                self.assertEqual((root / 'compositor-env').read_text(), (root / 'benchmark-env').read_text())
                expected_fence = '1' if mode == 'native-sync' else 'unset'
                self.assertEqual((root / 'benchmark-env').read_text().splitlines()[-1], expected_fence)
                self.assertIn(str(candidate / 'niri.kdl'), (root / 'compositor-args').read_text().splitlines())
                evidence = list((root / 'results').glob('*/niri-maps.txt'))
                self.assertEqual(len(evidence), 1)

    def test_native_sync_shares_quoted_environment(self):
        self.run_case()

    def test_baseline_clears_inherited_native_fence(self):
        self.run_case(mode='baseline')

    def test_refuse_fallback_before_service_changes(self):
        self.run_case(kernel='6.12.111-mocha-experimental-fbdiag')

    def test_preserve_preexisting_override(self):
        self.run_case(old_override=True)

    def test_restore_on_failed_restart(self):
        self.run_case(fail='restart')

    def test_restore_on_benchmark_failure(self):
        self.run_case(fail='benchmark')

    def test_refuse_success_without_complete_benchmark(self):
        self.run_case(fail='incomplete')

    def test_refuse_wrong_benchmark_frame_count(self):
        self.run_case(fail='short')

    def test_refuse_stale_socket_and_restore(self):
        self.run_case(fail='stale')

    def test_restore_on_signal(self):
        self.run_case(fail='signal')


if __name__ == '__main__':
    unittest.main()
