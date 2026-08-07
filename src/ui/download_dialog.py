import os
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar
)
from src.core.sonovel_client import SoNovelClient

class DownloadWorker(QThread):
    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, client: SoNovelClient, book_info: dict, save_dir: str):
        super().__init__()
        self.client = client
        self.book_info = book_info
        self.save_dir = save_dir

    def run(self):
        try:
            rule = self.book_info["rule"]
            book_url = self.book_info["url"]
            book_name = self.book_info["bookName"]
            author = self.book_info["author"]
            
            # 1. 获取目录
            self.progress_signal.emit(0, 0, "正在获取目录...")
            toc = self.client.get_toc(book_url, rule)
            if not toc:
                self.error_signal.emit("未解析到任何目录章节。")
                return

            total = len(toc)
            self.progress_signal.emit(0, total, f"找到 {total} 章，开始下载...")

            os.makedirs(self.save_dir, exist_ok=True)
            save_path = os.path.join(self.save_dir, f"{book_name}_{author}.txt")

            with open(save_path, "w", encoding="utf-8") as f:
                for idx, chap in enumerate(toc):
                    self.progress_signal.emit(idx + 1, total, f"下载中: {chap['title']}")
                    content = self.client.download_chapter(chap["url"], rule)
                    f.write(f"\n\n{chap['title']}\n\n{content}\n")

            self.finished_signal.emit(save_path)
        except Exception as e:
            self.error_signal.emit(f"下载发生异常: {str(e)}")


class DownloadDialog(QDialog):
    populate_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = SoNovelClient()
        self.setWindowTitle("🔍 搜索与下载小说 (SoNovel)")
        self.resize(750, 450)
        
        # 使用原生窗口装饰，这里不采用极简无边框
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.populate_signal.connect(self._populate_table)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 搜索区
        h_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入小说名或作者进行全网规则搜索...")
        self.search_input.returnPressed.connect(self.do_search)
        
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.do_search)
        
        h_layout.addWidget(self.search_input)
        h_layout.addWidget(self.search_btn)
        layout.addLayout(h_layout)

        # 结果表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书名", "作者", "最新章节", "书源"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # 进度区
        self.progress_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

        # 下载按钮
        self.download_btn = QPushButton("📥 下载选中的小说")
        self.download_btn.clicked.connect(self.do_download)
        layout.addWidget(self.download_btn)

        self.results = []

    def do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜索中...")
        self.table.setRowCount(0)
        self.results.clear()
        self.progress_label.setText("正在执行规则匹配与搜索，请稍候...")
        QMessageBox.information(self, "搜索提示", "即将遍历规则库进行搜索，此过程可能需要几秒到十几秒不等。")

        # 现实项目中建议放入 QThread，此处为精简展示主线程阻塞搜索
        import threading
        def _search_thread():
            try:
                res = self.client.search(keyword)
                self.results = res
                self.populate_signal.emit()
            except Exception as e:
                self.progress_label.setText(f"搜索出错: {e}")
            finally:
                self.search_btn.setEnabled(True)
                self.search_btn.setText("搜索")
        
        threading.Thread(target=_search_thread, daemon=True).start()

    def _populate_table(self):
        self.table.setRowCount(len(self.results))
        for row, item in enumerate(self.results):
            self.table.setItem(row, 0, QTableWidgetItem(item["bookName"]))
            self.table.setItem(row, 1, QTableWidgetItem(item["author"]))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("latestChapter", "")))
            self.table.setItem(row, 3, QTableWidgetItem(item["sourceName"]))
        self.progress_label.setText(f"搜索完成，共找到 {len(self.results)} 个结果。")

    def do_download(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选中一本小说。")
            return

        row = selected[0].row()
        book_info = self.results[row]

        save_dir = os.path.join(os.path.expanduser("~"), "NovelRead_Downloads")
        
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.worker = DownloadWorker(self.client, book_info, save_dir)
        self.worker.progress_signal.connect(self.on_download_progress)
        self.worker.finished_signal.connect(self.on_download_finished)
        self.worker.error_signal.connect(self.on_download_error)
        self.worker.start()

    def on_download_progress(self, current, total, text):
        self.progress_label.setText(text)
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def on_download_finished(self, save_path):
        self.progress_label.setText("下载完成！")
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        QMessageBox.information(self, "下载成功", f"小说已成功下载到：\n{save_path}\n\n你现在可以在阅读器中右键打开该文件了！")

    def on_download_error(self, err_msg):
        self.progress_label.setText(f"错误: {err_msg}")
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        QMessageBox.critical(self, "下载失败", err_msg)
