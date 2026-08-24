import os
import sys
import unittest
from PyQt6.QtWidgets import QApplication

from src.core.config import ConfigManager
from src.ui.stealth_views import STEALTH_VIEW_MAP
from src.ui.stealth_views.floating_view import FloatingView
from src.ui.stealth_views.ide_pseudo_view import IDEPseudoView
from src.ui.stealth_views.cad_pseudo_view import CADPseudoView

app = QApplication.instance() or QApplication(sys.argv)

class TestStealthModesSwitching(unittest.TestCase):
    def setUp(self):
        self.config_mgr = ConfigManager()

    def test_all_23_modes_in_map(self):
        self.assertEqual(len(STEALTH_VIEW_MAP), 23)
        self.assertIn("floating", STEALTH_VIEW_MAP)
        self.assertIn("ide_pseudo", STEALTH_VIEW_MAP)
        self.assertIn("cad_pseudo", STEALTH_VIEW_MAP)
        self.assertIn("excel_sheet", STEALTH_VIEW_MAP)

    def test_mode_instantiation(self):
        for mode_key, view_cls in STEALTH_VIEW_MAP.items():
            win = view_cls(self.config_mgr)
            self.assertEqual(win.mode_name, mode_key)
            win.close()

if __name__ == '__main__':
    unittest.main()
