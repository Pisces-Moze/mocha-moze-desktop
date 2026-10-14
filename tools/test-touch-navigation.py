#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Regression checks for empty-desktop key storms and workspace identity."""
import importlib.machinery
import pathlib
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).resolve().parents[1] / 'tablet/mocha-touch-nav'
nav = importlib.machinery.SourceFileLoader('touch_nav', str(path)).load_module()


class Navigation(unittest.TestCase):
    def dispatch(self, command):
        with patch.object(nav.sys, 'argv', ['mocha-touch-nav', command]):
            self.assertEqual(nav.main(), 0)

    def test_empty_back_does_not_inject_or_close_inactive_ui(self):
        with patch.object(nav, 'hide_keyboard', return_value=False), \
             patch.object(nav, 'noctalia', return_value={'panelOpen': False}) as shell, \
             patch.object(nav, 'niri', side_effect=lambda request: {'is_open':False} if request=='OverviewState' else None), \
             patch.object(nav, 'action') as action, patch.object(nav, 'run') as inject:
            for _ in range(20): self.dispatch('back')
            action.assert_not_called()
            inject.assert_not_called()
            self.assertEqual(shell.call_args_list, [unittest.mock.call('status')]*20)

    def test_keyboard_consumes_back_before_app_or_overview(self):
        with patch.object(nav, 'hide_keyboard', return_value=True), \
             patch.object(nav, 'niri') as ipc, patch.object(nav, 'noctalia') as shell:
            self.dispatch('back')
            ipc.assert_not_called(); shell.assert_not_called()

    def test_home_is_noop_on_current_empty_workspace(self):
        spaces=[{'id':99,'idx':1,'is_focused':True,'output':'DSI-1'}]
        def reply(request):
            return {'OverviewState':{'is_open':False},'Workspaces':spaces,'Windows':[]}[request]
        with patch.object(nav,'hide_keyboard'), patch.object(nav,'close_panel'), \
             patch.object(nav,'niri',side_effect=reply), patch.object(nav,'action') as action:
            for _ in range(20): self.dispatch('home')
            action.assert_not_called()

    def test_home_uses_workspace_id_not_mutable_index_or_other_output(self):
        spaces=[{'id':7,'idx':1,'is_focused':True,'output':'DSI-1'},
                {'id':91,'idx':2,'output':'HDMI-A-1'},
                {'id':42,'idx':3,'output':'DSI-1'}]
        def reply(request):
            return {'OverviewState':{'is_open':False},'Workspaces':spaces,
                    'Windows':[{'workspace_id':7}]}[request]
        with patch.object(nav,'hide_keyboard'), patch.object(nav,'close_panel'), \
             patch.object(nav,'niri',side_effect=reply), patch.object(nav,'action') as action:
            self.dispatch('home')
            action.assert_called_once_with('FocusWorkspace',reference={'Id':42})

    def test_browser_back_remains_history_navigation(self):
        def reply(request):
            return {'is_open':False} if request=='OverviewState' else {'app_id':'org.mozilla.firefox'}
        with patch.object(nav,'hide_keyboard',return_value=False), patch.object(nav,'close_panel',return_value=False), \
             patch.object(nav,'niri',side_effect=reply), patch.object(nav,'run') as inject:
            self.dispatch('back')
            inject.assert_called_once_with('wtype','-M','alt','-k','Left','-m','alt')


if __name__=='__main__': unittest.main()
