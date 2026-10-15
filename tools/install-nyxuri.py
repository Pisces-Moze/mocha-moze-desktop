#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Deploy the complete pinned Nyxuri checkout as the desktop user.

Package installation and privileged wrappers are deliberately separate. This
adapter uses Nyxuri's atomic deploy primitive and retains its custom-file rules.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

PIN = "ebafe03c9bdf1291eeb83d0f8c368d40a63ccdfd"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as the desktop user, with that user's HOME")
    source = args.source.resolve()
    for path in ("nyxuri/deploy/atomic.py", "configs/niri/config.kdl", "assets/fcitx5", "LICENSE"):
        if not (source / path).exists():
            parser.error(f"Incomplete Nyxuri source: {path}")
    marker = source / "MOCHA-UPSTREAM-COMMIT"
    if not marker.is_file() or marker.read_text().strip() != PIN:
        parser.error("Source was not verified against the pinned upstream archive")
    sys.path.insert(0, str(source))
    from nyxuri.deploy.atomic import atomic_replace_item
    from nyxuri.deploy.manifest import load_manifest

    home = Path.home()
    config = home / ".config"
    config.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nyxuri-stage-", dir=config) as temporary:
        stage = Path(temporary)
        shutil.copytree(source / "configs", stage / "configs", symlinks=True)
        content_dir = stage / "configs"
        for path in content_dir.rglob("*"):
            if path.is_file() and not path.is_symlink():
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeError:
                    continue
                path.write_text(text.replace("/home/user", str(home)), encoding="utf-8", newline="\n")
        niri = content_dir / "niri"
        main_config = (niri / "config.kdl").read_text()
        main_config = main_config.replace('    honor-xdg-activation-with-invalid-serial',
            '    honor-xdg-activation-with-invalid-serial\n    render-drm-device "/dev/dri/renderD128"')
        main_config = main_config.replace('spawn-at-startup "sh" "-c" "command -v fcitx5 >/dev/null 2>&1 && exec fcitx5 -d"',
            'spawn-at-startup "systemctl" "--user" "start" "mocha-input-method.service"')
        main_config = main_config.replace('include "animations.kdl"', 'include "animations__custom__.kdl"')
        main_config = main_config.replace('spawn-at-startup "~/.config/niri/scripts/session-shell.sh"',
            'spawn-at-startup "systemctl" "--user" "start" "mocha-nyxuri-shell.service"')
        (niri / "animations__custom__.kdl").write_text((niri / "animations.kdl").read_text())
        (niri / "mocha-tablet.kdl").write_text(main_config)
        (niri / "config.kdl").write_text(main_config)
        custom = niri / "__custom__.kdl"
        custom.write_text(custom.read_text() + '\nwindow-rule {\n    match app-id="mocha-nyxuri-settings.py"\n    open-floating true\n    default-column-width { proportion 0.65; }\n    default-window-height { proportion 0.75; }\n}\n')
        (niri / "monitor.kdl").write_text('output "DSI-1" { scale 1.5; transform "270"; }\n'
            'output "Unknown-1" { scale 1.5; transform "270"; }\n')
        input_file = niri / "input__custom__.kdl"
        input_text = re.sub(r"gestures\s*\{.*?^\}", "", input_file.read_text(), flags=re.S | re.M)
        input_text = input_text.replace("input {", 'input {\n    touch { map-to-output "DSI-1"; }\n    disable-power-key-handling', 1)
        input_file.write_text(input_text + "\n" + (args.adapter / "tablet/gestures.kdl").read_text())
        # The old physical input/legacy files remain available for rollback.
        old = config / "niri"
        for name in ("mocha-tablet-legacy.kdl", "gestures.kdl"):
            if (old / name).is_file():
                shutil.copy2(old / name, niri / name)
        # Do not lose the physical mapping if a prior custom input file exists.
        if (old / "input__custom__.kdl").is_file():
            existing = (old / "input__custom__.kdl").read_text()
            if 'map-to-output "DSI-1"' not in existing:
                print("Existing custom input requires the physical mapping; edit it before deployment", file=sys.stderr)
                return 1
        noctalia = content_dir / "noctalia"
        text = (noctalia / "noctalia-config.toml").read_text()
        text = text.replace(str(home / "图片/Wallpapers"), str(home / "Pictures/Wallpapers"))
        # Upstream used the centre of a 2560x1440 monitor. Keep the widget at
        # the centre of this display's logical 1365x1024 landscape coordinates.
        text = text.replace("cx = 1280.0", "cx = 682.5").replace("cy = 720.0", "cy = 512.0")
        for output in ('DSI-1','Unknown-1'):
            text += f'\n[brightness.monitor.{output}]\nbackend = "backlight"\nbacklight_device = "mocha-miui-backlight"\n'
        plugins = source.parent / "nyxuri-official-plugins/official-plugins-main"
        if not (plugins / "mpvpaper/plugin.toml").is_file():
            parser.error("The pinned official mpvpaper plugin source is missing")
        text += f'\n[[plugins.source]]\nname = "nyxuri-official"\nkind = "path"\nlocation = "{plugins}"\nenabled = true\n'
        (noctalia / "noctalia-config.toml").write_text(text)
        # GTK 3 implements mix(), while the upstream web-style color-mix()
        # spelling is not recognized. Preserve the exact colour weights.
        gtk = noctalia / "templates/gtk-3.0.css"
        gtk_text = re.sub(r"color-mix\(in srgb, (\{\{[^}]+\}\}) (\d+)%, (\{\{[^}]+\}\})\)",
            lambda m: f"mix({m[1]}, {m[3]}, {1-int(m[2])/100:.2f})", gtk.read_text())
        gtk.write_text(gtk_text)
        result = subprocess.run(["niri", "validate", "-c", str(niri / "mocha-tablet.kdl")], capture_output=True, text=True)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return result.returncode
        if args.check:
            print("NYXURI_FULL_CONFIG_VALID")
            return 0
        backup = home / ".local/state/nyxuri/mocha-backups" / time.strftime("%Y%m%d-%H%M%S")
        backup.mkdir(parents=True)
        names = [p.name for p in content_dir.iterdir() if not p.name.startswith(".") and not p.name.endswith(".module.toml")]
        for name in names:
            current = config / name
            if current.is_dir():
                shutil.copytree(current, backup / name, symlinks=True)
            elif current.is_file():
                shutil.copy2(current, backup / name)
        settings = home / ".local/state/noctalia/settings.toml"
        if settings.is_file():
            # One-time migration: previous simplified overrides otherwise
            # mask upstream defaults. All later UI adjustments are retained.
            if not (home / ".local/state/nyxuri/mocha-full-installed.json").exists():
                shutil.copy2(settings, backup / "noctalia-settings.toml")
                settings.rename(settings.with_name("settings.pre-nyxuri.toml"))
        for name in names:
            item = content_dir / name
            preserve = []
            if item.is_dir():
                manifest = load_manifest(source / "configs" / name)
                preserve = list(manifest.preserve)
                # monitor.kdl from older installs may refer to another panel.
                # Our first deployment supplies the tested rotation; subsequent
                # deployment preserves user adjustments just like upstream.
                if not (home / ".local/state/nyxuri/mocha-full-installed.json").exists():
                    preserve = [p for p in preserve if p != "monitor.kdl"]
            if not atomic_replace_item(item, config / name, preserve=preserve):
                raise RuntimeError(f"Deploy failed for {name}; backup: {backup}")
        for path in (config / "niri/scripts").glob("*"):
            if path.suffix in (".sh", ".py"):
                path.chmod(0o755)
        for path in (config / "noctalia/tools").glob("*.py"):
            path.chmod(0o755)
        for path in (config / "noctalia").glob("*.sh"):
            path.chmod(0o755)
        (home / ".local/bin").mkdir(parents=True, exist_ok=True)
        for name in ("mocha-nyxuri-settings.py",):
            shutil.copy2(args.adapter / "tablet" / name, home / ".local/bin" / name)
            (home / ".local/bin" / name).chmod(0o755)
        appdir = home / ".local/share/applications"
        appdir.mkdir(parents=True, exist_ok=True)
        commands = {
            "nyxuri-settings": ("Nyxuri 效果与触屏设置", str(home / ".local/bin/mocha-nyxuri-settings.py")),
            "nyxuri-orbit": ("Nyxuri Orbit 星环启动器", str(config / "noctalia/tools/orbit-launcher.py")),
            "nyxuri-wallpaper": ("Nyxuri 静态与动态壁纸", str(config / "noctalia/tools/wallpaper-picker.py")),
            "nyxuri-translate": ("Nyxuri Orbit 翻译", str(config / "noctalia/tools/orbit-translate.py")),
        }
        for identifier, (label, command) in commands.items():
            (appdir / f"{identifier}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={label}\nExec={command}\nIcon=preferences-desktop\nTerminal=false\nCategories=Settings;Utility;\n")
        bindir = home / ".local/bin"
        bindir.mkdir(exist_ok=True, parents=True)
        (bindir / "nyxuri").write_text('#!/bin/sh\nexport PYTHONPATH=' + str(source) + '${PYTHONPATH:+:$PYTHONPATH}\nexec /usr/bin/python3 -m nyxuri "$@"\n')
        (bindir / "nyxuri").chmod(0o755)
        wallpapers = home / "Pictures/Wallpapers"
        wallpapers.mkdir(parents=True, exist_ok=True)
        for image in (source / "assets/wallpapers").rglob("*"):
            if image.is_file() and image.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".mp4", ".webm"):
                destination = wallpapers / image.relative_to(source / "assets/wallpapers")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copy2(image, destination)
        from nyxuri.modules.fcitx import fcitx_install
        from nyxuri.modules.gtktheme import gtktheme_install
        if not fcitx_install() or not gtktheme_install():
            raise RuntimeError(f"Theme module installation failed; backup: {backup}")
        record = home / ".local/state/nyxuri/mocha-full-installed.json"
        record.write_text(json.dumps({"upstream": PIN, "backup": str(backup), "modules": names,
            "hardware": {"transform": 270, "scale": 1.5, "render_node": "renderD128"}}, indent=2) + "\n")
        units = home / '.config/systemd/user'
        units.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.adapter / 'tablet/mocha-nyxuri-shell.service', units / 'mocha-nyxuri-shell.service')
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', 'mocha-nyxuri-shell.service'], check=True)
        subprocess.run([sys.executable, str(args.adapter / 'tools/install-touch-navigation.py'),
            '--adapter', str(args.adapter)], check=True)
        print(f"NYXURI_FULL_DEPLOYED backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
