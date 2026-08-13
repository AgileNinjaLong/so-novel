from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class DeepLTranslatePseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "deepl_translate"
        self.resize(760, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🌐 DeepL Translator - [English -> Chinese Simplified]")
        self.title_lbl.setStyleSheet("background-color: #0F2B46; color: #00B5E2; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #141C24; color: #E1E1E1; padding: 12px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))

        trans = ["【DeepL 实时智能翻译结果】\n"]
        for line in self.lines[start:end]:
            trans.append(f"ORIGINAL >> [Segment] {line}")
            trans.append(f"TRANSLATION >> {line}\n")
        self.editor.setText("\n".join(trans))
