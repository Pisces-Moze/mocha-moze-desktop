#!/usr/bin/env python3
"""Protect panel namespace adaptation and its effect policy boundary."""
import importlib.util
from pathlib import Path
import re
import unittest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-nyxuri.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PanelNamespaces(unittest.TestCase):
    def test_panel_mapping_preserves_effects_and_ignores_input_only_surfaces(self):
        source = 'layer-rule {\n match namespace="^(nyxuri|clavis)-shell-"\n background-effect { xray false; }\n}\n'
        adapted = installer.adapt_panel_namespaces(source)
        pattern = re.search('namespace="([^"]+)"', adapted)[1]
        for name in ['nyxuri-shell-control-center', 'clavis-shell-osd', 'noctalia-panel', 'noctalia-osd']:
            self.assertIsNotNone(re.search(pattern, name), name)
        for name in ['noctalia-panel-click-shield', 'noctalia-bar-bar', 'mpvpaper', 'unrelated-noctalia-panel']:
            self.assertIsNone(re.search(pattern, name), name)
        self.assertIn('background-effect { xray false; }', adapted)
        self.assertEqual(installer.adapt_panel_namespaces(adapted), adapted)

    def test_upstream_rule_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            installer.adapt_panel_namespaces('layer-rule {}')


if __name__ == '__main__':
    unittest.main()
