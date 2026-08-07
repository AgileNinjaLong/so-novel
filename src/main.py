import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QShortcut, QKeySequence
from src.core.config import ConfigManager
from src.ui.floating_view import FloatingView
from src.ui.ide_pseudo_view import IDEPseudoView
from src.ui.cad_pseudo_view import CADPseudoView
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
        self.cad_view = CADPseudoView(self.config_mgr)

        self.current_mode = self.config_mgr.settings.get("mode", "floating")
        if self.current_mode == "ide_pseudo":
            self.active_window = self.ide_view
        elif self.current_mode == "cad_pseudo":
            self.active_window = self.cad_view
        else:
            self.active_window = self.floating_view

        # 信号绑定
        for view in [self.floating_view, self.ide_view, self.cad_view]:
            view.file_loaded_signal.connect(lambda path, v=view: self.sync_file(path, v))
            view.settings_changed_signal.connect(self.reload_shortcuts)

        # 局部模式快捷键对象容器
        self.shortcuts = []
        self.reload_shortcuts()

        # 启动全局老板键服务
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

    def reload_shortcuts(self):
        # 清除旧快捷键
        for sc in self.shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.shortcuts.clear()

        # 重新绑定老板键（部分情况下老板键改动需要重新注册Win32事件）
        self.reload_boss_key()

        # 为每个窗口独立注册应用内快捷键
        for view in [self.floating_view, self.ide_view, self.cad_view]:
            hk_floating = self.config_mgr.settings.get("hk_floating", "Ctrl+1")
            if hk_floating:
                sc1 = QShortcut(QKeySequence(hk_floating), view)
                sc1.activated.connect(lambda: self.switch_to_mode("floating"))
                self.shortcuts.append(sc1)

            hk_ide = self.config_mgr.settings.get("hk_ide", "Ctrl+2")
            if hk_ide:
                sc2 = QShortcut(QKeySequence(hk_ide), view)
                sc2.activated.connect(lambda: self.switch_to_mode("ide_pseudo"))
                self.shortcuts.append(sc2)

            hk_cad = self.config_mgr.settings.get("hk_cad", "Ctrl+3")
            if hk_cad:
                sc3 = QShortcut(QKeySequence(hk_cad), view)
                sc3.activated.connect(lambda: self.switch_to_mode("cad_pseudo"))
                self.shortcuts.append(sc3)

    def sync_file(self, file_path: str, source_view):
        if source_view != self.floating_view:
            self.floating_view.load_file(file_path, notify=False)
        if source_view != self.ide_view:
            self.ide_view.load_file(file_path, notify=False)
        if source_view != self.cad_view:
            self.cad_view.load_file(file_path, notify=False)

    def show(self):
        last_file = self.config_mgr.get_last_file()
        if last_file:
            self.floating_view.load_file(last_file, notify=False)
            self.ide_view.load_file(last_file, notify=False)
            self.cad_view.load_file(last_file, notify=False)
        self.active_window.show()

    def switch_to_mode(self, target_mode: str):
        if self.current_mode == target_mode:
            return
            
        pos = self.active_window.pos()
        book = self.active_window.book

        self.active_window.hide()
        self.current_mode = target_mode
        
        if self.current_mode == "ide_pseudo":
            self.active_window = self.ide_view
        elif self.current_mode == "cad_pseudo":
            self.active_window = self.cad_view
        else:
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
