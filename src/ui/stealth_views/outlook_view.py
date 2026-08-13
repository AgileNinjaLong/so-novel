import datetime
from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class OutlookPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "outlook_email"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  ✉️ Outlook - [RE: 关于本周工作进展与季度规划报告的讨论]")
        self.title_lbl.setStyleSheet("background-color: #0072C6; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Segoe UI", 10))
        self.editor.setStyleSheet("background-color: #1F1F1F; color: #D4D4D4; padding: 10px;")
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
        text = "\n".join(self.lines[start:end])

        mail_content = [
            f"发件人: manager@company.com",
            f"收件人: team@company.com",
            f"主题: RE: [{self.book.title}] {chap.title if chap else ''} 工作进展讨论",
            f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "----------------------------------------------------------------------",
            "各位同事：\n",
            text,
            "\n祝好，\n项目管理组"
        ]
        self.editor.setText("\n".join(mail_content))
