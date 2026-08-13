from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QColor
from PyQt6.QtCore import Qt, QTimer
from src.ui.base_window import BaseStealthWindow

class FloatingView(BaseStealthWindow):
    def __init__(self, config_manager, parent=None, bookshelf_window=None):
        super().__init__(config_manager, parent=parent, bookshelf_window=bookshelf_window)
        self.mode_name = "floating"
        self.scroll_y = 0.0
        self.line_height = 28
        self.init_ui()

    def init_ui(self):
        self.resize(600, 36)
        font_size = self.config_mgr.settings.get("font_size", 11)
        font_family = self.config_mgr.settings.get("font_family", "Microsoft YaHei")
        self.setFont(QFont(font_family, font_size))

    def _on_auto_scroll_timeout(self):
        """60 FPS 匀速连续向上像素推进回调"""
        if not self.is_auto_scrolling:
            return
            
        speed_px_per_sec = float(self.config_mgr.settings.get("auto_scroll_speed", 30))
        speed_per_frame = speed_px_per_sec / 60.0  # 每帧增量像素
        
        self.scroll_y += speed_per_frame
        
        # 当滚动过一行高度时，同步推进 line_idx 索引
        if self.scroll_y >= self.line_height:
            self.scroll_y -= self.line_height
            if self.book and self.lines:
                if self.book.current_line_idx < len(self.lines) - 1:
                    self.book.current_line_idx += 1
                else:
                    if not self.book.next_chapter():
                        self.stop_auto_scroll()
                    else:
                        self.recalculate_lines(self.book.get_current_chapter())
                        self.book.current_line_idx = 0

        self.update()  # 触发 60 FPS 画面重绘

    def recalculate_lines(self, chap):
        from PyQt6.QtGui import QTextLayout
        fm = QFontMetrics(self.font())
        
        title_width = fm.horizontalAdvance(f"[{chap.title}]   (100%)")
        available_width = self.width() - title_width - 30
        if available_width < 50:
            available_width = 50
            
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
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor(self.config_mgr.settings.get("bg_color", "#FFFFFF"))
        font_color = QColor(self.config_mgr.settings.get("font_color", "#333333"))

        # 绘制无边框圆角背景底板
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)

        painter.setFont(self.font())
        painter.setPen(font_color)

        if not self.book or not self.book.chapters or not self.lines:
            painter.drawText(12, 24, "NovelRead | 右键打开文件或直接拖拽小说到此处")
            return

        chap = self.book.get_current_chapter()
        total_chaps = self.book.total_chapters
        progress_pct = int(((self.book.current_chapter_idx + 1) / total_chaps) * 100) if total_chaps else 0

        auto_speed = self.config_mgr.settings.get("auto_scroll_speed", 30)
        auto_tag = f" ▶ [{auto_speed}px/s]" if self.is_auto_scrolling else ""
        header_tag = f"[{chap.title}] "
        footer_tag = f"  ({progress_pct}%){auto_tag}"

        curr_idx = self.book.current_line_idx
        next_idx = curr_idx + 1 if curr_idx + 1 < len(self.lines) else 0

        line1 = self.lines[curr_idx]
        line2 = self.lines[next_idx] if curr_idx + 1 < len(self.lines) else ""

        text1 = f"{header_tag}{line1}{footer_tag}"
        text2 = f"{header_tag}{line2}{footer_tag}"

        # 基于 scroll_y 绘制像素级匀速向上滑动
        draw_y1 = int(24 - self.scroll_y)
        draw_y2 = int(24 + self.line_height - self.scroll_y)

        painter.drawText(12, draw_y1, text1)
        if line2:
            painter.drawText(12, draw_y2, text2)
