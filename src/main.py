import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from src.core.config import ConfigManager
from src.ui.bookshelf_window import BookshelfWindow
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

        # 启动主书架窗口
        self.bookshelf_window = BookshelfWindow(self.config_mgr)
        
        # 启动全局老板键监听服务
        self.boss_mgr = None
        self.reload_boss_key()

        # 程序退出前强制持久化保存
        self.app.aboutToQuit.connect(self.config_mgr.save_immediately)

    def reload_boss_key(self):
        if self.boss_mgr:
            self.boss_mgr.stop()
        boss_key_str = self.config_mgr.settings.get("boss_key", "Alt+Z")
        self.boss_mgr = BossKeyManager(boss_key_str)
        self.boss_mgr.triggered.connect(self.on_boss_key_triggered)
        self.boss_mgr.start()

    def on_boss_key_triggered(self):
        # 一键隐藏或唤醒活动中的摸鱼伪装窗口或主书架窗口
        if hasattr(self.bookshelf_window, 'active_stealth_window') and self.bookshelf_window.active_stealth_window:
            self.bookshelf_window.active_stealth_window.toggle_boss_key()
        elif self.bookshelf_window:
            if self.bookshelf_window.isVisible():
                self.bookshelf_window.hide()
            else:
                self.bookshelf_window.show()
                self.bookshelf_window.raise_()
                self.bookshelf_window.activateWindow()

    def run(self):
        # 检查命令行入参，支持直接拉起文件
        if len(sys.argv) > 1:
            arg_file = sys.argv[1]
            if os.path.exists(arg_file):
                self.config_mgr.add_to_bookshelf(arg_file)
                self.bookshelf_window.refresh_bookshelf()
                self.bookshelf_window.start_reading(arg_file)
            else:
                self.bookshelf_window.show()
        else:
            self.bookshelf_window.show()

        sys.exit(self.app.exec())

if __name__ == "__main__":
    app = NovelReadApp()
    app.run()
