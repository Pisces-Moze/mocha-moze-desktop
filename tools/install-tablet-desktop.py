#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Activate a checked ARM bundle on the installed data volume, with rollback files.

Bundle: niri, noctalia, mesa/, wallpaper.webp, SHA256SUMS. No boot flashing.
Run after install-tablet-input.sh; restart is explicit through --activate.
"""
import argparse, hashlib, json, os, pathlib, pwd, shutil, subprocess, time

parser = argparse.ArgumentParser()
parser.add_argument('bundle', type=pathlib.Path)
parser.add_argument('--activate', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0, 'Run as root on the prototype'
assert subprocess.check_output(['dpkg','--print-architecture'], text=True).strip() == 'armhf'
repo = pathlib.Path(__file__).resolve().parents[1]
bundle = args.bundle.resolve()
assert str(bundle).startswith('/srv/mocha-data/'), 'Stage on data volume'
assert not bundle.is_symlink()
assets = pathlib.Path('/srv/mocha-data/codex-debian-desktop/local/share/noctalia/assets')
assert all((assets/name).is_file() for name in ('emoji.json','fonts/noctalia-tabler.ttf','templates/builtin.toml','translations/en.json')), 'Noctalia asset bundle is incomplete'
for line in (bundle/'SHA256SUMS').read_text().splitlines():
    digest, name = line.split(maxsplit=1)
    target = (bundle/name.lstrip('*')).resolve()
    assert target.is_relative_to(bundle), 'Hash path escapes bundle'
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, name
for name in ('niri','noctalia'):
    binary = bundle/name
    assert binary.is_file() and os.access(binary, os.X_OK)
    data = binary.read_bytes()[:20]
    assert data[:4] == b'\x7fELF' and int.from_bytes(data[18:20],'little') == 40
    result = subprocess.run(['ldd',str(binary)], capture_output=True, text=True)
    assert result.returncode == 0 and 'not found' not in result.stdout+result.stderr, result.stdout
subprocess.run([str(bundle/'niri'),'validate','--config',str(repo/'tablet/niri.kdl')],check=True)
subprocess.run([str(bundle/'noctalia'),'config','validate',str(repo/'tablet/noctalia.toml')],check=True)
account = pwd.getpwnam('mocha')
home = pathlib.Path(account.pw_dir)
runtime = f'/run/user/{account.pw_uid}'
def userctl(*argv):
    return subprocess.run(['runuser','-u','mocha','--','env',f'XDG_RUNTIME_DIR={runtime}',f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus','systemctl','--user',*argv],check=True)
if args.activate:
    user_env=['runuser','-u','mocha','--','env',f'HOME={home}',
              f'XDG_RUNTIME_DIR={runtime}',f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus']
    active=subprocess.run([*user_env,'systemctl','--user','is-active','--quiet','niri.service'])
    if active.returncode==0:
        state=subprocess.run([*user_env,'/usr/local/libexec/mocha-session-exec',
                              '/usr/local/bin/noctalia','msg','status'],
                             capture_output=True,text=True,timeout=10)
        assert state.returncode==0, 'Cannot verify lock state; leave the running session unchanged'
        assert json.loads(state.stdout).get('locked') is False, 'Unlock normally before activating a new desktop'
backup = home/'.local/state/mocha-backups'/('desktop-'+time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
paths = ['.config/niri','.config/noctalia','.local/state/noctalia','.config/systemd/user/niri.service.d','.config/systemd/user/mocha-buttons.service']
for name in paths:
    source = home/name
    if source.exists():
        target = backup/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir(): shutil.copytree(source,target,symlinks=True)
        else: shutil.copy2(source,target)
current = pathlib.Path('/usr/local/libexec/mocha-tablet-current')
if current.is_symlink(): (backup/'previous-release.txt').write_text(os.readlink(current)+'\n')
if args.activate:
    for unit in ('mocha-buttons.service','mocha-keyboard.service','mocha-input-method.service','niri.service'):
        try: userctl('stop',unit)
        except subprocess.CalledProcessError:
            if unit == 'niri.service': raise
def write(path, data, mode=0o644, owner=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_name(path.name+'.new')
    temp.write_text(data,encoding='utf-8',newline='\n')
    temp.chmod(mode)
    if owner: os.chown(temp,account.pw_uid,account.pw_gid)
    temp.replace(path)
for name, target in [('niri-entry','/usr/local/bin/niri'),('noctalia-entry','/usr/local/bin/noctalia'),('mocha-native-app','/usr/local/libexec/mocha-native-app'),('mocha-buttons.py','/usr/local/libexec/mocha-buttons.py')]:
    write(pathlib.Path(target),(repo/'tablet'/name).read_text(),0o755)
write(home/'.config/niri/mocha-tablet.kdl',(repo/'tablet/niri.kdl').read_text(),owner=True)
legacy=(repo/'tablet/niri.kdl').read_text().replace('map-to-output "DSI-1"','map-to-output "Unknown-1"')
legacy=legacy.replace('    render-drm-device "/dev/dri/renderD128"\n','')
write(home/'.config/niri/mocha-tablet-legacy.kdl',legacy,owner=True)
write(home/'.config/niri/gestures.kdl',(repo/'tablet/gestures.kdl').read_text(),owner=True)
password_ready = subprocess.check_output(['passwd','-S','mocha'],text=True).split()[1] == 'P'
config = (repo/'tablet/noctalia.toml').read_text()
if not password_ready: config = config.replace('[lockscreen]\nenabled = true','[lockscreen]\nenabled = false')
config += '\n[wallpaper]\ndirectory = "'+str(home/'Pictures/Wallpapers')+'"\n'
write(home/'.config/noctalia/config.toml',config,owner=True)
# Move old generated overrides aside so they do not override the new theme.
state = home/'.local/state/noctalia/settings.toml'
if state.exists(): state.rename(backup/'settings-before-theme.toml')
wallpaper = home/'Pictures/Wallpapers/Nyxuri-lawson-fuji.webp'
wallpaper.parent.mkdir(parents=True,exist_ok=True)
os.chown(wallpaper.parent,account.pw_uid,account.pw_gid)
os.chown(wallpaper.parent.parent,account.pw_uid,account.pw_gid)
shutil.copy2(bundle/'wallpaper.webp',wallpaper)
os.chown(wallpaper,account.pw_uid,account.pw_gid)
write(home/'.config/systemd/user/niri.service.d/zzz-tablet.conf','[Service]\nExecStart=\nExecStart=/usr/local/bin/niri --session\n',owner=True)
write(home/'.config/systemd/user/mocha-buttons.service',(repo/'tablet/mocha-buttons.service').read_text(),owner=True)
if password_ready:
    # Keep logind from powering off during the gap before the user handler owns
    # gpio-keys. The handler implements release-to-lock and long-press menu.
    write(pathlib.Path('/etc/systemd/logind.conf.d/70-mocha-buttons.conf'),
          '[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress=ignore\n')
    subprocess.run(['systemctl','reload','systemd-logind.service'],check=True)
current.parent.mkdir(parents=True,exist_ok=True)
pending=current.with_name(current.name+'.new')
pending.unlink(missing_ok=True)
pending.symlink_to(bundle)
pending.replace(current)
userctl('daemon-reload')
if password_ready: userctl('enable','mocha-buttons.service')
else: userctl('disable','mocha-buttons.service')
if args.activate:
    userctl('start','niri.service')
    userctl('start','mocha-input-method.service')
    if password_ready: userctl('start','mocha-buttons.service')
print('Installed release:',bundle,'Backup:',backup,'Lock password ready:',password_ready)
