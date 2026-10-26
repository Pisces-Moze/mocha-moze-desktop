#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install the Mocha adapter around existing systemd/earlyoom/zram components."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import time

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user',default='mocha')
    parser.add_argument('--app2unit-root',required=True,type=Path)
    parser.add_argument('--addon',required=True,type=Path)
    parser.add_argument('--extra-zram',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Run as root')
    account=pwd.getpwnam(args.user);home=Path(account.pw_dir);repo=Path(__file__).resolve().parents[1]
    lock=json.loads((repo/'config/memory-components.json').read_text())
    script=(args.app2unit_root/'app2unit').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(script).hexdigest()!=lock['app2unit']['script_sha256_lf']:parser.error('Unexpected App2Unit source')
    addon=args.addon.read_bytes()
    if hashlib.sha256(addon).hexdigest()!=lock['auto_tab_discard']['sha256']:parser.error('Unexpected signed XPI')
    for executable in ['earlyoom','pactl','systemd-run','wl-paste']:
        if not shutil.which(executable):parser.error('Install Debian dependencies first: '+executable)
    if not Path('/sys/fs/cgroup/cgroup.controllers').exists():parser.error('cgroup v2 required')
    backup=Path('/var/backups/mocha-memory')/time.strftime('%Y%m%d-%H%M%S');backup.mkdir(parents=True,mode=0o700)
    def write(path,data,mode=0o644,user=False):
        path=Path(path)
        if path.exists():
            old=backup/str(path).lstrip('/');old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,old)
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name(path.name+'.memory-new');temp.write_bytes(data);temp.chmod(mode)
        if user:os.chown(temp,account.pw_uid,account.pw_gid)
        temp.replace(path)
    for source,target,mode,user in [
        ('tablet/mocha-app-freezer.py','/usr/local/libexec/mocha-app-freezer.py',0o755,False),
        ('tablet/mocha-memory','/usr/local/bin/mocha-memory',0o755,False),
        ('tablet/mocha-app-freezer.service',str(home/'.config/systemd/user/mocha-app-freezer.service'),0o644,True),
        ('config/firefox-mocha-memory-freezer.js','/etc/firefox-esr/mocha-memory-freezer.js',0o644,False)]:
        write(target,(repo/source).read_bytes().replace(b'\r\n',b'\n'),mode,user)
    user_config=home/'.config/mocha/memory.json'
    if not user_config.exists():write(user_config,(repo/'config/mocha-memory.json').read_bytes(),user=True)
    write('/usr/local/bin/app2unit',script,0o755)
    write('/usr/local/share/doc/app2unit/LICENSE',(args.app2unit_root/'LICENSE').read_bytes())
    addon_path=Path('/usr/local/share/mocha-memory/auto-tab-discard.xpi');write(addon_path,addon)
    pref=Path('/usr/lib/firefox-esr/defaults/pref/mocha-memory-freezer.js')
    if not pref.exists():pref.symlink_to('/etc/firefox-esr/mocha-memory-freezer.js')
    policy=Path('/etc/firefox/policies/policies.json')
    document=json.loads(policy.read_text()) if policy.exists() else {'policies':{}}
    policies=document.setdefault('policies',{});addon_id=lock['auto_tab_discard']['id']
    policies.setdefault('ExtensionSettings',{})[addon_id]={'installation_mode':'normal_installed','install_url':addon_path.as_uri()}
    policies.setdefault('3rdparty',{}).setdefault('Extensions',{})[addon_id]=json.loads((repo/'config/auto-tab-discard-settings.json').read_text())
    write(policy,(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode())
    shell=home/'.config/noctalia/noctalia-config.toml'
    if shell.exists():
        text=shell.read_text()
        for key,value in [('launch_apps_as_systemd_services','true'),('launch_apps_custom_command','""')]:
            if re.search(r'(?m)^'+key+r'\s*=',text):text=re.sub(r'(?m)^'+key+r'\s*=.*$',key+' = '+value,text)
            elif '[shell]' in text:text=text.replace('[shell]','[shell]\n'+key+' = '+value,1)
            else:text+='\n[shell]\n'+key+' = '+value+'\n'
        write(shell,text.encode(),user=True)
    early="-M 196608,98304 -s 15,5 -r 300 --ignore-root-user --ignore '^(niri|noctalia|fcitx5|pipewire.*|wireplumber|dbus.*|systemd.*|mocha-.*|xdg-.*|gpg-agent|ssh-agent)$'"
    write('/etc/default/earlyoom',('EARLYOOM_ARGS="'+early+'"\n').encode())
    subprocess.run(['systemctl','enable','--now','earlyoom.service'],check=True)
    subprocess.run(['systemctl','restart','earlyoom.service'],check=True)
    if args.extra_zram:
        zram=Path('/etc/systemd/zram-generator.conf')
        if not zram.exists():write(zram,(repo/'config/mocha-zram-generator.conf').read_bytes())
        elif '[zram1]' not in zram.read_text():parser.error('Existing zram configuration preserved; merge manually')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','start','dev-zram1.swap'],check=True)
    env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{account.pw_uid}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{account.pw_uid}/bus')
    for command in [['daemon-reload'],['enable','--now','mocha-app-freezer.service'],['restart','mocha-app-freezer.service']]:
        subprocess.run(['runuser','-u',args.user,'--','systemctl','--user']+command,env=env,cwd=home,check=True)
    print('Installed; backup:',backup)
    print('Restart Firefox normally to activate tab policies. No automatic browser restart.')

if __name__=='__main__':main()
