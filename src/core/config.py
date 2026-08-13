import json
import os
import sys
from typing import Dict, Any, Optional
from PyQt6.QtCore import QTimer, QObject

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")

DEFAULT_SETTINGS = {
    "boss_key": "Alt+Z",
    "hk_floating": "Ctrl+1",
    "hk_ide": "Ctrl+2",
    "hk_cad": "Ctrl+3",
    "hk_next_line": "Down",
    "hk_prev_line": "Up",
    "hk_next_chap": "PageDown",
    "hk_prev_chap": "PageUp",
    "hk_toggle_auto": "Ctrl+Space",
    "auto_scroll_speed": 8.0,
    "auto_scroll_interval": 2.5,
    "opacity": 0.85,
    "idle_opacity": 0.15,
    "mode": "floating",  # 'floating' 或 'ide_pseudo'
    "font_size": 11,
    "font_family": "Microsoft YaHei",
    "font_color": "#333333",
    "bg_color": "#FFFFFF",
    "line_length": 35,
    "last_file": "",      # 上次打开的图书路径
    "auto_restore_last_read": True, # 软件启动时自动恢复上次阅读进度（精准至行索引）
    "bookshelf": {}       # 书架列表 path -> {title, author, format, add_time, chapter_index, character_offset}
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

    def get_bookshelf(self) -> Dict[str, Dict[str, Any]]:
        if "bookshelf" not in self.settings or not isinstance(self.settings["bookshelf"], dict):
            self.settings["bookshelf"] = {}
        return self.settings["bookshelf"]

    def add_to_bookshelf(self, file_path: str, info: Optional[Dict[str, Any]] = None):
        import time
        file_path = os.path.abspath(file_path)
        shelf = self.get_bookshelf()
        
        filename = os.path.basename(file_path)
        name_without_ext, ext = os.path.splitext(filename)
        fmt = ext.lstrip('.').lower() or 'txt'
        
        title = name_without_ext
        author = "未知作者"
        if "_" in name_without_ext:
            parts = name_without_ext.split("_", 1)
            title, author = parts[0], parts[1]
        elif "(" in name_without_ext and ")" in name_without_ext:
            title = name_without_ext.split("(")[0]
            author = name_without_ext.split("(")[1].rstrip(")")

        data = {
            "title": info.get("title", title) if info else title,
            "author": info.get("author", author) if info else author,
            "format": fmt,
            "add_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_type": info.get("source_type", "local") if info else "local",
            "url": info.get("url", "") if info else "",
            "rule": info.get("rule", {}) if info else {},
            "is_auto_update": info.get("is_auto_update", 0) if info else 0,
            "chapter_index": 0,
            "character_offset": 0
        }
        if info:
            data.update(info)

        shelf[file_path] = data
        self._save_timer.start()

    def remove_from_bookshelf(self, file_path: str):
        file_path = os.path.abspath(file_path)
        shelf = self.get_bookshelf()
        if file_path in shelf:
            del shelf[file_path]
            self._save_timer.start()

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
        self.settings["last_file"] = file_path
        # 触发防抖保存
        self._save_timer.start()

    def get_last_file(self) -> Optional[str]:
        last_file = self.settings.get("last_file", "")
        if last_file and os.path.exists(last_file):
            return last_file
        elif last_file:
            # 文件不存在或已被删除，清除记录
            self.settings["last_file"] = ""
            self.save_immediately()
        return None
        
    def save_immediately(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
        self.save()
