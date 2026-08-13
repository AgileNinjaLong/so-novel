from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class JupyterPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "jupyter_notebook"
        self.resize(750, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🪐 Jupyter Notebook - [data_analysis_v2.ipynb] (PyTorch 2.1)")
        self.title_lbl.setStyleSheet("background-color: #F37626; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #191919; color: #D4D4D4; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))

        cells = []
        for i, line in enumerate(self.lines[start:end]):
            cells.append(f"In [{i+1}]: df.loc[{i}, 'summary_text']")
            cells.append(f"Out[{i}]: '{line}'\n")
        self.editor.setText("\n".join(cells))
