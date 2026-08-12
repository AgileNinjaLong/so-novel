import os
import sys
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar, QLabel, QFileDialog
)
from src.core.sonovel_client import SoNovelClient

class SearchWorker(QObject):
    item_found_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, client: SoNovelClient, keyword: str):
        super().__init__()
        self.client = client
        self.keyword = keyword
        import threading
        self.cancel_event = threading.Event()

    def start(self):
        import threading
        threading.Thread(target=self.run, daemon=True).start()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            def on_item(item):
                try:
                    self.item_found_signal.emit(item)
                except RuntimeError:
                    pass

            def on_status(msg):
                try:
                    self.status_signal.emit(msg)
                except RuntimeError:
                    pass
            
            res = self.client.search(
                self.keyword, 
                callback=on_item, 
                status_callback=on_status, 
                cancel_event=self.cancel_event
            )
            try:
                self.finished_signal.emit(res)
            except RuntimeError:
                pass
        except Exception as e:
            try:
                self.error_signal.emit(str(e))
            except RuntimeError:
                pass

class DownloadWorker(QObject):
    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, client: SoNovelClient, book_info: dict, save_path: str, export_mode: str = "txt"):
        super().__init__()
        self.client = client
        self.book_info = book_info
        self.save_path = save_path
        self.export_mode = export_mode  # 'txt', 'epub', 'dir'

    def start(self):
        import threading
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            rule = self.book_info["rule"]
            book_url = self.book_info["url"]
            book_name = self.book_info.get("bookName", "未知书名")
            author = self.book_info.get("author", "未知作者")
            
            # 1. 获取目录
            self.progress_signal.emit(0, 0, "正在获取目录...")
            toc = self.client.get_toc(book_url, rule)
            if not toc:
                self.error_signal.emit("未解析到任何目录章节。")
                return

            total = len(toc)
            self.progress_signal.emit(0, total, f"找到 {total} 章，准备极速下载...")

            os.makedirs(os.path.dirname(os.path.abspath(self.save_path)), exist_ok=True)

            import concurrent.futures
            chapter_contents = [None] * total
            completed = 0

            def _download_task(i, chap):
                try:
                    return i, self.client.download_chapter(chap["url"], rule)
                except Exception as e:
                    return i, f"下载失败: {e}"

            # 使用高并发加快下载速度
            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                futures = {executor.submit(_download_task, i, chap): i for i, chap in enumerate(toc)}
                for future in concurrent.futures.as_completed(futures):
                    i, content = future.result()
                    chapter_contents[i] = content
                    completed += 1
                    
                    if completed % 10 == 0 or completed == total:
                        self.progress_signal.emit(completed, total, f"极速下载中: {completed}/{total} 章")

            # 针对少量因网络抖动或代理限制下载失败的章节，进行二次串行精准补下载
            failed_indices = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c]
            if failed_indices:
                self.progress_signal.emit(total, total, f"检测到 {len(failed_indices)} 章超时，正在自动重试补全...")
                for idx in failed_indices:
                    chap = toc[idx]
                    try:
                        res = self.client.download_chapter(chap["url"], rule)
                        if "下载失败" not in res and "解析失败" not in res:
                            chapter_contents[idx] = res
                    except Exception:
                        pass

            self.progress_signal.emit(total, total, "下载完毕，正在按所选模式合成落盘...")

            # 2. 根据所选 export_mode 进行多样化合成落盘
            if self.export_mode == "epub":
                from src.core.epub_builder import EpubBuilder
                chapters_data = [
                    {"title": chap["title"], "content": chapter_contents[idx] or ""}
                    for idx, chap in enumerate(toc)
                ]
                EpubBuilder.build_epub(book_name, author, chapters_data, self.save_path)
            elif self.export_mode == "dir":
                target_dir = self.save_path
                os.makedirs(target_dir, exist_ok=True)
                for idx, chap in enumerate(toc):
                    safe_chap_title = re.sub(r'[\\/:*?"<>|]', '_', chap['title'])
                    chap_file_path = os.path.join(target_dir, f"{idx+1:04d}_{safe_chap_title}.txt")
                    with open(chap_file_path, "w", encoding="utf-8") as f:
                        f.write(f"{chap['title']}\n\n{chapter_contents[idx] or ''}\n")
            else: # txt
                with open(self.save_path, "w", encoding="utf-8") as f:
                    for idx, chap in enumerate(toc):
                        f.write(f"\n\n{chap['title']}\n\n{chapter_contents[idx] or ''}\n")

            self.finished_signal.emit(self.save_path)
        except Exception as e:
            self.error_signal.emit(f"下载合并发生异常: {str(e)}")


class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = SoNovelClient()
        self.setWindowTitle("🔍 搜索与下载小说 (SoNovel)")
        self.resize(800, 500)
        
        # 使用原生窗口装饰，这里不采用极简无边框
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

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

        # 底部操作控制区
        bottom_layout = QHBoxLayout()
        from PyQt6.QtWidgets import QComboBox
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("📄 单文件 TXT (合并文本)", "txt")
        self.mode_combo.addItem("📚 EPUB 电子书 (标准打包)", "epub")
        self.mode_combo.addItem("📂 按章节拆分目录 (离散文件)", "dir")
        
        self.download_btn = QPushButton("📥 下载选中的小说")
        self.download_btn.clicked.connect(self.do_download)
        
        bottom_layout.addWidget(QLabel("合成模式:"))
        bottom_layout.addWidget(self.mode_combo)
        bottom_layout.addWidget(self.download_btn)
        layout.addLayout(bottom_layout)

        self.results = []

    def do_search(self):
        if getattr(self, 'is_searching', False):
            self.cancel_search()
            return

        keyword = self.search_input.text().strip()
        if not keyword:
            return

        self.is_searching = True
        self.search_btn.setText("取消")
        self.search_btn.setEnabled(True)
        self.table.setRowCount(0)
        self.results.clear()
        self.progress_label.setText("正在连接书源并测试连通性...")
        
        self.search_worker = SearchWorker(self.client, keyword)
        self.search_worker.item_found_signal.connect(self.on_item_found)
        self.search_worker.status_signal.connect(self.on_search_status)
        self.search_worker.finished_signal.connect(self.on_search_finished)
        self.search_worker.error_signal.connect(self.on_search_error)
        self.search_worker.start()

    def cancel_search(self):
        if hasattr(self, 'search_worker') and self.search_worker:
            self.search_worker.cancel()
            self.progress_label.setText("正在强行打断连接，请稍候...")
            self.search_btn.setEnabled(False)

    def on_item_found(self, item):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(item.get("bookName", "未知")))
        self.table.setItem(row, 1, QTableWidgetItem(item.get("author", "未知")))
        self.table.setItem(row, 2, QTableWidgetItem(item.get("latestChapter", "")))
        self.table.setItem(row, 3, QTableWidgetItem(item.get("sourceName", "未知")))
        
        self.results.append(item)
        self.progress_label.setText(f"搜索流式输出中... 已发现 {len(self.results)} 个结果")

    def on_search_status(self, msg):
        self.progress_label.setText(msg)

    def on_search_finished(self, sorted_results):
        self.is_searching = False
        self.results = sorted_results
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.results))
        for row, item in enumerate(self.results):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("bookName", "未知")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("author", "未知")))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("latestChapter", "")))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("sourceName", "未知")))
            
        if self.search_worker and self.search_worker.cancel_event.is_set():
            self.progress_label.setText("搜索已由用户手动取消。")
        else:
            self.progress_label.setText(f"搜索完成，共找到 {len(self.results)} 个可用结果。")
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")

    def on_search_error(self, err_msg):
        self.is_searching = False
        self.progress_label.setText(f"搜索出错: {err_msg}")
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")

    def do_download(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选中一本小说。")
            return

        row = selected[0].row()
        book_info = self.results[row]
        export_mode = self.mode_combo.currentData() or "txt"

        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        default_download_dir = os.path.join(app_dir, "download")
        os.makedirs(default_download_dir, exist_ok=True)

        if export_mode == "epub":
            filter_str = "EPUB Files (*.epub);;All Files (*)"
            default_filename = f"{book_info.get('bookName', '未知')}_{book_info.get('author', '未知')}.epub"
            default_save_path = os.path.join(default_download_dir, default_filename)
            save_path, _ = QFileDialog.getSaveFileName(self, "选择 EPUB 保存路径", default_save_path, filter_str)
        elif export_mode == "dir":
            default_filename = f"{book_info.get('bookName', '未知')}_{book_info.get('author', '未知')}"
            default_save_path = os.path.join(default_download_dir, default_filename)
            save_path = QFileDialog.getExistingDirectory(self, "选择保存文件夹目录", default_save_path)
        else:
            filter_str = "Text Files (*.txt);;All Files (*)"
            default_filename = f"{book_info.get('bookName', '未知')}_{book_info.get('author', '未知')}.txt"
            default_save_path = os.path.join(default_download_dir, default_filename)
            save_path, _ = QFileDialog.getSaveFileName(self, "选择 TXT 保存路径", default_save_path, filter_str)

        if not save_path:
            return  # 用户取消

        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.download_worker = DownloadWorker(self.client, book_info, save_path, export_mode=export_mode)
        self.download_worker.progress_signal.connect(self.on_download_progress)
        self.download_worker.finished_signal.connect(self.on_download_finished)
        self.download_worker.error_signal.connect(self.on_download_error)
        self.download_worker.start()

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
