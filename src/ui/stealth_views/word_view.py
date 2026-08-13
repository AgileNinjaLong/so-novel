from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class WordPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "word_doc"
        self.resize(700, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📄 Microsoft Word - [工作总结与季度规划草稿.docx]")
        self.title_lbl.setStyleSheet("background-color: #2B579A; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E24;
                color: #E0E0E0;
                border: 1px solid #2B579A;
                padding: 10px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        self.title_lbl.setText(f"  📄 Word - [{self.book.title}.docx] - {chap.title if chap else ''}")

        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        display_text = "\n".join(self.lines[start:end])
        self.editor.setText(f"【工作汇报与可行性方案】\n\n{display_text}")
