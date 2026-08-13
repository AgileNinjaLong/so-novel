from PyQt6.QtWidgets import QVBoxLayout, QLabel, QHeaderView, QTableWidgetItem
from PyQt6.QtGui import QColor
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTableWidget

class DBDBeaverPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "database_dbeaver"
        self.resize(750, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🗄️ DBeaver Enterprise - [Script-1.sql @ production_db]")
        self.title_lbl.setStyleSheet("background-color: #37474F; color: #80CBC4; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["id", "sql_query_statement", "execution_result_text"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                gridline-color: #2D2D2D;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #263238;
                color: #80CBC4;
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
            self.table.setItem(i, 0, QTableWidgetItem(f"{start+i+1}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"SELECT * FROM tbl_{start+i}"))
            
            val_item = QTableWidgetItem(line_text)
            val_item.setForeground(QColor("#CE9178"))
            self.table.setItem(i, 2, val_item)
