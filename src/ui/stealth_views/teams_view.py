import datetime
from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class ChatTeamsPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "chat_teams"
        self.resize(720, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  💬 Microsoft Teams - [项目开发与需求同步群]")
        self.title_lbl.setStyleSheet("background-color: #464775; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #1F1F1F; color: #D4D4D4; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))

        chats = [f"--- 消息历史 ({datetime.datetime.now().strftime('%H:%M')}) ---"]
        for i, line in enumerate(self.lines[start:end]):
            user = "项目经理" if i % 2 == 0 else "技术架构师"
            chats.append(f"[{user}]: {line}")
        self.editor.setText("\n".join(chats))
