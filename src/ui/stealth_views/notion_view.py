from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class NotionPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "notion_markdown"
        self.resize(720, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📓 Notion Workspace - [项目架构设计与需求拆解]")
        self.title_lbl.setStyleSheet("background-color: #2F3437; color: #E3E3E3; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #191919; color: #D3D3D3; padding: 12px; line-height: 1.6;")
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

        note_lines = [
            f"# {self.book.title} - {chap.title if chap else ''}",
            "## 📌 需求描述与架构拆解",
            "- [x] 完成架构复核",
            "- [ ] 推进单元测试覆盖率\n",
            "> " + "\n> ".join(self.lines[start:end])
        ]
        self.editor.setText("\n".join(note_lines))
