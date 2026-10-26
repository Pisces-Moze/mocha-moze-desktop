#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Keep NyxMellow's selected candidate readable without depending on SVG loading.

Run for the active user's home and for the Nyxuri source assets. Updating both
the generated theme and its template makes the fix survive palette changes.
Never reads preedit, candidates or passwords.
"""
import argparse
from pathlib import Path
import re


def repair(text):
    template = '{{ colors.primary.default.hex }}' in text or '{{ colors.on_primary.default.hex }}' in text
    color = '{{ colors.primary.default.hex }}' if template else None
    # The paired text/background values use exactly the same palette role.
    # Generated theme.conf contains the selected text role; a safe explicit
    # fallback is used until Noctalia regenerates the template.
    if color is None:
        match = re.search(r'^HighlightBackgroundColor=(#[0-9a-fA-F]{6})(?:ff)?$', text, re.M)
        color = match[1] if match and match[1].lower() != '#000000' else '#b6c7e7'
        text = re.sub(r'(?m)^HighlightCandidateColor=.*$', 'HighlightCandidateColor=#161a23', text, count=1)
    section = re.compile(r'(\[InputPanel/Highlight\]\n)(.*?)(?=\n\[|\Z)', re.S)
    def replace(match):
        body = re.sub(r'(?m)^Image=.*$', 'Image=', match[2])
        body = re.sub(r'(?m)^Color=.*$', 'Color=' + color, body)
        return match[1] + body
    return section.sub(replace, text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, default=Path.home())
    p.add_argument('--source', type=Path)
    a = p.parse_args()
    roots = [a.home/'.local/share/fcitx5/themes/nyxmellow']
    if a.source:
        roots.append(a.source/'assets/fcitx5/nyxmellow')
    for root in roots:
        for path in (root/'theme.conf', root/'templates/theme.conf'):
            if not path.is_file():
                continue
            original = path.read_text(encoding='utf-8')
            revised = repair(original)
            if revised != original:
                path.write_text(revised, encoding='utf-8')
                print('Repaired selected-candidate background:', path)


if __name__ == '__main__':
    main()
