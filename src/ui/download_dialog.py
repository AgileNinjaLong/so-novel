import os
import sys
import re
import time
import threading
import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar, QLabel, QFileDialog, QTabWidget, QWidget
)
from src.core.sonovel_client import SoNovelClient

class SearchWorker(QObject):
    item_found_signal = pyqtSignal(dict)
    rule_tested_signal = pyqtSignal(int, str, bool, int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, client: SoNovelClient, keyword: str):
        super().__init__()
        self.client = client
        self.keyword = keyword
        self.cancel_event = threading.Event()

    def start(self):
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

            def on_rule_tested(r_idx, r_name, is_ok, latency_ms):
                try:
                    self.rule_tested_signal.emit(r_idx, r_name, is_ok, latency_ms)
                except RuntimeError:
                    pass
            
            res = self.client.search(
                self.keyword, 
                callback=on_item, 
                status_callback=on_status, 
                cancel_event=self.cancel_event,
                rule_tested_callback=on_rule_tested
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
    progress_signal = pyqtSignal(str, int, int, str)
    finished_signal = pyqtSignal(str, str)
    error_signal = pyqtSignal(str, str)
    cancelled_signal = pyqtSignal(str)

    def __init__(self, client: SoNovelClient, task_id: str, book_info: dict, save_path: str, export_mode: str = "txt"):
        super().__init__()
        self.client = client
        self.task_id = task_id
        self.book_info = book_info
        self.save_path = save_path
        self.export_mode = export_mode  # 'txt', 'epub', 'dir'
        self.cancel_event = threading.Event()
        
        # 独立专属 requests.Session 与 50 槽位连接池，防止搜书时槽位卡死
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.session.headers.update(self.client.headers)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            rule = self.book_info["rule"]
            book_url = self.book_info["url"]
            book_name = self.book_info.get("bookName", "未知书名")
            author = self.book_info.get("author", "未知作者")
            
            # 1. 获取目录
            self.progress_signal.emit(self.task_id, 0, 0, "正在解析图书目录...")
            toc = self.client.get_toc(book_url, rule)
            if not toc:
                self.error_signal.emit(self.task_id, "未解析到任何目录章节。")
                return

            if self.cancel_event.is_set():
                self.cancelled_signal.emit(self.task_id)
                return

            total = len(toc)
            self.progress_signal.emit(self.task_id, 0, total, f"找到 {total} 章，准备高并发下载...")

            os.makedirs(os.path.dirname(os.path.abspath(self.save_path)), exist_ok=True)

            import concurrent.futures
            chapter_contents = [None] * total
            completed = 0

            def _download_task(i, chap):
                if self.cancel_event.is_set():
                    return i, None
                try:
                    # 使用独立 session 进行抓取
                    content = self.download_chapter_isolated(chap["url"], rule)
                    return i, content
                except Exception as e:
                    return i, f"下载失败: {e}"

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=30)
            try:
                futures = {executor.submit(_download_task, i, chap): i for i, chap in enumerate(toc)}
                for future in concurrent.futures.as_completed(futures):
                    if self.cancel_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        self.cancelled_signal.emit(self.task_id)
                        return
                    try:
                        i, content = future.result()
                        chapter_contents[i] = content
                        completed += 1
                        
                        if completed % 5 == 0 or completed == total:
                            self.progress_signal.emit(self.task_id, completed, total, f"极速下载中: {completed}/{total} 章")
                    except Exception:
                        pass
            finally:
                if not self.cancel_event.is_set():
                    executor.shutdown(wait=False)

            if self.cancel_event.is_set():
                self.cancelled_signal.emit(self.task_id)
                return

            # 补漏下载
            failed_indices = [i for i, c in enumerate(chapter_contents) if not c or "下载失败" in c or "解析失败" in c]
            if failed_indices and not self.cancel_event.is_set():
                self.progress_signal.emit(self.task_id, total, total, f"正在精准补全 {len(failed_indices)} 个卡顿章节...")
                for idx in failed_indices:
                    if self.cancel_event.is_set():
                        self.cancelled_signal.emit(self.task_id)
                        return
                    chap = toc[idx]
                    try:
                        res = self.download_chapter_isolated(chap["url"], rule)
                        if "下载失败" not in res and "解析失败" not in res:
                            chapter_contents[idx] = res
                    except Exception:
                        pass

            self.progress_signal.emit(self.task_id, total, total, "下载完毕，正在按格式合成落盘...")

            # 2. 合成落盘
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

            self.finished_signal.emit(self.task_id, self.save_path)
        except Exception as e:
            self.error_signal.emit(self.task_id, f"下载合并发生异常: {str(e)}")

    def download_chapter_isolated(self, chapter_url: str, rule: dict) -> str:
        """使用独享物理 Session 抓取章节纯文本"""
        chap_rule = rule.get("chapter", {})
        content_parts = []
        current_url = chapter_url
        visited = set()

        while current_url and current_url not in visited:
            if self.cancel_event.is_set():
                break
            visited.add(current_url)
            resp = None
            for attempt in range(3):
                if self.cancel_event.is_set():
                    break
                try:
                    resp = self.session.get(current_url, timeout=12)
                    if resp.status_code == 200:
                        break
                except Exception:
                    if attempt < 2:
                        time.sleep(0.3)

            if not resp or resp.status_code != 200:
                return "(本章下载失败)"

            try:
                if resp.encoding.lower() in ['iso-8859-1', 'us-ascii']:
                    resp.encoding = resp.apparent_encoding
                
                tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))
                
                filter_tags = [t.strip() for t in chap_rule.get("filterTag", "").split(',') if t.strip()]
                for tag in filter_tags:
                    for match in self.client._select_elements(tree, tag):
                        match.drop_tree()
                
                content_rule = chap_rule.get("content", "")
                js_code = ""
                if '@js:' in content_rule:
                    content_rule, js_code = content_rule.split('@js:', 1)

                content_nodes = self.client._select_elements(tree, content_rule)
                if not content_nodes:
                    break
                    
                node = content_nodes[0]
                
                if js_code:
                    raw_inner_html = html.tostring(node, encoding='unicode', method='html')
                    processed_html = self.client._apply_js(raw_inner_html, js_code)
                    node = html.fromstring(processed_html)
                
                for br in node.xpath(".//br"):
                    br.tail = "\n" + (br.tail or "")
                for p in node.xpath(".//p"):
                    p.tail = "\n" + (p.tail or "")
                    
                text = node.text_content()
                filter_txt = chap_rule.get("filterTxt", "")
                if filter_txt:
                    text = re.sub(filter_txt, '', text)
                    
                content_parts.append("\n".join([line.strip() for line in text.splitlines() if line.strip()]))
                break
            except Exception:
                return "(本章解析失败)"
                
        return "\n".join(content_parts) if content_parts else "(本章暂无内容)"


class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = SoNovelClient()
        self.setWindowTitle("🌐 全网书城与多任务下载中心")
        self.resize(850, 530)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.tasks = {}  # task_id -> {worker, row, save_path, title, author, mode}
        self.results = []
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 选项卡控件
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # ====== 切页 1: 🔍 全网搜书 =====
        search_tab = QWidget()
        search_layout = QVBoxLayout(search_tab)
        
        # 搜索框区
        h_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入小说名或作者进行 24 书源高并发搜索...")
        self.search_input.returnPressed.connect(self.do_search)
        
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.do_search)
        
        h_layout.addWidget(self.search_input)
        h_layout.addWidget(self.search_btn)
        search_layout.addLayout(h_layout)

        # 结果/连通性表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书名", "作者", "最新章节", "书源"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        search_layout.addWidget(self.table)

        # 搜索状态与下载控制区
        self.progress_label = QLabel("")
        search_layout.addWidget(self.progress_label)

        bottom_layout = QHBoxLayout()
        from PyQt6.QtWidgets import QComboBox
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("📄 单文件 TXT (合并文本)", "txt")
        self.mode_combo.addItem("📚 EPUB 电子书 (标准打包)", "epub")
        self.mode_combo.addItem("📂 按章节拆分目录 (离散文件)", "dir")
        
        self.download_btn = QPushButton("📥 下载选中的小说 (添加任务)")
        self.download_btn.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.download_btn.clicked.connect(self.do_download)
        
        bottom_layout.addWidget(QLabel("合成格式:"))
        bottom_layout.addWidget(self.mode_combo)
        bottom_layout.addWidget(self.download_btn)
        search_layout.addLayout(bottom_layout)

        self.tabs.addTab(search_tab, "🔍 全网搜书")

        # ====== 切页 2: 📥 下载任务与进度 =====
        task_tab = QWidget()
        task_layout = QVBoxLayout(task_tab)

        self.task_table = QTableWidget()
        self.task_table.setColumnCount(5)
        self.task_table.setHorizontalHeaderLabels(["小说名称", "格式", "进度条", "状态说明", "操作"])
        self.task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.task_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        task_layout.addWidget(self.task_table)

        self.tabs.addTab(task_tab, "📥 下载任务与书架 (0)")

    def setup_connectivity_view(self):
        self.table_view_mode = "connectivity"
        self.table.setRowCount(0)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书源名称", "连通状态", "响应延迟", "规则位次"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        
        self.rule_test_states = {}
        for idx, rule in enumerate(self.client.rules):
            r_idx = rule.get('rule_index', idx)
            r_name = rule.get("name", "未知书源")
            self.rule_test_states[r_idx] = {
                "name": r_name,
                "rule_index": r_idx,
                "is_ok": False,
                "is_tested": False,
                "latency_ms": 999999,
                "latency_str": "-"
            }
        self.refresh_connectivity_table()

    def on_rule_tested(self, r_idx, r_name, is_ok, latency_ms):
        if getattr(self, 'table_view_mode', '') != "connectivity":
            return
        if r_idx in self.rule_test_states:
            st = self.rule_test_states[r_idx]
            st["is_tested"] = True
            st["is_ok"] = is_ok
            st["latency_ms"] = latency_ms if is_ok else 999999
            st["latency_str"] = f"{latency_ms} ms" if is_ok else "超时"
        self.refresh_connectivity_table()

    def refresh_connectivity_table(self):
        if getattr(self, 'table_view_mode', '') != "connectivity":
            return

        sorted_states = list(self.rule_test_states.values())
        def sort_key(st):
            if st["is_ok"]: priority = 0
            elif st["is_tested"]: priority = 1
            else: priority = 2
            return (priority, st["latency_ms"], st["rule_index"])

        sorted_states.sort(key=sort_key)
        from PyQt6.QtGui import QColor
        self.table.setRowCount(len(sorted_states))
        for row, st in enumerate(sorted_states):
            self.table.setItem(row, 0, QTableWidgetItem(st["name"]))
            if st["is_ok"]:
                status_item = QTableWidgetItem("✅ 连通成功")
                status_item.setForeground(QColor("#2E7D32"))
            elif st["is_tested"]:
                status_item = QTableWidgetItem("❌ 超时/不可用")
                status_item.setForeground(QColor("#C62828"))
            else:
                status_item = QTableWidgetItem("⏳ 连接测试中...")
                status_item.setForeground(QColor("#888888"))
                
            self.table.setItem(row, 1, status_item)
            self.table.setItem(row, 2, QTableWidgetItem(st["latency_str"]))
            self.table.setItem(row, 3, QTableWidgetItem(f"规则 #{st['rule_index'] + 1}"))

    def setup_results_view(self):
        self.table_view_mode = "results"
        self.table.setRowCount(0)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书名", "作者", "最新章节", "书源"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    def do_search(self):
        now = time.time()
        if hasattr(self, 'last_search_trigger_time') and now - self.last_search_trigger_time < 0.3:
            return
        self.last_search_trigger_time = now

        if getattr(self, 'is_searching', False):
            self.cancel_search()
            return

        keyword = self.search_input.text().strip()
        if not keyword:
            return

        self.is_searching = True
        self.search_btn.setText("取消")
        self.search_btn.setEnabled(True)
        self.results.clear()
        
        self.setup_connectivity_view()
        self.progress_label.setText("正在全量并发测试书源连通性...")
        
        self.search_worker = SearchWorker(self.client, keyword)
        self.search_worker.rule_tested_signal.connect(self.on_rule_tested)
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
        if getattr(self, 'table_view_mode', '') == "connectivity":
            self.setup_results_view()
            
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
        if getattr(self, 'table_view_mode', '') == "connectivity":
            self.setup_results_view()

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

        book_title = book_info.get('bookName', '未知')
        author_name = book_info.get('author', '未知')

        if export_mode == "epub":
            filter_str = "EPUB Files (*.epub);;All Files (*)"
            default_filename = f"{book_title}_{author_name}.epub"
            default_save_path = os.path.join(default_download_dir, default_filename)
            save_path, _ = QFileDialog.getSaveFileName(self, "选择 EPUB 保存路径", default_save_path, filter_str)
        elif export_mode == "dir":
            default_filename = f"{book_title}_{author_name}"
            default_save_path = os.path.join(default_download_dir, default_filename)
            save_path = QFileDialog.getExistingDirectory(self, "选择保存文件夹目录", default_save_path)
        else:
            filter_str = "Text Files (*.txt);;All Files (*)"
            default_filename = f"{book_title}_{author_name}.txt"
            default_save_path = os.path.join(default_download_dir, default_filename)
            save_path, _ = QFileDialog.getSaveFileName(self, "选择 TXT 保存路径", default_save_path, filter_str)

        if not save_path:
            return  # 用户取消

        # 创建多任务独立的 DownloadWorker
        task_id = f"task_{int(time.time() * 1000)}"
        worker = DownloadWorker(self.client, task_id, book_info, save_path, export_mode=export_mode)
        
        # 将任务添加到下载管理 Tab 表格中
        t_row = self.task_table.rowCount()
        self.task_table.insertRow(t_row)
        
        self.task_table.setItem(t_row, 0, QTableWidgetItem(f"{book_title} ({author_name})"))
        self.task_table.setItem(t_row, 1, QTableWidgetItem(export_mode.upper()))
        
        pbar = QProgressBar()
        pbar.setValue(0)
        self.task_table.setCellWidget(t_row, 2, pbar)
        
        st_item = QTableWidgetItem("⏳ 准备下载...")
        self.task_table.setItem(t_row, 3, st_item)
        
        cancel_btn = QPushButton("❌ 取消下载")
        cancel_btn.setStyleSheet("background-color: #C62828; color: white; border-radius: 3px; font-size: 11px;")
        cancel_btn.clicked.connect(lambda _, tid=task_id: self.cancel_download_task(tid))
        self.task_table.setCellWidget(t_row, 4, cancel_btn)

        self.tasks[task_id] = {
            "worker": worker,
            "row": t_row,
            "save_path": save_path,
            "title": book_title,
            "author": author_name,
            "mode": export_mode,
            "pbar": pbar,
            "st_item": st_item,
            "btn": cancel_btn
        }

        # 关联信号
        worker.progress_signal.connect(self.on_task_progress)
        worker.finished_signal.connect(self.on_task_finished)
        worker.error_signal.connect(self.on_task_error)
        worker.cancelled_signal.connect(self.on_task_cancelled)
        
        # 启动线程
        worker.start()

        # 更新选项卡标题
        self.tabs.setTabText(1, f"📥 下载任务与书架 ({len(self.tasks)})")
        # 自动跳转到下载任务 Tab 查看进度
        self.tabs.setCurrentIndex(1)

    def cancel_download_task(self, task_id: str):
        if task_id in self.tasks:
            info = self.tasks[task_id]
            info["worker"].cancel()
            info["st_item"].setText("正在中断连接...")
            info["btn"].setEnabled(False)

    def on_task_progress(self, task_id: str, current: int, total: int, status_text: str):
        if task_id in self.tasks:
            info = self.tasks[task_id]
            info["st_item"].setText(status_text)
            if total > 0:
                info["pbar"].setMaximum(total)
                info["pbar"].setValue(current)

    def on_task_finished(self, task_id: str, save_path: str):
        if task_id in self.tasks:
            info = self.tasks[task_id]
            from PyQt6.QtGui import QColor
            info["st_item"].setText("✅ 下载完成并入库书架")
            info["st_item"].setForeground(QColor("#2E7D32"))
            info["btn"].setText("✅ 已完成")
            info["btn"].setEnabled(False)
            info["btn"].setStyleSheet("background-color: #2E7D32; color: white;")
            
            # 自动登记到主书架 ConfigManager
            parent_win = self.parent()
            if parent_win and hasattr(parent_win, 'config_manager'):
                parent_win.config_manager.add_to_bookshelf(save_path, {
                    "title": info["title"],
                    "author": info["author"],
                    "format": info["mode"]
                })
                if hasattr(parent_win, 'refresh_bookshelf'):
                    parent_win.refresh_bookshelf()

    def on_task_error(self, task_id: str, err_msg: str):
        if task_id in self.tasks:
            info = self.tasks[task_id]
            from PyQt6.QtGui import QColor
            info["st_item"].setText(f"❌ 失败: {err_msg}")
            info["st_item"].setForeground(QColor("#C62828"))
            info["btn"].setText("重试")
            info["btn"].setEnabled(True)

    def on_task_cancelled(self, task_id: str):
        if task_id in self.tasks:
            info = self.tasks[task_id]
            from PyQt6.QtGui import QColor
            info["st_item"].setText("⛔ 已手动取消")
            info["st_item"].setForeground(QColor("#888888"))
            info["btn"].setText("已取消")
            info["btn"].setEnabled(False)
            info["btn"].setStyleSheet("background-color: #888888; color: white;")

