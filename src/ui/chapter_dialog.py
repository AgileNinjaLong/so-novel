from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, 
    QListWidgetItem, QPushButton
)

class ChapterDialog(QDialog):
    def __init__(self, chapters, current_idx=0, parent=None):
        super().__init__(parent)
        self.chapters = chapters
        self.selected_index = current_idx
        self.setWindowTitle("章节目录")
        self.resize(420, 550)
        # 独立顶层窗口，防止受父窗口透明度及事件处理影响
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)

        # 防抖定时器
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._do_filter)

        self.init_ui(current_idx)

    def init_ui(self, current_idx):
        layout = QVBoxLayout(self)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索章节名称或数字...")
        self.search_input.textChanged.connect(self.on_search_changed)
        layout.addWidget(self.search_input)

        # 列表框 - 批量加载优化
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setUniformItemSizes(True)  # 关键优化：固定高度大幅提升大列表绘制速度

        self.list_widget.setUpdatesEnabled(False)
        for idx, chap in enumerate(self.chapters):
            item = QListWidgetItem(f"{idx + 1}. {chap.title}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_widget.addItem(item)
        self.list_widget.setUpdatesEnabled(True)

        # 选中并滚动定位到当前章节
        if 0 <= current_idx < len(self.chapters):
            self.list_widget.setCurrentRow(current_idx)
            item = self.list_widget.item(current_idx)
            if item:
                self.list_widget.scrollToItem(item)

        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # 按钮栏
        btn_layout = QHBoxLayout()
        confirm_btn = QPushButton("跳转")
        cancel_btn = QPushButton("取消")

        confirm_btn.clicked.connect(self.accept_selection)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(confirm_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # 样式定义
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLineEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #454545;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QListWidget {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 5px 8px;
            }
            QListWidget::item:selected {
                background-color: #043927;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #2a2d2e;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def on_search_changed(self):
        self.search_timer.start(150)  # 150ms 防抖

    def _do_filter(self):
        text = self.search_input.text().strip().lower()
        self.list_widget.setUpdatesEnabled(False)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(bool(text and text not in item.text().lower()))
        self.list_widget.setUpdatesEnabled(True)

    def on_item_double_clicked(self, item):
        val = item.data(Qt.ItemDataRole.UserRole)
        if val is not None:
            self.selected_index = int(val)
            self.accept()

    def accept_selection(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            val = current_item.data(Qt.ItemDataRole.UserRole)
            if val is not None:
                self.selected_index = int(val)
                self.accept()
                return
        self.reject()
