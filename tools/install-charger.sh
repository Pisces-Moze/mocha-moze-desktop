#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
test "$(uname -m)" = armv7l; test "$EUID" = 0
install -d /usr/local/libexec /etc/systemd/system /etc/systemd/system-generators
install -m755 "$repo/build/mocha-charger-ui" /usr/local/libexec/
for n in mocha-charge-detect.py mocha-charge-policy.py mocha-charger-session;do install -m755 "$repo/charging/$n" /usr/local/libexec/;done
install -m755 "$repo/charging/mocha-charger-generator" /etc/systemd/system-generators/
for n in mocha-charge-policy.service mocha-charger.service mocha-charger.target;do install -m644 "$repo/charging/$n" /etc/systemd/system/;done
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/mocha-charger.service /etc/systemd/system/mocha-charger.target
systemctl enable mocha-charge-policy.service
echo 'Installed. Automatic charger boot remains disabled until /boot/mocha-charger.enabled exists.'
