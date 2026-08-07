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
        return 65

    def init_ui(self):
        self.resize(800, 260)
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(2, 2, 2, 2)

        # 模拟 AutoCAD 的背景画布
        self.canvas = QFrame()
        self.canvas.setStyleSheet("""
            QFrame {
                background-color: #212830;
                border: 1px solid #333333;
                border-bottom: none;
            }
        """)
        # 简单在画布上加一些虚构的坐标轴或提示线
        canvas_layout = QVBoxLayout()
        canvas_label = QLabel("AutoCAD 2026 - [Drawing1.dwg]")
        canvas_label.setStyleSheet("color: #4B5A69; font-size: 14px; padding: 10px;")
        canvas_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        canvas_layout.addWidget(canvas_label)
        canvas_layout.addStretch()
        self.canvas.setLayout(canvas_layout)
        
        layout.addWidget(self.canvas, stretch=1)

        # 模拟 AutoCAD 底部的命令行
        self.editor = CADCommandLineEdit(parent_view=self)
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setAcceptDrops(False)
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.editor.setFixedHeight(110)
        
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #999999;
                font-family: 'Consolas', 'Courier New', monospace;
                padding: 4px;
            }
        """)

        layout.addWidget(self.editor, stretch=0)
        self.setLayout(layout)
        
        sample_log = [
            "Command: _line",
            "Specify first point:",
            "Specify next point or [Undo]:",
            "Command: [AutoCAD CAD Mode Active - Right click to open file]",
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
            f"Command: _open",
            f"Loading {self.book.title}.dwg... done.",
            f"Command: _zoom All",
            f"Command: [Layer: {chap.title}]",
        ]

        start_idx = max(0, self.book.current_line_idx - 2)
        end_idx = min(len(self.lines), start_idx + 6)

        for i in range(start_idx, end_idx):
            if i == self.book.current_line_idx:
                output_logs.append(f"Command: {self.lines[i]}")
            else:
                output_logs.append(f"Specify next point: {self.lines[i]}")

        output_logs.append(f"Progress: {self.book.current_chapter_idx + 1}/{self.book.total_chapters}")

        self.editor.setText("\n".join(output_logs))
