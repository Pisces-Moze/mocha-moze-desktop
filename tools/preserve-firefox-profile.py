#!/usr/bin/python3
"""Keep a user's existing default when a matched Firefox runtime moves.

Firefox itself discovers the new installation ID in an empty temporary HOME.
Only profiles.ini/installs.ini metadata changes; never copy/delete profile data.
"""
import argparse
import configparser
import hashlib
import io
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import subprocess
import tempfile
import time


def parse(path):
    document=configparser.ConfigParser(interpolation=None)
    document.optionxform=str
    if path.exists():document.read(path,encoding='utf-8')
    return document


def choose_existing(profiles,installs):
    defaults={installs[s]['Default'] for s in installs.sections() if installs[s].get('Default')}
    defaults.update(profiles[s]['Default'] for s in profiles.sections()
                    if s.startswith('Install') and profiles[s].get('Default'))
    if len(defaults)==1:return defaults.pop()
    # Multiple dedicated profiles need the user's choice, not a heuristic.
    if len(defaults)>1:raise ValueError('Multiple installation defaults; choose a profile before migrating')
    defaults=[profiles[s].get('Path') for s in profiles.sections()
              if s.startswith('Profile') and profiles[s].get('Default')=='1']
    if len(defaults)==1 and defaults[0]:return defaults[0]
    raise ValueError('No unambiguous existing default profile')


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def discover(runtime,user):
    with tempfile.TemporaryDirectory(prefix='mocha-firefox-install-id-',dir='/tmp') as directory:
        home=Path(directory);os.chown(home,user.pw_uid,user.pw_gid)
        env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),
                 XDG_CACHE_HOME=str(home/'.cache'),XDG_DATA_HOME=str(home/'.local/share'),
                 MOZ_CRASHREPORTER_NO_REPORT='1',
                 LD_LIBRARY_PATH=str(runtime)+':'+str(runtime/'codecs'))
        for key in ('MOZ_LEGACY_PROFILES','MOZ_PROFILE_PATH'):env.pop(key,None)
        with (home/'startup.log').open('w') as log:
            process=subprocess.Popen(['runuser','-u',user.pw_name,'--','env',
                'HOME='+str(home),'XDG_CONFIG_HOME='+str(home/'.config'),
                'XDG_CACHE_HOME='+str(home/'.cache'),'XDG_DATA_HOME='+str(home/'.local/share'),
                str(runtime/'firefox-esr'),'--headless','--no-remote','about:blank'],
                env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    for relative in ('.config/mozilla/firefox','.mozilla/firefox'):
                        document=parse(home/relative/'installs.ini')
                        ids=document.sections()
                        if len(ids)==1 and re.fullmatch('[0-9A-F]{8,32}',ids[0]):return ids[0],relative
                    if process.poll() is not None:break
                    time.sleep(.2)
                raise RuntimeError('Temporary Firefox did not produce an installation ID')
            finally:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()


def write(path,document,user):
    stream=io.StringIO();document.write(stream)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        os.fchmod(fd,0o600);os.fchown(fd,user.pw_uid,user.pw_gid)
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            output.write(stream.getvalue());output.flush();os.fsync(output.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True)
    args=p.parse_args()
    if os.geteuid()!=0:p.error('root required')
    runtime=args.runtime.resolve(strict=True)
    assert (runtime/'mocha-request-runtime.json').is_file()
    assert subprocess.run(['pgrep','-x','firefox-esr'],stdout=subprocess.DEVNULL).returncode==1,'Close Firefox first'
    user=pwd.getpwuid(1000);home=Path(user.pw_dir).resolve()
    candidates=[home/relative for relative in ('.config/mozilla/firefox','.mozilla/firefox')
                if (home/relative/'profiles.ini').exists()]
    if not candidates:
        print('No default-profile metadata; no mapping changed');return
    if len(candidates)!=1:raise ValueError('Multiple profile roots require review; no mapping changed')
    base=candidates[0]
    assert base.resolve().is_relative_to(home)
    paths=[base/'profiles.ini',base/'installs.ini']
    assert not any(path.is_symlink() for path in paths)
    hashes={path:fingerprint(path) for path in paths}
    profiles,installs=map(parse,paths)
    selected=choose_existing(profiles,installs)
    actual=(base/selected).resolve()
    assert actual.is_dir() and actual.is_relative_to(home)
    installation,relative=discover(runtime,user)
    if base!=home/relative:raise ValueError('Profile root migration requires review; no mapping changed')
    for document,section in ((profiles,'Install'+installation),(installs,installation)):
        if section in document and document[section].get('Default')!=selected:
            raise ValueError('New runtime already has a different selected profile; not replacing it')
        if section not in document:document.add_section(section)
        document[section]['Default']=selected;document[section]['Locked']='1'
    assert all(fingerprint(path)==hashes[path] for path in paths),'Profile metadata changed during discovery'
    assert subprocess.run(['pgrep','-x','firefox-esr'],stdout=subprocess.DEVNULL).returncode==1
    backup=Path('/var/backups/mocha-firefox')/('profile-mapping-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True,mode=0o700)
    for path in paths:
        if path.exists():shutil.copy2(path,backup/path.name)
    try:
        write(paths[0],profiles,user);write(paths[1],installs,user)
        descriptor=os.open(base,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        assert parse(paths[0])['Install'+installation]['Default']==selected
        assert parse(paths[1])[installation]['Default']==selected
    except BaseException:
        for path in paths:
            if (backup/path.name).exists():shutil.copy2(backup/path.name,path)
            else:path.unlink(missing_ok=True)
        raise
    print('EXISTING_DEFAULT_PROFILE_PRESERVED; installation mappings verified; profile data untouched')
    print('METADATA_BACKUP',backup)


if __name__=='__main__':main()
