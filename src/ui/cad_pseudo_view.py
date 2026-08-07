from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QFont, QWheelEvent, QKeyEvent
from src.ui.base_window import BaseStealthWindow

class CADCommandLineEdit(QTextEdit):
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
        self.parent_view.keyPressEvent(event)

class CADPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, parent=None):
        super().__init__(config_manager, parent)
        self.init_ui()

    def get_line_length(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self.editor.font())
        char_width = fm.horizontalAdvance("中")
        if char_width == 0:
            char_width = 12
        available_width = self.editor.viewport().width() - 20
        return max(20, available_width // char_width)

    def init_ui(self):
        self.resize(800, 160)
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(2, 2, 2, 2)

        # 纯黑 AutoCAD 命令行模式
        self.editor = CADCommandLineEdit(parent_view=self)
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setAcceptDrops(False)
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        
        # 背景全黑，文字亮灰
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #D4D4D4;
                border: 1px solid #333333;
                font-family: 'Consolas', 'Courier New', monospace;
                padding: 4px;
            }
        """)

        layout.addWidget(self.editor)
        self.setLayout(layout)
        
        sample_log = [
            "Command: _line",
            "Specify first point:",
            "Specify next point or [Undo]:",
            "Command: [AutoCAD CAD Mode Active - Right click to open file]",
        ]
        self.editor.setText("\n".join(sample_log))

    def get_visible_lines_count(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self.editor.font())
        line_height = fm.lineSpacing()
        if line_height == 0:
            line_height = 20
        available_height = self.editor.viewport().height()
        return max(5, available_height // line_height)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return

        if not self.book or not self.book.chapters:
            return

        chap = self.book.get_current_chapter()

        output_logs = [
            f"Command: _open",
            f"Loading {self.book.title}.dwg... done.",
            f"Command: _zoom All",
            f"Command: [Layer: {chap.title}]",
        ]

        visible_lines = max(5, self.get_visible_lines_count() - 5)
        half_visible = visible_lines // 2
        start_idx = max(0, self.book.current_line_idx - half_visible)
        end_idx = min(len(self.lines), start_idx + visible_lines)

        for i in range(start_idx, end_idx):
            if i == self.book.current_line_idx:
                output_logs.append(f"Command: {self.lines[i]}")
            else:
                output_logs.append(f"Specify next point: {self.lines[i]}")

        output_logs.append(f"Progress: {self.book.current_chapter_idx + 1}/{self.book.total_chapters}")

        self.editor.setText("\n".join(output_logs))
