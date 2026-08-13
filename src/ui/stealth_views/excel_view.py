from PyQt6.QtWidgets import QVBoxLayout, QLabel, QHeaderView, QTableWidgetItem
from PyQt6.QtGui import QColor
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTableWidget

class ExcelPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "excel_sheet"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.header_lbl = QLabel("  📊 Microsoft Excel - [Data_Analysis_Report_2026.xlsx]   fx =SUM(C2:C100)")
        self.header_lbl.setStyleSheet("background-color: #107C41; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.header_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Row_ID", "Cell_Formula", "Data_Content", "Status_Flag"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                gridline-color: #333333;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #107C41;
                font-weight: bold;
                border: 1px solid #333333;
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

        chap = self.book.get_current_chapter()
        title_str = chap.title if chap else "Sheet1"
        self.header_lbl.setText(f"  📊 Microsoft Excel - [{self.book.title}.xlsx] - Sheet: {title_str}   fx =CELL(\"contents\")")

        start = self.book.current_line_idx
        end = min(start + 15, len(self.lines))
        display_lines = self.lines[start:end]

        self.table.setRowCount(len(display_lines))
        for i, line_text in enumerate(display_lines):
            row_num = start + i + 1
            self.table.setItem(i, 0, QTableWidgetItem(f"R_{row_num:03d}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"=VAL(\"C{row_num}\")"))
            
            val_item = QTableWidgetItem(line_text)
            val_item.setForeground(QColor("#9CDCFE"))
            self.table.setItem(i, 2, val_item)
            self.table.setItem(i, 3, QTableWidgetItem("CALCULATED"))
