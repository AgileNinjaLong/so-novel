from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class JSONValidatorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "json_validator"
        self.resize(720, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🔍 JSON Online Validator - Status: Valid JSON")
        self.title_lbl.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1E1E1E; color: #CE9178; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        
        json_lines = ['{', '  "status": 200,', '  "message": "success",', '  "payload": {']
        for line in self.lines[start:end]:
            json_lines.append(f'    "item_{len(json_lines)}": "{line}",')
        json_lines.append("  }")
        json_lines.append("}")
        self.editor.setText("\n".join(json_lines))
