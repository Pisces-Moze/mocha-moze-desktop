#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install the verified browser library environment with reversible backups."""
import os
from pathlib import Path
import re
import shutil
import time

def install():
    if os.geteuid()!=0:raise SystemExit('root required')
    backup=Path('/var/backups/mocha-firefox-launcher')/time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    source=Path(__file__).with_name('mocha-firefox')
    target=Path('/usr/local/bin/mocha-firefox')
    if target.exists():shutil.copy2(target,backup/'previous-launcher')
    shutil.copyfile(source,target);target.chmod(0o755)
    # Keep translations, actions and URL placeholders in existing desktop files.
    desktop_files=[Path('/usr/share/applications/firefox-esr.desktop')]
    home=Path('/srv/mocha-data/codex-debian-desktop/home/mocha')
    desktop_files+=list((home/'.local/share/applications').glob('*Firefox*.desktop'))
    for index,path in enumerate(desktop_files):
        if not path.is_file():continue
        text=path.read_text()
        revised=re.sub(r'(?m)^Exec=(?:/usr/lib/firefox-esr|/srv/mocha-data/codex-debian-desktop/firefox-esr)/firefox-esr(?=\s|$)',
                       'Exec=/usr/local/bin/mocha-firefox',text)
        if revised!=text:
            shutil.copy2(path,backup/f'{index}-{path.name}')
            path.write_text(revised)
    print('FIREFOX_LAUNCHER_INSTALLED',backup)

if __name__=='__main__':install()
