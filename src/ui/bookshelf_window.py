import os
import sys
import time
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QFrame, QMenu, QHeaderView, QTableWidget, QTableWidgetItem
)
from PyQt6.QtGui import QColor, QFont, QIcon, QDragEnterEvent, QDropEvent
from src.core.config import ConfigManager
from src.ui.download_dialog import DownloadDialog
from src.ui.settings_dialog import SettingsDialog
from src.core.parser import NovelParser

class BookshelfWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.active_stealth_window = None
        
        self.setWindowTitle("📚 摸鱼阅读器 - 我的藏书与全网书城")
        self.resize(850, 560)
        self.setAcceptDrops(True)

        self.init_ui()
        self.refresh_bookshelf()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. 顶栏控制区域
        header_layout = QHBoxLayout()
        title_label = QLabel("📚 我的摸鱼书架")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e1e1e;")
        
        self.import_btn = QPushButton("📂 导入本地书籍")
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #1B5E20;
            }
        """)
        self.import_btn.clicked.connect(self.do_import_local_book)

        self.store_btn = QPushButton("🌐 全网书城 / 搜书下载")
        self.store_btn.setStyleSheet("""
            QPushButton {
                background-color: #0288D1;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #01579B;
            }
        """)
        self.store_btn.clicked.connect(self.do_open_bookstore)

        self.settings_btn = QPushButton("⚙️ 偏好设置")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #333333;
            }
        """)
        self.settings_btn.clicked.connect(self.do_open_settings)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.import_btn)
        header_layout.addWidget(self.store_btn)
        header_layout.addWidget(self.settings_btn)
        main_layout.addLayout(header_layout)

        # 提示 banner
        tip_label = QLabel("💡 提示：可直接拖拽电脑中的 .txt / .epub 小说文件放入下方列表入库。双击即可一键开启摸鱼隐蔽阅读！")
        tip_label.setStyleSheet("color: #666666; font-size: 12px; background-color: #F0F4F8; padding: 6px 10px; border-radius: 4px;")
        main_layout.addWidget(tip_label)

        # 2. 书籍列表表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["小说名称", "作者", "格式", "加入时间", "进度", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        main_layout.addWidget(self.table)

    def refresh_bookshelf(self):
        shelf = self.config_manager.get_bookshelf()
        self.table.setRowCount(0)
        
        # 按加入时间降序排列
        sorted_items = sorted(shelf.items(), key=lambda x: x[1].get("add_time", ""), reverse=True)
        
        for path, info in sorted_items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            title_item = QTableWidgetItem(info.get("title", "未知小说"))
            title_item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 0, title_item)
            
            self.table.setItem(row, 1, QTableWidgetItem(info.get("author", "未知")))
            
            fmt_str = info.get("format", "txt").upper()
            fmt_item = QTableWidgetItem(fmt_str)
            fmt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, fmt_item)
            
            self.table.setItem(row, 3, QTableWidgetItem(info.get("add_time", "-")))
            
            # 计算阅读进度
            hist = self.config_manager.history.get(path, {})
            c_idx = hist.get("chapter_idx", 0)
            prog_str = f"第 {c_idx + 1} 章" if c_idx > 0 else "未开始"
            prog_item = QTableWidgetItem(prog_str)
            prog_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, prog_item)

            # 操作控件容器
            btn_box = QWidget()
            btn_layout = QHBoxLayout(btn_box)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)
            
            read_btn = QPushButton("📖 摸鱼开读")
            read_btn.setStyleSheet("background-color: #2E7D32; color: white; border-radius: 3px; padding: 3px 8px; font-size: 11px;")
            read_btn.clicked.connect(lambda _, p=path: self.start_reading(p))
            
            remove_btn = QPushButton("🗑️ 移出")
            remove_btn.setStyleSheet("background-color: #C62828; color: white; border-radius: 3px; padding: 3px 8px; font-size: 11px;")
            remove_btn.clicked.connect(lambda _, p=path: self.remove_book(p))
            
            btn_layout.addWidget(read_btn)
            btn_layout.addWidget(remove_btn)
            self.table.setCellWidget(row, 5, btn_box)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        imported_count = 0
        for url in urls:
            file_path = url.toLocalFile()
            if os.path.exists(file_path) and (file_path.endswith('.txt') or file_path.endswith('.epub') or os.path.isdir(file_path)):
                self.config_manager.add_to_bookshelf(file_path)
                imported_count += 1
        if imported_count > 0:
            self.refresh_bookshelf()
            QMessageBox.information(self, "导入成功", f"已成功将 {imported_count} 本小说添加到您的摸鱼书架！")

    def do_import_local_book(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择本地小说文件导入书架", "", "Novel Files (*.txt *.epub);;All Files (*)")
        if files:
            for f in files:
                self.config_manager.add_to_bookshelf(f)
            self.refresh_bookshelf()
            QMessageBox.information(self, "导入成功", f"已成功导入 {len(files)} 本小说！")

    def do_open_bookstore(self):
        dlg = DownloadDialog(self)
        # 连接下载完成信号自动同步到书架
        dlg.exec()
        self.refresh_bookshelf()

    def do_open_settings(self):
        dlg = SettingsDialog(self.config_manager, self)
        dlg.exec()

    def on_item_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        title_item = self.table.item(row, 0)
        if title_item:
            path = title_item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.start_reading(path)

    def start_reading(self, file_path: str):
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "文件丢失", f"找不到小说文件，可能已被移动或删除：\n{file_path}")
            self.config_manager.remove_from_bookshelf(file_path)
            self.refresh_bookshelf()
            return

        # 保存为上次打开的文件
        self.config_manager.settings["last_file"] = file_path
        self.config_manager.save_immediately()

        mode = self.config_manager.settings.get("mode", "floating")
        
        # 隐藏书架窗口
        self.hide()

        # 根据配置唤醒摸鱼伪装模式
        if mode == "ide_pseudo":
            from src.ui.ide_pseudo_view import IdePseudoView
            self.active_stealth_window = IdePseudoView(self.config_manager, file_path=file_path, bookshelf_window=self)
        elif mode == "cad_pseudo":
            from src.ui.cad_pseudo_view import CadPseudoView
            self.active_stealth_window = CadPseudoView(self.config_manager, file_path=file_path, bookshelf_window=self)
        else:
            from src.ui.floating_view import FloatingView
            self.active_stealth_window = FloatingView(self.config_manager, file_path=file_path, bookshelf_window=self)

        self.active_stealth_window.show()

    def remove_book(self, file_path: str):
        self.config_manager.remove_from_bookshelf(file_path)
        self.refresh_bookshelf()
