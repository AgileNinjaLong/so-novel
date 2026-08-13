from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class TerminalPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "terminal_cli"
        self.resize(720, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🖥️ Administrator: Windows PowerShell")
        self.title_lbl.setStyleSheet("background-color: #012456; color: white; font-weight: bold; font-size: 11px; padding: 3px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #012456; color: #CCCCCC; border: none; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(f"PS C:\\System32> {error_msg}")
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 14, len(self.lines))

        logs = [
            "Windows PowerShell",
            "Copyright (C) Microsoft Corporation. All rights reserved.",
            "",
            f"PS C:\\Users\\Admin\\Projects\\{self.book.title}> Get-Content -Path .\\chapter_{self.book.current_chapter_idx + 1}.log"
        ]
        for line in self.lines[start:end]:
            logs.append(f"LOG >> {line}")

        logs.append(f"PS C:\\Users\\Admin\\Projects\\{self.book.title}> _")
        self.editor.setText("\n".join(logs))
