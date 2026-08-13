from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class PDFReaderPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "pdf_reader"
        self.resize(750, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📑 Adobe Acrobat Reader - [IEEE_Research_Paper_2026.pdf]")
        self.title_lbl.setStyleSheet("background-color: #DC382D; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Times New Roman", 10))
        self.editor.setStyleSheet("background-color: #222222; color: #E0E0E0; padding: 12px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))

        pdf_text = [
            f"Abstract — Research on {self.book.title} ({chap.title if chap else ''})\n",
            "1. INTRODUCTION\n",
            "\n".join(self.lines[start:end]),
            f"\n--- Page {self.book.current_chapter_idx + 1} of {len(self.book.chapters)} ---"
        ]
        self.editor.setText("\n".join(pdf_text))
