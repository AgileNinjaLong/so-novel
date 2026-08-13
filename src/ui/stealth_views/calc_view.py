from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTextEdit

class CalculatorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "calculator_gui"
        self.resize(650, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🧮 Financial Calculator v3.1")
        self.title_lbl.setStyleSheet("background-color: #4A4A4A; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1C1C1C; color: #00E676; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))
        
        calc_history = []
        for i, line in enumerate(self.lines[start:end]):
            calc_history.append(f"CALC [{i+1:02d}] >> 1500 * 1.05 = {1575+i*10}")
            calc_history.append(f"OUTPUT >> {line}\n")
        self.editor.setText("\n".join(calc_history))
