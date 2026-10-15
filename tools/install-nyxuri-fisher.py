#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install all three upstream Fish plugins from checked, offline archives.

This keeps the reviewed upstream lockfile and Fisher ownership bookkeeping.
No existing unmanaged Fisher installation is overwritten.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ARCHIVES = (
    ("fisher-pinned.tar.gz", "jorgebucaran/fisher", "791da644d33d392216f6b1a9b5fc1e470db6d7f2"),
    ("autopair-pinned.tar.gz", "jorgebucaran/autopair.fish", "4d1752ff5b39819ab58d7337c69220342e9de0e2"),
    ("fzf-fish-pinned.tar.gz", "PatrickF1/fzf.fish", "6a6136998879dcc1f29a405dfdd6b92c5f229c39"),
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--archives",type=Path,required=True)
    args=parser.parse_args()
    if os.geteuid()==0:
        parser.error("Run as the desktop user")
    sys.path.insert(0,str(args.source.resolve()))
    from nyxuri.modules import fisher
    directory=Path.home()/".config/fish"
    state=fisher._load_ownership()
    if state is None and (directory/"functions/fisher.fish").exists():
        parser.error("Existing unmanaged Fisher is preserved; migrate it explicitly")
    if state and state.get("fisher_preexisting"):
        parser.error("Existing Fisher predates Nyxuri ownership")
    if not fisher._locked_plugins():
        parser.error("fish_plugins differs from the reviewed upstream lockfile")
    with tempfile.TemporaryDirectory(prefix="nyxuri-fisher-") as temporary:
        stage=Path(temporary)
        plugins=[]
        for name, repo, commit in ARCHIVES:
            dest=stage/repo.split("/")[1]
            dest.mkdir()
            with tarfile.open(args.archives/name) as archive:
                if archive.pax_headers.get("comment")!=commit:
                    parser.error(f"Wrong source revision: {name}")
                archive.extractall(dest,filter="data")
            roots=list(dest.iterdir())
            if len(roots)!=1 or not roots[0].is_dir():
                parser.error(f"Invalid archive layout: {name}")
            plugins.append(roots[0])
        bootstrap=plugins[0]/"functions/fisher.fish"
        if hashlib.sha256(bootstrap.read_bytes()).hexdigest()!=fisher.FISHER_BOOTSTRAP_SHA256:
            parser.error("Fisher bootstrap checksum mismatch")
        before=fisher._managed_files(directory)
        state=state or {"complete":False,"files":[],"fisher_preexisting":False}
        temporary_config=stage/"isolated-config"
        temporary_config.mkdir()
        install_directory=stage/"installed-fish"
        install_directory.mkdir()
        result=subprocess.run(["fish","-c",
            "set --global fisher_path $argv[2]; source -- $argv[1]; fisher install $argv[3..-1]",
            "--",str(bootstrap),str(install_directory),*[str(p) for p in plugins]],
            env={**os.environ,"XDG_CONFIG_HOME":str(temporary_config)},cwd=Path.home(),stdin=subprocess.DEVNULL,timeout=30)
        # Fisher records the supplied local paths. Restore the canonical
        # lockfile so future updates remain pinned to the same commits.
        if result.returncode:
            return result.returncode
        for relative in fisher.MANAGED_FILES:
            installed=install_directory/relative
            if installed.is_file():
                target=directory/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(installed,target)
        (directory/"fish_plugins").write_text("\n".join(fisher.FISHER_PLUGINS)+"\n")
        fisher._record_new_files(state,before,directory)
        state["plugins"]=list(fisher.FISHER_PLUGINS)
        state["complete"]=True
        fisher._write_ownership(state)
        print("NYXURI_ALL_FISH_PLUGINS_INSTALLED")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
