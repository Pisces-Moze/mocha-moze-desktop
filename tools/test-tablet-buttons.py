#!/usr/bin/python3
"""Power release ordering, bounce/repeat rejection, volume rate limiting."""
import importlib.util, pathlib, unittest
from unittest.mock import patch
p=pathlib.Path(__file__).resolve().parents[1]/'tablet/mocha-buttons.py'
spec=importlib.util.spec_from_file_location('buttons',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Tests(unittest.TestCase):
    def setUp(self):
        self.display = patch.object(m, 'display_off', return_value=None)
        self.display.start()
        self.addCleanup(self.display.stop)
        self.log = patch.object(m, 'record')
        self.log.start()
        self.addCleanup(self.log.stop)

    def test_idle_dpms_off_wakes_without_locking_again(self):
        b=m.Buttons()
        with patch.object(m,'display_off',return_value=True), patch.object(m,'status',return_value={'locked':True}), patch.object(m,'shell') as shell:
            b.power(.1)
            shell.assert_called_once_with('dpms-on')
            self.assertFalse(b.screen_off)

    def test_dpms_on_with_blank_backlight_is_still_off(self):
        self.display.stop()
        with patch.object(m.glob,'glob',return_value=['/fake/dpms']), patch.object(m.Path,'read_text',return_value='On'), patch.object(m,'BACKLIGHT') as lamp:
            lamp.read_text.return_value='0'
            self.assertTrue(m.display_off())

    def test_only_release_dispatches_and_repeat_is_ignored(self):
        b=m.Buttons()
        with patch.object(b,'power') as power:
            b.event(116,1,10);b.event(116,2,10.2)
            power.assert_not_called()
            b.event(116,0,10.3)
            power.assert_called_once()
            self.assertAlmostEqual(power.call_args.args[0],.3)
            b.event(116,0,10.4)
            power.assert_called_once()

    def test_bounce_and_unmatched_release(self):
        b=m.Buttons()
        with patch.object(b,'power') as power:
            b.event(116,0,5)
            b.event(116,1,10);b.event(116,0,10.1)
            b.event(116,1,10.15);b.event(116,0,10.2)
            power.assert_called_once()

    def test_volume_repeat_rate_limit(self):
        b=m.Buttons()
        with patch.object(m,'shell') as shell:
            b.event(115,1,10);b.event(115,2,10.01);b.event(115,2,10.2)
            b.event(114,0,10.3)
            self.assertEqual(shell.call_args_list,[unittest.mock.call('volume-up','5')]*2)

    def test_wake_keeps_lock(self):
        b=m.Buttons();b.screen_off=True
        with patch.object(m,'shell') as shell, patch.object(m,'status',return_value={'locked':True}):
            b.power(.1)
            shell.assert_called_once_with('dpms-on')
            self.assertFalse(b.screen_off)

    def test_failed_lock_does_not_turn_screen_off(self):
        b=m.Buttons()
        with patch.object(m,'shell',return_value=None) as shell:
            b.power(.1)
            shell.assert_called_once_with('session','lock')
            self.assertFalse(b.screen_off)

    def test_long_press_opens_menu(self):
        b=m.Buttons()
        with patch.object(m,'shell') as shell:
            b.power(2.1)
            shell.assert_called_once_with('panel-open','session')

    def test_lock_acquired_before_off(self):
        b=m.Buttons()
        result=type('Result',(),{'returncode':0})()
        with patch.object(m,'shell',return_value=result) as shell, patch.object(m,'status',return_value={'locked':True}), patch.object(m.time,'sleep'):
            b.power(.1)
            self.assertEqual(shell.call_args_list,[unittest.mock.call('session','lock'),unittest.mock.call('dpms-off')])
            self.assertTrue(b.screen_off)

    def test_touch_unlock_clears_stale_off_state(self):
        b=m.Buttons();b.screen_off=True
        result=type('Result',(),{'returncode':0})()
        with patch.object(m,'shell',return_value=result) as shell, patch.object(m,'status',side_effect=[{'locked':False},{'locked':True}]), patch.object(m.time,'sleep'):
            b.power(.1)
            self.assertEqual(shell.call_args_list,[unittest.mock.call('session','lock'),unittest.mock.call('dpms-off')])
            self.assertTrue(b.screen_off)

    def test_backlight_restore_preserves_user_brightness(self):
        b=m.Buttons()
        with patch.object(m,'BACKLIGHT') as lamp:
            lamp.read_text.return_value='96'
            b.backlight(False);b.backlight(True)
            self.assertEqual(lamp.write_text.call_args_list,[unittest.mock.call('0'),unittest.mock.call('96')])
            self.assertIsNone(b.saved_brightness)

if __name__=='__main__':unittest.main()
