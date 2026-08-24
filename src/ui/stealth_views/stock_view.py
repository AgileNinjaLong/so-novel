from PyQt6.QtWidgets import QVBoxLayout, QLabel, QHeaderView, QTableWidgetItem
from PyQt6.QtGui import QColor
from src.ui.base_window import BaseStealthWindow
from src.ui.stealth_views.common import ForwardTableWidget

class StockKlinePseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "stock_kline"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📈 同花顺金融终端 - [上证指数 3345.12 +1.25% 成交量 4500 亿]")
        self.title_lbl.setStyleSheet("background-color: #C62828; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["代码/时间", "开盘/收盘", "行情研报/分析文本", "涨跌幅"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #121212;
                color: #00E676;
                gridline-color: #222222;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #1E1E1E;
                color: #FF5252;
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
        f_color = self.config_mgr.get_mode_style(self.mode_name, "font_color", "")

        for i, line_text in enumerate(display_lines):
            t_str = f"600{start+i:03d}"
            self.table.setItem(i, 0, QTableWidgetItem(t_str))
            self.table.setItem(i, 1, QTableWidgetItem(f"32.{i:02d} / 33.{i:02d}"))

            val_item = QTableWidgetItem(line_text)
            actual_color = f_color if f_color else ("#FF5252" if i % 2 == 0 else "#00E676")
            val_item.setForeground(QColor(actual_color))
            self.table.setItem(i, 2, val_item)
            self.table.setItem(i, 3, QTableWidgetItem(f"+{1.2 + i*0.1:.2f}%"))
