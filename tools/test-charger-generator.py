#!/usr/bin/python3
"""A read-only generator must not consume persistent boot state."""
import importlib.machinery, importlib.util, pathlib, unittest
from unittest.mock import patch, MagicMock
path=pathlib.Path(__file__).resolve().parents[1]/'charging/mocha-charger-generator'
loader=importlib.machinery.SourceFileLoader('charger_generator',str(path))
spec=importlib.util.spec_from_loader(loader.name,loader)
generator=importlib.util.module_from_spec(spec);loader.exec_module(generator)

class Tests(unittest.TestCase):
    def test_policy(self):
        self.assertTrue(generator.select_charge(True,True,'console=tty0',False))
        for args in [(False,True,'',False),(True,False,'',False),(True,True,'',True),(True,True,'systemd.unit=multi-user.target',False),(True,True,'mocha_native_debug4=1',False)]:
            self.assertFalse(generator.select_charge(*args))

    def test_desktop_once_is_only_read(self):
        paths={}
        def mock_path(name):
            if name not in paths:paths[name]=MagicMock()
            return paths[name]
        mock_path('/boot/mocha-charger.enabled').exists.return_value=True
        mock_path('/boot/mocha-desktop.once').exists.return_value=True
        mock_path('/sys/class/power_supply/bq24190-charger/online').read_text.return_value='1'
        mock_path('/proc/cmdline').read_text.return_value='console=tty0'
        with patch.object(generator,'Path',side_effect=mock_path),patch.object(generator,'power_key_held',return_value=False),patch.object(generator.sys,'argv',['generator','normal','early','late']):generator.main()
        mock_path('/boot/mocha-desktop.once').unlink.assert_not_called()
        self.assertNotIn('early',paths)

    def test_power_intent_bypasses_charging_only_with_ready_battery(self):
        for command,held,capacity,charge in [('mocha_desktop_requested=1',False,'73',False),
                                            ('console=tty0',True,'73',False),
                                            ('console=tty0',False,'73',True),
                                            ('mocha_desktop_requested=1',False,'4',True),
                                            ('mocha_desktop_requested=1',False,'unavailable',True)]:
            with self.subTest(command=command,held=held,capacity=capacity):
                paths={}
                def path(name):
                    if name not in paths:paths[name]=MagicMock()
                    return paths[name]
                path('/boot/mocha-charger.enabled').exists.return_value=True
                path('/boot/mocha-desktop.once').exists.return_value=False
                path('/sys/class/power_supply/bq24190-charger/online').read_text.return_value='1'
                path('/sys/class/power_supply/bq27520g4-0/capacity').read_text.return_value=capacity
                path('/proc/cmdline').read_text.return_value=command
                with patch.object(generator,'Path',side_effect=path),patch.object(generator,'power_key_held',return_value=held),patch.object(generator.sys,'argv',['generator','normal','early','late']):generator.main()
                self.assertEqual('early' in paths,charge)

if __name__=='__main__':unittest.main()
