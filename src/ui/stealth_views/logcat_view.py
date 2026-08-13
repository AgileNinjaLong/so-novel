import datetime
from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class LogcatPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "logcat_viewer"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📜 Server Log Stream - [tail -f /var/log/application.log]")
        self.title_lbl.setStyleSheet("background-color: #263238; color: #80D8FF; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #121212; color: #B0BEC5; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 13, len(self.lines))

        logs = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for line in self.lines[start:end]:
            logs.append(f"[{now_str}] [INFO] [Thread-Pool-1] {line}")
        self.editor.setText("\n".join(logs))
