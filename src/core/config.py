import json
import os
from typing import Dict, Any
from PyQt6.QtCore import QTimer, QObject

DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".novelread", "config.json")

DEFAULT_SETTINGS = {
    "boss_key": "Alt+Z",
    "opacity": 0.85,
    "idle_opacity": 0.15,
    "mode": "floating",  # 'floating' 或 'ide_pseudo'
    "font_size": 11,
    "font_family": "Microsoft YaHei",
    "font_color": "#333333",
    "bg_color": "#FFFFFF",
    "line_length": 35
}

class ConfigManager(QObject):
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        super().__init__()
        self.config_path = config_path
        self.settings: Dict[str, Any] = DEFAULT_SETTINGS.copy()
        self.history: Dict[str, Dict[str, Any]] = {}
        
        # 延迟保存定时器（防频写磁盘卡顿）
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)  # 1秒防抖
        self._save_timer.timeout.connect(self.save)
        
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.settings.update(data.get("settings", {}))
                    self.history = data.get("history", {})
            except Exception:
                pass

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                "settings": self.settings,
                "history": self.history
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_progress(self, file_path: str) -> Dict[str, int]:
        return self.history.get(file_path, {"chapter_idx": 0, "line_idx": 0})

    def save_progress(self, file_path: str, chapter_idx: int, line_idx: int):
        self.history[file_path] = {
            "chapter_idx": chapter_idx,
            "line_idx": line_idx
        }
        # 触发防抖保存，避免每次滚轮滑动都操作IO
        self._save_timer.start()
        
    def save_immediately(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
        self.save()
