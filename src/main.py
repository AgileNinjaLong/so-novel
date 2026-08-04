import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from src.core.config import ConfigManager
from src.ui.floating_view import FloatingView
from src.ui.ide_pseudo_view import IDEPseudoView
from src.ui.boss_key import BossKeyManager

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"CRITICAL ERROR: {err_msg}", file=sys.stderr)

sys.excepthook = handle_exception

class NovelReadApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.config_mgr = ConfigManager()

        self.floating_view = FloatingView(self.config_mgr)
        self.ide_view = IDEPseudoView(self.config_mgr)

        self.current_mode = self.config_mgr.settings.get("mode", "floating")
        self.active_window = self.floating_view if self.current_mode == "floating" else self.ide_view

        # 信号绑定
        self.floating_view.switch_mode_signal.connect(self.switch_view_mode)
        self.ide_view.switch_mode_signal.connect(self.switch_view_mode)
        self.floating_view.file_loaded_signal.connect(lambda path: self.ide_view.load_file(path, notify=False))
        self.ide_view.file_loaded_signal.connect(lambda path: self.floating_view.load_file(path, notify=False))

        # 启动全局老板键服务
        boss_key_str = self.config_mgr.settings.get("boss_key", "Alt+Z")
        self.boss_mgr = BossKeyManager(boss_key_str)
        self.boss_mgr.triggered.connect(self.on_boss_key_triggered)
        self.boss_mgr.start()

        # 程序退出前强制持久化保存
        self.app.aboutToQuit.connect(self.config_mgr.save_immediately)

    def show(self):
        # 自动加载上一次的小说（若存在）
        last_file = self.config_mgr.get_last_file()
        if last_file:
            self.floating_view.load_file(last_file)
            self.ide_view.load_file(last_file)
        self.active_window.show()

    def switch_view_mode(self):
        pos = self.active_window.pos()
        book = self.active_window.book

        self.active_window.hide()
        if self.current_mode == "floating":
            self.current_mode = "ide_pseudo"
            self.active_window = self.ide_view
        else:
            self.current_mode = "floating"
            self.active_window = self.floating_view

        self.config_mgr.settings["mode"] = self.current_mode
        self.config_mgr.save_immediately()

        if book:
            self.active_window.book = book
            self.active_window.update_content()

        self.active_window.move(pos)
        self.active_window.show()
        self.active_window.raise_()
        self.active_window.activateWindow()

    def on_boss_key_triggered(self):
        self.active_window.toggle_boss_key()

    def run(self):
        self.show()
        sys.exit(self.app.exec())

if __name__ == "__main__":
    app = NovelReadApp()
    app.run()
