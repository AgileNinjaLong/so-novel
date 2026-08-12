import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout
from PyQt6.QtGui import QFont, QWheelEvent, QKeyEvent, QMouseEvent, QContextMenuEvent

class LogTextEdit(QTextEdit):
    def __init__(self, parent_view=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_view = parent_view

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if self.parent_view:
            if delta < 0:
                self.parent_view.next_line()
            else:
                self.parent_view.prev_line()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if not self.parent_view:
            super().keyPressEvent(event)
            return
        
        # 将按键事件转发给父窗口
        self.parent_view.keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if self.parent_view and event.button() == Qt.MouseButton.LeftButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(),
                parent_pos.toPointF(),
                event.globalPosition(),
                event.button(),
                event.buttons(),
                event.modifiers()
            )
            self.parent_view.mousePressEvent(pe)
            event.accept()
            return
        elif self.parent_view and event.button() == Qt.MouseButton.RightButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            cme = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, parent_pos.toPoint(), event.globalPosition().toPoint())
            self.parent_view.contextMenuEvent(cme)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.parent_view:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(),
                parent_pos.toPointF(),
                event.globalPosition(),
                event.button(),
                event.buttons(),
                event.modifiers()
            )
            self.parent_view.mouseMoveEvent(pe)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.parent_view and event.button() == Qt.MouseButton.LeftButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(),
                parent_pos.toPointF(),
                event.globalPosition(),
                event.button(),
                event.buttons(),
                event.modifiers()
            )
            self.parent_view.mouseReleaseEvent(pe)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class IDEPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, parent=None, bookshelf_window=None):
        super().__init__(config_manager, parent=parent, bookshelf_window=bookshelf_window)
        self.init_ui()

    def get_line_length(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self.editor.font())
        char_width = fm.horizontalAdvance("中")
        if char_width == 0:
            char_width = 12
        available_width = self.editor.viewport().width() - 20
        return max(20, available_width // char_width)

    def get_visible_lines_count(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self.editor.font())
        line_height = fm.lineSpacing()
        if line_height == 0:
            line_height = 20
        available_height = self.editor.viewport().height()
        return max(5, available_height // line_height)

    def init_ui(self):
        self.resize(720, 240)
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        self.editor = LogTextEdit(parent_view=self)
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setAcceptDrops(False)
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: rgb(51, 51, 51);
                color: #CCCCCC;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)

        layout.addWidget(self.editor)
        self.setLayout(layout)
        
        sample_log = [
            "[INFO 10:42:01] Initializing background task daemon...",
            "[DEBUG 10:42:02] Loading module: core.network.service...",
            "# [DEBUG 10:42:03] NovelRead IDE Pseudo Mode - RGB(51,51,51) (F12 切换模式, 右键打开电子书)",
            "[INFO 10:42:04] Worker thread pool started with 8 threads."
        ]
        self.editor.setText("\n".join(sample_log))

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return

        if not self.book or not self.book.chapters:
            return

        chap = self.book.get_current_chapter()

        output_logs = [
            f"[INFO {datetime.datetime.now().strftime('%H:%M:%S')}] Executing task: {self.book.title}.py",
            f"[DEBUG {datetime.datetime.now().strftime('%H:%M:%S')}] Active Chapter: [{chap.title}]",
            "--------------------------------------------------------------------------------"
        ]

        visible_lines = max(5, self.get_visible_lines_count() - 4)  # 留出 4 行作为伪装日志的头尾
        half_visible = visible_lines // 2
        start_idx = max(0, self.book.current_line_idx - half_visible)
        end_idx = min(len(self.lines), start_idx + visible_lines)

        now_str = datetime.datetime.now().strftime('%H:%M:%S')
        for i in range(start_idx, end_idx):
            # 保证前缀无论是 DEBUG 还是 FOCUS 聚焦行，长度一律精准保持为 20 个字符，防止文本缩进跳动
            prefix = f"# [DEBUG {now_str}] " if i != self.book.current_line_idx else f"> [DEBUG {now_str}] "
            output_logs.append(f"{prefix}{self.lines[i]}")

        output_logs.append("--------------------------------------------------------------------------------")
        auto_str = f" (AUTO-RUN {self.config_mgr.settings.get('auto_scroll_interval', 2.5)}s)" if self.is_auto_scrolling else ""
        output_logs.append(f"[INFO {datetime.datetime.now().strftime('%H:%M:%S')}] Status: OK{auto_str} | Chapter Progress: {self.book.current_chapter_idx + 1}/{self.book.total_chapters}")

        self.editor.setText("\n".join(output_logs))
