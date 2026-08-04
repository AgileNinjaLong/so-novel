import sys
from PyQt6.QtCore import QObject, pyqtSignal

class BossKeyManager(QObject):
    triggered = pyqtSignal()

    def __init__(self, key_combination: str = "Alt+Z"):
        super().__init__()
        self.key_combination = key_combination
        self.is_active = False

    def start(self):
        try:
            import keyboard
            # 将 PyQt 快捷键转换为 keyboard 库格式
            hk = self.key_combination.lower().replace("alt", "alt").replace("ctrl", "ctrl")
            keyboard.add_hotkey(hk, self._on_triggered)
            self.is_active = True
        except Exception:
            # 环境缺乏全局 hook 权限时降级处理
            self.is_active = False

    def _on_triggered(self):
        self.triggered.emit()

    def stop(self):
        try:
            import keyboard
            keyboard.remove_hotkey(self._on_triggered)
        except Exception:
            pass
