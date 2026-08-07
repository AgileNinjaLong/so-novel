from PyQt6.QtWidgets import QLabel, QVBoxLayout
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow

class FloatingView(BaseStealthWindow):
    def __init__(self, config_manager, parent=None):
        super().__init__(config_manager, parent)
        self.init_ui()

    def init_ui(self):
        self.resize(600, 36)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 4, 10, 4)

        self.label = QLabel("NovelRead | 右键打开文件或直接拖拽小说到此处")
        self.label.setWordWrap(False)
        self.label.setAcceptDrops(False)
        
        font_size = self.config_mgr.settings.get("font_size", 11)
        font_family = self.config_mgr.settings.get("font_family", "Microsoft YaHei")
        font_color = self.config_mgr.settings.get("font_color", "#333333")
        bg_color = self.config_mgr.settings.get("bg_color", "#FFFFFF")

        self.setFont(QFont(font_family, font_size))
        self.setStyleSheet(f"""
            QLabel {{
                color: {font_color};
                background-color: {bg_color};
                border-radius: 4px;
                padding: 2px 8px;
            }}
        """)

        layout.addWidget(self.label)
        self.setLayout(layout)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.label.setText(error_msg)
            return

        if not self.book or not self.book.chapters:
            return

        chap = self.book.get_current_chapter()
        current_line_text = self.lines[self.book.current_line_idx] if self.lines else ""
        total_chaps = self.book.total_chapters
        progress_pct = int(((self.book.current_chapter_idx + 1) / total_chaps) * 100) if total_chaps else 0

        text = f"[{chap.title}] {current_line_text}  ({progress_pct}%)"
        self.label.setText(text)
