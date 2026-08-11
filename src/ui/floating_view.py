from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QSizePolicy
from PyQt6.QtGui import QFont, QFontMetrics, QTextLayout
from PyQt6.QtCore import QPropertyAnimation, QPoint, QEasingCurve, QParallelAnimationGroup, Qt
from src.ui.base_window import BaseStealthWindow

class FloatingView(BaseStealthWindow):
    def __init__(self, config_manager, parent=None):
        super().__init__(config_manager, parent)
        self.anim_group = None
        self.init_ui()

    def init_ui(self):
        self.resize(600, 36)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 4, 10, 4)

        # 挂载两个 QLabel 的容器层，用于平滑向上滑动动画
        self.container = QWidget(self)
        self.container.setStyleSheet("background: transparent;")
        
        font_size = self.config_mgr.settings.get("font_size", 11)
        font_family = self.config_mgr.settings.get("font_family", "Microsoft YaHei")
        font_color = self.config_mgr.settings.get("font_color", "#333333")
        bg_color = self.config_mgr.settings.get("bg_color", "#FFFFFF")

        self.setFont(QFont(font_family, font_size))
        
        style = f"""
            QLabel {{
                color: {font_color};
                background-color: {bg_color};
                border-radius: 4px;
                padding: 2px 8px;
            }}
        """

        self.label1 = QLabel("NovelRead | 右键打开文件或直接拖拽小说到此处", self.container)
        self.label1.setStyleSheet(style)
        self.label1.setWordWrap(False)
        self.label1.setAcceptDrops(False)

        self.label2 = QLabel("", self.container)
        self.label2.setStyleSheet(style)
        self.label2.setWordWrap(False)
        self.label2.setAcceptDrops(False)

        self.label1.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.label2.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        layout.addWidget(self.container)
        self.setLayout(layout)
        
        self._current_label = self.label1
        self._next_label = self.label2

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.container.width()
        h = self.container.height()
        self.label1.setGeometry(0, 0, w, h)
        self.label2.setGeometry(0, h, w, h)

    def get_line_length(self) -> int:
        fm = QFontMetrics(self.font())
        char_width = fm.horizontalAdvance("中")
        if char_width == 0:
            char_width = 12
        available_width = self.width() - 40
        return max(10, available_width // char_width)

    def recalculate_lines(self, chap):
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
            self._current_label.setText(error_msg)
            return

        if not self.book or not self.book.chapters:
            return

        chap = self.book.get_current_chapter()
        current_line_text = self.lines[self.book.current_line_idx] if self.lines else ""
        total_chaps = self.book.total_chapters
        progress_pct = int(((self.book.current_chapter_idx + 1) / total_chaps) * 100) if total_chaps else 0

        auto_tag = f" ▶ [{self.config_mgr.settings.get('auto_scroll_interval', 2.5)}s]" if self.is_auto_scrolling else ""
        new_text = f"[{chap.title}] {current_line_text}  ({progress_pct}%){auto_tag}"

        # 如果没有开启自动翻页或者是第一次渲染/提示消息，直接静态更新无动画
        if not self.is_auto_scrolling or self._current_label.text() == new_text or "NovelRead" in self._current_label.text():
            if self.anim_group and self.anim_group.state() == QParallelAnimationGroup.State.Running:
                self.anim_group.stop()
            self._current_label.setText(new_text)
            return

        # 如果动画正在进行，先强制停止并复位
        if self.anim_group and self.anim_group.state() == QParallelAnimationGroup.State.Running:
            self.anim_group.stop()
            self._current_label.setGeometry(0, 0, self.container.width(), self.container.height())
            self._next_label.setGeometry(0, self.container.height(), self.container.width(), self.container.height())

        # 执行平滑向上滑动动画 (350ms OutCubic)
        w = self.container.width()
        h = self.container.height()

        self._next_label.setText(new_text)
        self._next_label.setGeometry(0, h, w, h)

        anim1 = QPropertyAnimation(self._current_label, b"pos", self)
        anim1.setDuration(350)
        anim1.setStartValue(QPoint(0, 0))
        anim1.setEndValue(QPoint(0, -h))
        anim1.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim2 = QPropertyAnimation(self._next_label, b"pos", self)
        anim2.setDuration(350)
        anim2.setStartValue(QPoint(0, h))
        anim2.setEndValue(QPoint(0, 0))
        anim2.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(anim1)
        self.anim_group.addAnimation(anim2)

        def _on_anim_finished():
            # 动画结束，交换两个 label 身份并归位
            self._current_label, self._next_label = self._next_label, self._current_label

        self.anim_group.finished.connect(_on_anim_finished)
        self.anim_group.start()
