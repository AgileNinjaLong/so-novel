from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class GitDiffPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "git_diff"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🔀 Git Commit Diff - commit [a8f93e2]")
        self.title_lbl.setStyleSheet("background-color: #F05032; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #181818; color: #CCCCCC; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 13, len(self.lines))

        diff_logs = [
            f"diff --git a/src/{self.book.title}.py b/src/{self.book.title}.py",
            "index 7f83a21..b912e45 100644",
            f"--- a/src/{self.book.title}.py",
            f"+++ b/src/{self.book.title}.py",
            f"@@ -{start+1},12 +{start+1},14 @@ {chap.title if chap else ''}"
        ]
        for idx, line in enumerate(self.lines[start:end]):
            prefix = "+" if idx % 2 == 0 else " "
            diff_logs.append(f"{prefix} {line}")

        self.editor.setText("\n".join(diff_logs))
