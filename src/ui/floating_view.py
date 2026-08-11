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
        
        # 禁止 label 根据内容自动撑开窗口
        from PyQt6.QtWidgets import QSizePolicy
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.label.setMinimumWidth(1)
        
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

    def get_line_length(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        char_width = fm.horizontalAdvance("中")
        if char_width == 0:
            char_width = 12
        available_width = self.width() - 40
        return max(10, available_width // char_width)

    def recalculate_lines(self, chap):
        from PyQt6.QtGui import QTextLayout, QFontMetrics
        fm = QFontMetrics(self.font())
        
        # 预留给标题和进度的空间
        title_width = fm.horizontalAdvance(f"[{chap.title}]   (100%)")
        available_width = self.width() - title_width - 30
        if available_width < 50:
            available_width = 50
            
        # 如果缓存有效，则直接返回
        if hasattr(self, '_cached_chap_index') and self._cached_chap_index == chap.index and getattr(self, '_cached_width', 0) == available_width:
            return
            
        lines = []
        for paragraph in chap.content.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            layout = QTextLayout(paragraph, self.font())
            layout.beginLayout()
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_width)
                lines.append(paragraph[line.textStart():line.textStart() + line.textLength()])
            layout.endLayout()
            
        self.lines = lines if lines else [""]
        self._cached_chap_index = chap.index
        self._cached_width = available_width

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

        auto_tag = f" ▶ [{self.config_mgr.settings.get('auto_scroll_interval', 2.5)}s]" if self.is_auto_scrolling else ""
        text = f"[{chap.title}] {current_line_text}  ({progress_pct}%){auto_tag}"
        self.label.setText(text)
