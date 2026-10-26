#!/usr/bin/env python3
"""Test the patched picker backend without launching a desktop or player."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backend', Path(sys.argv.pop(1)))
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class ManagedWallpaper(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'assignments.json'
        self.video = self.root / "动画 wallpaper 'a'.mp4"
        self.video.touch()
        self.state.write_text(json.dumps({'assignments': {'*': 'old.mp4'}, 'futureMetadata': 7}))
        self.addCleanup(patch.stopall)
        patch.object(backend, 'STATE_DIR', str(self.root)).start()
        patch.object(backend, 'ASSIGNMENTS_FILE', str(self.state)).start()
        patch.object(backend.subprocess, 'Popen', side_effect=AssertionError('Do not spawn a separate player')).start()
        patch.object(backend, '_clear_mpvpaper', side_effect=AssertionError('Plugin owns process lifecycle')).start()

    def test_selection_uses_plugin_and_waits_for_persisted_state(self):
        def command(argv, **kwargs):
            self.assertEqual(argv, ['noctalia', 'msg', 'plugin', 'noctalia/mpvpaper:service', 'all', 'set-video', str(self.video)])
            self.assertNotIn('shell', kwargs)
            self.state.write_text(json.dumps({'assignments': {'*': str(self.video)}, 'futureMetadata': 7}))
            return subprocess.CompletedProcess(argv, 0, 'ok: dispatched 1\n', '')
        with patch.object(backend.subprocess, 'run', side_effect=command):
            self.assertTrue(backend.apply_dynamic_wallpaper(str(self.video)))

    def test_ipc_error_is_not_success(self):
        with patch.object(backend.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'error: missing service', '')):
            self.assertFalse(backend.apply_dynamic_wallpaper(str(self.video)))

    def test_acknowledged_unknown_event_is_not_success(self):
        with patch.object(backend.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok: dispatched 1', '')), \
             patch.object(backend.time, 'monotonic', side_effect=[0, 4]):
            self.assertFalse(backend.apply_dynamic_wallpaper(str(self.video)))

    def test_clear_preserves_metadata_and_last_selection(self):
        backend._write_mpvpaper_assignments({})
        data = json.loads(self.state.read_text())
        self.assertEqual(data['assignments'], {})
        self.assertEqual(data['lastAssignments'], {'*': 'old.mp4'})
        self.assertEqual(data['futureMetadata'], 7)

    def test_missing_video_does_not_dispatch(self):
        with patch.object(backend.subprocess, 'run', side_effect=AssertionError('Missing file must not be selected')):
            self.assertFalse(backend.apply_dynamic_wallpaper(str(self.root/'missing.mp4')))

    def test_static_selection_uses_plugin_completed_handover(self):
        image = self.root/'still.png'
        image.touch()
        def command(argv, **kwargs):
            self.assertEqual(argv, ['noctalia', 'msg', 'plugin', 'noctalia/mpvpaper:service', 'all', 'set-static', str(image)])
            self.assertNotIn('shell', kwargs)
            self.state.write_text(json.dumps({'assignments': {}, 'staticSelection': str(image)}))
            return subprocess.CompletedProcess(argv, 0, 'ok: dispatched 1\n', '')
        with patch.object(backend.subprocess, 'run', side_effect=command):
            self.assertTrue(backend.apply_static_wallpaper(str(image)))

    def test_static_acknowledgement_without_completion_is_not_success(self):
        image = self.root/'still.png'
        image.touch()
        with patch.object(backend.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok: dispatched 1', '')), \
             patch.object(backend.time, 'monotonic', side_effect=[0, 6]):
            self.assertFalse(backend.apply_static_wallpaper(str(image)))


if __name__ == '__main__':
    unittest.main()
