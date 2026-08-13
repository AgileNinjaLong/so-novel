from PyQt6.QtWidgets import QVBoxLayout, QLabel, QHeaderView, QTableWidgetItem
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTableWidget

class SysMonitorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "sys_monitor"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📊 Windows Resource Monitor - CPU: 12%  MEM: 42%")
        self.title_lbl.setStyleSheet("background-color: #2D2D30; color: #00E676; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "Process Name", "Thread Activity Trace", "CPU %"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                gridline-color: #333333;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #00E676;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.table.setRowCount(1)
            self.table.setItem(0, 2, QTableWidgetItem(error_msg))
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        display_lines = self.lines[start:end]

        self.table.setRowCount(len(display_lines))
        for i, line_text in enumerate(display_lines):
            self.table.setItem(i, 0, QTableWidgetItem(f"{4000+i}"))
            self.table.setItem(i, 1, QTableWidgetItem("svchost.exe"))
            self.table.setItem(i, 2, QTableWidgetItem(line_text))
            self.table.setItem(i, 3, QTableWidgetItem(f"{0.5+i*0.1:.1f}%"))
