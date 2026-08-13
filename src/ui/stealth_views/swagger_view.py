from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class SwaggerPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "swagger_api"
        self.resize(750, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🔌 Swagger UI - RESTful API Specification v2.4")
        self.title_lbl.setStyleSheet("background-color: #89BF04; color: black; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1E1E1E; color: #B5CEA8; padding: 8px;")
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

        api_payload = [
            f"GET /api/v1/{self.book.title}/chapter/{self.book.current_chapter_idx + 1}",
            "Host: api.company.internal",
            "Accept: application/json",
            "HTTP/1.1 200 OK",
            "{",
            f'  "code": 200,',
            f'  "chapter_name": "{chap.title if chap else ""}",',
            '  "data": ['
        ]
        for line in self.lines[start:end]:
            api_payload.append(f'    "{line}",')
        api_payload.append("  ]")
        api_payload.append("}")
        self.editor.setText("\n".join(api_payload))
