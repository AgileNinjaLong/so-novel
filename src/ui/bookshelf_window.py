import os
import sys
import re
import time
import threading
import requests
from typing import Dict, Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QComboBox, QProgressBar,
    QSystemTrayIcon, QMenu, QGroupBox, QFormLayout, QKeySequenceEdit, QDoubleSpinBox, QApplication, QStyle, QCheckBox
)
from PyQt6.QtGui import QColor, QFont, QIcon, QDragEnterEvent, QDropEvent, QKeySequence

from src.core.config import ConfigManager
from src.core.db_manager import DatabaseManager
from src.core.sonovel_client import SoNovelClient
from src.core.parser import NovelParser
from src.core.version import __version__, FULL_VERSION_STRING, RELEASE_DATE

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_DOWNLOAD_DIR = os.path.join(ROOT_DIR, "downloads")

def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
        p = os.path.join(base_path, relative_path)
        if os.path.exists(p):
            return p
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        return os.path.join(exe_dir, relative_path)
    else:
        return os.path.join(ROOT_DIR, relative_path)

# ==================== 搜索/下载 工作线程 ====================
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
        try:
            if hasattr(self, 'client') and hasattr(self.client, 'session'):
                self.client.session.close()  # 强行关闭底层物理 Socket，打断阻塞中的 HTTP 请求
        except Exception:
            pass

    def run(self):
        try:
            def on_item(item):
                try: self.item_found_signal.emit(item)
                except RuntimeError: pass

            def on_status(msg):
                try: self.status_signal.emit(msg)
                except RuntimeError: pass

            def on_rule_tested(r_idx, r_name, is_ok, latency_ms):
                try: self.rule_tested_signal.emit(r_idx, r_name, is_ok, latency_ms)
                except RuntimeError: pass
            
            res = self.client.search(
                self.keyword, 
                callback=on_item, 
                status_callback=on_status, 
                cancel_event=self.cancel_event,
                rule_tested_callback=on_rule_tested
            )
            try: self.finished_signal.emit(res)
            except RuntimeError: pass
        except Exception as e:
            try: self.error_signal.emit(str(e))
            except RuntimeError: pass


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
        self.export_mode = export_mode
        self.cancel_event = threading.Event()
        
        # 物理隔离 Session 与 50 槽位连接池
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.session.headers.update(self.client.headers)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def cancel(self):
        self.cancel_event.set()
        try:
            self.session.close()  # 强行关闭底层物理 Socket，打断阻塞中的 HTTP 请求
        except Exception:
            pass

    def run(self):
        try:
            rule = self.book_info["rule"]
            book_url = self.book_info["url"]
            book_name = self.book_info.get("bookName", "未知书名")
            author = self.book_info.get("author", "未知作者")
            
            self.progress_signal.emit(self.task_id, 0, 0, "正在解析图书目录...")
            toc = self.client.get_toc(book_url, rule, cancel_event=self.cancel_event, session=self.session)
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
                    content = self.download_chapter_isolated(chap["url"], rule)
                    return i, content
                except Exception as e:
                    return i, f"下载失败: {e}"

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=15)
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
                self.progress_signal.emit(self.task_id, total, total, f"正在补全 {len(failed_indices)} 个卡顿章节...")
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

            self.progress_signal.emit(self.task_id, total, total, "下载完毕，合成落盘中...")

            # 合成落盘
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
            self.error_signal.emit(self.task_id, f"下载异常: {str(e)}")

    def download_chapter_isolated(self, chapter_url: str, rule: dict) -> str:
        from lxml import html
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
                    resp = self.session.get(current_url, timeout=(3.0, 5.0))
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


class AutoUpdateWorker(QObject):
    task_progress_signal = pyqtSignal(str, int, int, str)
    task_finished_signal = pyqtSignal(str, str)
    task_error_signal = pyqtSignal(str, str)
    status_signal = pyqtSignal(str)

    def __init__(self, client: SoNovelClient, tasks_to_update: list, db_manager: DatabaseManager):
        super().__init__()
        self.client = client
        self.tasks_to_update = tasks_to_update
        self.db_manager = db_manager
        self.cancel_event = threading.Event()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        if not self.tasks_to_update:
            return

        self.status_signal.emit(f"🔄 正在自动追更检查 {len(self.tasks_to_update)} 本小说...")
        
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update(self.client.headers)

        for task in self.tasks_to_update:
            if self.cancel_event.is_set():
                break

            task_id = task["task_id"]
            book_title = task.get("book_title", "未知")
            book_url = task.get("url", "")
            rule = task.get("rule", {})
            existing_total = task.get("progress_total", 0)

            if not book_url or not rule:
                continue

            self.task_progress_signal.emit(task_id, existing_total, existing_total, "🔄 正在检测最新章节...")

            # 链接超时时间 10s，最多重试 3 次
            toc = None
            for attempt in range(3):
                if self.cancel_event.is_set():
                    break
                try:
                    toc = self.client.get_toc(book_url, rule, cancel_event=self.cancel_event, session=session)
                    if toc:
                        break
                except Exception:
                    if attempt < 2:
                        time.sleep(1.0)

            if self.cancel_event.is_set():
                break

            if not toc:
                # 提示自动更新失败（网络/书源超时）
                err_text = "❌ 自动更新失败 (网络/书源超时)"
                self.task_error_signal.emit(task_id, err_text)
                self.db_manager.update_task_status(task_id, "ERROR", err_text)
                continue

            new_total = len(toc)
            if new_total > existing_total:
                added_count = new_total - existing_total
                self.task_progress_signal.emit(task_id, existing_total, new_total, f"发现 {added_count} 章新章节，准备追更...")

                import concurrent.futures
                chapter_contents = [None] * new_total

                def _download_chap(i, chap):
                    if self.cancel_event.is_set():
                        return i, None
                    try:
                        resp = session.get(chap["url"], timeout=(4.0, 10.0))
                        if resp.status_code == 200:
                            from lxml import html
                            tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding or resp.apparent_encoding))
                            content_nodes = self.client._select_elements(tree, rule.get("chapter", {}).get("content", ""))
                            if content_nodes:
                                text = content_nodes[0].text_content()
                                return i, "\n".join([l.strip() for l in text.splitlines() if l.strip()])
                    except Exception:
                        pass
                    return i, "(追更本章暂无内容)"

                executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
                try:
                    futures = {executor.submit(_download_chap, i, toc[i]): i for i in range(existing_total, new_total)}
                    for future in concurrent.futures.as_completed(futures):
                        if self.cancel_event.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        try:
                            i, content = future.result()
                            chapter_contents[i] = content
                        except Exception:
                            pass
                finally:
                    executor.shutdown(wait=False)

                if self.cancel_event.is_set():
                    return

                # 追加写入落盘文件
                save_path = task.get("save_path", "")
                export_mode = task.get("export_mode", "epub")
                if save_path and os.path.exists(os.path.dirname(os.path.abspath(save_path))):
                    if export_mode == "txt" and os.path.exists(save_path):
                        with open(save_path, "a", encoding="utf-8") as f:
                            for idx in range(existing_total, new_total):
                                f.write(f"\n\n{toc[idx]['title']}\n\n{chapter_contents[idx] or ''}\n")
                    elif export_mode == "dir":
                        os.makedirs(save_path, exist_ok=True)
                        for idx in range(existing_total, new_total):
                            chap = toc[idx]
                            safe_t = re.sub(r'[\\/:*?"<>|]', '_', chap['title'])
                            fpath = os.path.join(save_path, f"{idx+1:04d}_{safe_t}.txt")
                            with open(fpath, "w", encoding="utf-8") as f:
                                f.write(f"{chap['title']}\n\n{chapter_contents[idx] or ''}\n")

                succ_msg = f"✅ 追更成功 (新增 {added_count} 章，总 {new_total} 章)"
                self.task_finished_signal.emit(task_id, succ_msg)
                self.db_manager.update_task_progress(task_id, succ_msg, new_total, new_total)
                self.db_manager.update_task_status(task_id, "COMPLETED", succ_msg)
            else:
                ok_msg = f"✅ 已是最新章节 (共 {existing_total} 章)"
                self.task_progress_signal.emit(task_id, existing_total, existing_total, ok_msg)
                self.db_manager.update_task_status(task_id, "COMPLETED", ok_msg)

        session.close()
        self.status_signal.emit("✅ 自动追更轮询检测完毕")


# ==================== 主书架全 Tab 窗口 ====================
class BookshelfWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.db_manager = DatabaseManager()
        self._client = None  # 延迟加载 SoNovelClient，提升启动速度
        self.active_reading_windows = {}  # file_path -> stealth_window
        self.download_tasks = {}          # task_id -> task_info
        self.search_results = []
        
        self.tab_initialized = {0: False, 1: False, 2: False, 3: False}
        os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)

        self.setWindowTitle("📚 摸鱼看小说 - 全网藏书与下载中心")
        self.resize(920, 620)
        self.setAcceptDrops(True)
        
        # 加载图标 (优先使用 get_resource_path 兼容 PyInstaller 打包与源码运行)
        icon_path = get_resource_path(os.path.join("resources", "icon.png"))
        if not os.path.exists(icon_path):
            icon_path = get_resource_path(os.path.join("resources", "icon.ico"))

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.init_system_tray(icon_path)
        self.init_ui()
        self.load_download_tasks_from_db()

        # 自动追更定时器：每 30 分钟轮询检测一次，软件启动 2 秒后默认执行第一次
        self.auto_update_timer = QTimer(self)
        self.auto_update_timer.setInterval(30 * 60 * 1000)
        self.auto_update_timer.timeout.connect(self.trigger_auto_update_check)
        self.auto_update_timer.start()

        QTimer.singleShot(2000, self.trigger_auto_update_check)

    def trigger_auto_update_check(self):
        """自动追更检索：软件开启默认执行一次，之后每 30 分钟轮询一次"""
        tasks = self.db_manager.get_all_tasks()
        auto_tasks = [t for t in tasks if t.get("is_auto_update") == 1]
        if not auto_tasks:
            return

        valid_auto_tasks = []
        for t in auto_tasks:
            tid = t["task_id"]
            if tid in self.download_tasks and self.download_tasks[tid].get("worker"):
                continue
            valid_auto_tasks.append(t)

        if not valid_auto_tasks:
            return

        self.auto_worker = AutoUpdateWorker(self.client, valid_auto_tasks, self.db_manager)
        self.auto_worker.task_progress_signal.connect(self.on_task_progress)
        self.auto_worker.task_finished_signal.connect(self.on_task_finished)
        self.auto_worker.task_error_signal.connect(self.on_task_error)
        self.auto_worker.start()

    def load_download_tasks_from_db(self):
        """启动时从 SQLite 数据库恢复并落库展现所有历史下载任务"""
        tasks = self.db_manager.get_all_tasks()
        for t in tasks:
            task_id = t["task_id"]
            book_title = t.get("book_title", "未知")
            author_name = t.get("author", "未知")
            export_mode = t.get("export_mode", "epub")
            save_path = t.get("save_path", "")
            status = t.get("status", "COMPLETED")
            status_text = t.get("status_text", "✅ 已完成")
            progress_current = t.get("progress_current", 0)
            progress_total = t.get("progress_total", 0)
            is_auto = t.get("is_auto_update", 0) == 1
            book_info = t.get("book_info", {})

            t_row = self.task_table.rowCount()
            self.task_table.insertRow(t_row)

            title_item = QTableWidgetItem()
            title_item.setData(Qt.ItemDataRole.UserRole, task_id)
            title_item.setData(Qt.ItemDataRole.UserRole + 1, t.get("url", ""))

            def _apply_title_style(item, b_title, a_name, is_checked):
                if is_checked:
                    item.setText(f"[🔄 追更中] {b_title} ({a_name})")
                    item.setForeground(QColor("#7C4DFF"))  # 专属高亮紫色
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setText(f"{b_title} ({a_name})")
                    item.setForeground(QColor("#FFFFFF"))
                    font = item.font()
                    font.setBold(False)
                    item.setFont(font)

            _apply_title_style(title_item, book_title, author_name, is_auto)
            self.task_table.setItem(t_row, 0, title_item)
            self.task_table.setItem(t_row, 1, QTableWidgetItem(export_mode.upper()))

            pbar = QProgressBar()
            if progress_total > 0:
                pbar.setMaximum(progress_total)
                pbar.setValue(progress_current)
            else:
                pbar.setValue(100 if status == "COMPLETED" else 0)
            self.task_table.setCellWidget(t_row, 2, pbar)

            st_item = QTableWidgetItem(status_text)
            if status == "COMPLETED":
                st_item.setForeground(QColor("#2E7D32"))
            elif status in ("CANCELLED", "ERROR"):
                st_item.setForeground(QColor("#888888" if status == "CANCELLED" else "#C62828"))
            self.task_table.setItem(t_row, 3, st_item)

            btn_box = QWidget()
            btn_layout = QHBoxLayout(btn_box)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(6)

            chk_auto = QCheckBox("🔄 追更")
            chk_auto.setToolTip("勾选后将开启后台独立线程每 30 分钟自动检查并增量更新最新章节")
            chk_auto.setStyleSheet("color: #64B5F6; font-size: 11px; font-weight: bold;")
            chk_auto.setChecked(is_auto)

            def _make_toggled(tid, item, b_title, a_name):
                def _on_toggled(checked):
                    val = 1 if checked else 0
                    self.db_manager.set_auto_update(tid, val)
                    if tid in self.download_tasks:
                        self.download_tasks[tid]["is_auto_update"] = val
                    _apply_title_style(item, b_title, a_name, checked)
                return _on_toggled

            chk_auto.toggled.connect(_make_toggled(task_id, title_item, book_title, author_name))

            action_btn = QPushButton()
            action_btn.setFixedWidth(70)
            action_btn.setFixedHeight(26)

            if status == "COMPLETED":
                action_btn.setText("✅ 完成")
                action_btn.setEnabled(False)
                action_btn.setStyleSheet("background-color: #2E7D32; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
            elif status == "CANCELLED":
                action_btn.setText("重试")
                action_btn.setEnabled(True)
                action_btn.setStyleSheet("background-color: #0288D1; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
                action_btn.clicked.connect(lambda _, tid=task_id: self.retry_download_task(tid))
            elif status == "ERROR":
                action_btn.setText("重试")
                action_btn.setEnabled(True)
                action_btn.setStyleSheet("background-color: #0288D1; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
                action_btn.clicked.connect(lambda _, tid=task_id: self.retry_download_task(tid))
            else: # DOWNLOADING / PENDING
                st_item.setText("⏸️ 上次未完成")
                action_btn.setText("重新下载")
                action_btn.setEnabled(True)
                action_btn.setStyleSheet("background-color: #0288D1; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
                action_btn.clicked.connect(lambda _, tid=task_id: self.retry_download_task(tid))

            del_btn = QPushButton("🗑️ 清除")
            del_btn.setFixedWidth(70)
            del_btn.setFixedHeight(26)
            del_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
            del_btn.clicked.connect(lambda _, tid=task_id: self.remove_download_task(tid))

            btn_layout.addWidget(chk_auto)
            btn_layout.addWidget(action_btn)
            btn_layout.addWidget(del_btn)
            self.task_table.setCellWidget(t_row, 4, btn_box)

            self.download_tasks[task_id] = {
                "worker": None, "row": t_row, "save_path": save_path,
                "title": book_title, "author": author_name, "mode": export_mode,
                "url": t.get("url", ""), "source_name": t.get("source_name", "未知"),
                "pbar": pbar, "st_item": st_item, "btn": action_btn, "del_btn": del_btn,
                "book_info": book_info, "is_auto_update": 1 if is_auto else 0
            }

        self.tabs.setTabText(2, f"📥 下载管理 ({len(self.download_tasks)})")

    def retry_download_task(self, task_id: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            book_info = info.get("book_info", {})
            save_path = info.get("save_path", "")
            export_mode = info.get("mode", "epub")
            if not book_info or not book_info.get("url"):
                QMessageBox.warning(self, "重试提示", "未能恢复该任务的书源配置信息。")
                return

            info["btn"].setText("❌ 取消")
            info["btn"].setEnabled(True)
            info["btn"].setStyleSheet("background-color: #C62828; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
            try: info["btn"].clicked.disconnect()
            except Exception: pass
            info["btn"].clicked.connect(lambda _, tid=task_id: self.cancel_download_task(tid))

            info["st_item"].setText("⏳ 重新准备下载...")
            info["st_item"].setForeground(QColor("#FFFFFF"))

            worker = DownloadWorker(self.client, task_id, book_info, save_path, export_mode=export_mode)
            info["worker"] = worker

            worker.progress_signal.connect(self.on_task_progress)
            worker.finished_signal.connect(self.on_task_finished)
            worker.error_signal.connect(self.on_task_error)
            worker.cancelled_signal.connect(self.on_task_cancelled)
            worker.start()

            self.db_manager.update_task_status(task_id, "DOWNLOADING", "⏳ 重新准备下载...")

    @property
    def client(self):
        if self._client is None:
            self._client = SoNovelClient()
        return self._client

    def init_system_tray(self, icon_path):
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("📚 摸鱼看小说阅读器 (单击/双击恢复主窗口)")
        
        menu = QMenu()
        show_action = menu.addAction("📚 显示主书架窗口")
        show_action.triggered.connect(self.show_main_window)

        boss_action = menu.addAction(f"🛡️ 隐身老板键 ({self.config_manager.settings.get('boss_key', 'Alt+Z')})")
        boss_action.triggered.connect(self.toggle_all_reading_windows)

        menu.addSeparator()
        quit_action = menu.addAction("❌ 彻底退出程序")
        quit_action.triggered.connect(self.quit_application)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def show_main_window(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()

    def on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_main_window()

    def toggle_all_reading_windows(self):
        for path, win in list(self.active_reading_windows.items()):
            if win and hasattr(win, 'toggle_boss_key'):
                win.toggle_boss_key()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # 统一全局纯正黑色科技风 QSS 样式表 (字体纯白高对比)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121214;
            }
            QWidget {
                background-color: #121214;
                color: #FFFFFF;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QTabWidget::pane {
                border: 1px solid #2D2D3A;
                background: #18181C;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #252530;
                color: #B0B0C0;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 3px;
            }
            QTabBar::tab:selected {
                background: #18181C;
                color: #64B5F6;
                border-bottom: 3px solid #64B5F6;
            }
            QTableWidget {
                background-color: #18181C;
                color: #FFFFFF;
                gridline-color: #2D2D3A;
                border: 1px solid #2D2D3A;
                border-radius: 4px;
                selection-background-color: #0D47A1;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #252530;
                color: #64B5F6;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #2D2D3A;
            }
            QLineEdit, QComboBox, QKeySequenceEdit, QDoubleSpinBox {
                background-color: #282836;
                color: #FFFFFF;
                border: 1px solid #3F3F56;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QLineEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {
                border: 1px solid #64B5F6;
            }
            QGroupBox {
                color: #64B5F6;
                font-weight: bold;
                border: 1px solid #3F3F56;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QProgressBar {
                border: 1px solid #3F3F56;
                border-radius: 4px;
                text-align: center;
                background-color: #282836;
                color: #FFFFFF;
            }
            QProgressBar::chunk {
                background-color: #2E7D32;
                border-radius: 3px;
            }
        """)

        # 选项卡主控件
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)

        # 预先构建所有 Tab 页面，确保 task_table 与 search_table 从启动刻起完全可用
        self.tab_bookshelf = QWidget()
        self.tab_bookstore = QWidget()
        self.tab_downloads = QWidget()
        self.tab_settings = QWidget()

        self.tabs.addTab(self.tab_bookshelf, "📚 我的藏书")
        self.tabs.addTab(self.tab_bookstore, "🌐 全网书城")
        self.tabs.addTab(self.tab_downloads, "📥 下载管理 (0)")
        self.tabs.addTab(self.tab_settings, "⚙️ 系统设置")

        self.init_tab_bookshelf()
        self.init_tab_bookstore()
        self.init_tab_downloads()
        self.init_tab_settings()

        self.refresh_bookshelf()
        for i in range(4):
            self.tab_initialized[i] = True

    def on_tab_changed(self, index: int):
        if index == 1 and not self.tab_initialized[1]:
            self.init_tab_bookstore()
            self.tab_initialized[1] = True
        elif index == 2 and not self.tab_initialized[2]:
            self.init_tab_downloads()
            self.tab_initialized[2] = True
        elif index == 3 and not self.tab_initialized[3]:
            self.init_tab_settings()
            self.tab_initialized[3] = True

    # ====== Tab 1: 我的藏书 =====
    def init_tab_bookshelf(self):
        layout = QVBoxLayout(self.tab_bookshelf)
        
        # 顶栏
        h = QHBoxLayout()
        lbl = QLabel("📚 我的摸鱼藏书")
        lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #64B5F6;")
        
        self.import_btn = QPushButton("📂 导入本地电子书 (.txt / .epub)")
        self.import_btn.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.import_btn.clicked.connect(self.do_import_local_book)

        h.addWidget(lbl)
        h.addStretch()
        h.addWidget(self.import_btn)
        layout.addLayout(h)

        tip = QLabel("💡 提示：可直接拖拽电脑中的小说文件放进来。点击“摸鱼开读”可在右下角隐蔽阅读，主界面不会强制关闭，支持同时打开多本看！")
        tip.setStyleSheet("color: #B0C4DE; font-size: 12px; background: #252535; padding: 6px 10px; border-radius: 4px;")
        layout.addWidget(tip)

        self.shelf_table = QTableWidget()
        self.shelf_table.setColumnCount(6)
        self.shelf_table.setHorizontalHeaderLabels(["小说名称", "作者", "格式", "加入时间", "阅读进度", "操作"])
        self.shelf_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.shelf_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.shelf_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.shelf_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.shelf_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.shelf_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.shelf_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.shelf_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.shelf_table.itemDoubleClicked.connect(self.on_shelf_item_double_clicked)
        layout.addWidget(self.shelf_table)

    # ====== Tab 2: 全网书城 =====
    def init_tab_bookstore(self):
        layout = QVBoxLayout(self.tab_bookstore)

        h = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入小说名或作者发起 24 书源高并发搜索...")
        self.search_input.returnPressed.connect(self.do_search)
        
        self.search_btn = QPushButton("搜索")
        self.search_btn.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.search_btn.clicked.connect(self.do_search)

        h.addWidget(self.search_input)
        h.addWidget(self.search_btn)
        layout.addLayout(h)

        self.search_table = QTableWidget()
        self.search_table.setColumnCount(4)
        self.search_table.setHorizontalHeaderLabels(["书名", "作者", "最新章节", "书源"])
        self.search_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.search_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.search_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.search_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.search_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.search_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.search_table)

        self.search_status_label = QLabel("")
        layout.addWidget(self.search_status_label)

        b_layout = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("📚 EPUB 电子书 (标准打包 - 默认首选)", "epub")
        self.mode_combo.addItem("📄 单文件 TXT (合并文本)", "txt")
        self.mode_combo.addItem("📂 按章节拆分目录 (离散文件)", "dir")

        self.download_btn = QPushButton("📥 下载选中的小说 (添加任务)")
        self.download_btn.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.download_btn.clicked.connect(self.do_add_download_task)

        b_layout.addWidget(QLabel("合成格式:"))
        b_layout.addWidget(self.mode_combo)
        b_layout.addWidget(self.download_btn)
        layout.addLayout(b_layout)

    # ====== Tab 3: 下载管理 =====
    def init_tab_downloads(self):
        layout = QVBoxLayout(self.tab_downloads)

        lbl = QLabel("📥 多任务下载管理 (专属 Socket 槽位隔离)")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(lbl)

        self.task_table = QTableWidget()
        self.task_table.setColumnCount(5)
        self.task_table.setHorizontalHeaderLabels(["小说名称", "格式", "进度条", "状态说明", "操作"])
        self.task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.task_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.task_table)

    # ====== Tab 4: 系统设置 =====
    def init_tab_settings(self):
        layout = QVBoxLayout(self.tab_settings)

        group_mode = QGroupBox("模式与全局隐身按键")
        form_mode = QFormLayout()
        
        self.boss_key_edit = QKeySequenceEdit(self)
        self.boss_key_edit.setKeySequence(QKeySequence(self.config_manager.settings.get("boss_key", "Alt+Z")))
        self.hk_floating_edit = QKeySequenceEdit(self)
        self.hk_floating_edit.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_floating", "Ctrl+1")))
        self.hk_ide_edit = QKeySequenceEdit(self)
        self.hk_ide_edit.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_ide", "Ctrl+2")))
        self.hk_cad_edit = QKeySequenceEdit(self)
        self.hk_cad_edit.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_cad", "Ctrl+3")))

        form_mode.addRow("🛡️ 老板键 (全局隐身):", self.boss_key_edit)
        form_mode.addRow("📖 极简透明模式:", self.hk_floating_edit)
        form_mode.addRow("💻 IDE 伪装模式:", self.hk_ide_edit)
        form_mode.addRow("📐 CAD 伪装模式:", self.hk_cad_edit)
        group_mode.setLayout(form_mode)
        layout.addWidget(group_mode)

        group_read = QGroupBox("阅读控制与自动滚动")
        form_read = QFormLayout()
        
        self.hk_next_line = QKeySequenceEdit(self)
        self.hk_next_line.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_next_line", "Down")))
        self.hk_prev_line = QKeySequenceEdit(self)
        self.hk_prev_line.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_prev_line", "Up")))
        self.hk_next_chap = QKeySequenceEdit(self)
        self.hk_next_chap.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_next_chap", "PageDown")))
        self.hk_prev_chap = QKeySequenceEdit(self)
        self.hk_prev_chap.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_prev_chap", "PageUp")))

        self.hk_toggle_auto = QKeySequenceEdit(self)
        self.hk_toggle_auto.setKeySequence(QKeySequence(self.config_manager.settings.get("hk_toggle_auto", "Ctrl+Space")))

        self.auto_speed_spin = QDoubleSpinBox(self)
        self.auto_speed_spin.setRange(1.0, 50.0)
        self.auto_speed_spin.setSingleStep(1.0)
        self.auto_speed_spin.setSuffix(" px/s (像素/秒)")
        self.auto_speed_spin.setValue(float(self.config_manager.settings.get("auto_scroll_speed", 8.0)))

        form_read.addRow("⬇️ 下一行:", self.hk_next_line)
        form_read.addRow("⬆️ 上一行:", self.hk_prev_line)
        form_read.addRow("⏭️ 下一章:", self.hk_next_chap)
        form_read.addRow("⏮️ 上一章:", self.hk_prev_chap)
        form_read.addRow("▶️ 开启/暂停自动翻页:", self.hk_toggle_auto)
        form_read.addRow("⏱️ 自动连续滚动速度:", self.auto_speed_spin)
        group_read.setLayout(form_read)
        layout.addWidget(group_read)

        save_btn = QPushButton("💾 保存系统设置")
        save_btn.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        save_btn.clicked.connect(self.save_settings_tab)
        layout.addWidget(save_btn)

    # ====== 藏书刷新与开读 =====
    def refresh_bookshelf(self):
        shelf = self.config_manager.get_bookshelf()
        self.shelf_table.setRowCount(0)
        sorted_items = sorted(shelf.items(), key=lambda x: x[1].get("add_time", ""), reverse=True)
        
        for path, info in sorted_items:
            row = self.shelf_table.rowCount()
            self.shelf_table.insertRow(row)
            
            title_item = QTableWidgetItem(info.get("title", "未知小说"))
            title_item.setData(Qt.ItemDataRole.UserRole, path)
            self.shelf_table.setItem(row, 0, title_item)
            self.shelf_table.setItem(row, 1, QTableWidgetItem(info.get("author", "未知")))
            
            fmt_item = QTableWidgetItem(info.get("format", "txt").upper())
            fmt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.shelf_table.setItem(row, 2, fmt_item)
            self.shelf_table.setItem(row, 3, QTableWidgetItem(info.get("add_time", "-")))
            
            hist = self.config_manager.history.get(path, {})
            c_idx = hist.get("chapter_idx", 0)
            prog_str = f"第 {c_idx + 1} 章" if c_idx > 0 else "未开始"
            prog_item = QTableWidgetItem(prog_str)
            prog_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.shelf_table.setItem(row, 4, prog_item)

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
            self.shelf_table.setCellWidget(row, 5, btn_box)

    def on_shelf_item_double_clicked(self, item):
        row = item.row()
        title_item = self.shelf_table.item(row, 0)
        if title_item:
            path = title_item.data(Qt.ItemDataRole.UserRole)
            if path: self.start_reading(path)

    def copy_file_to_downloads(self, src_path: str) -> str:
        """自动将外部导入的小说复制一份存放于项目根目录 downloads/ 文件夹中"""
        import shutil
        src_path = os.path.abspath(src_path)
        os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)
        
        try:
            if os.path.commonpath([src_path, os.path.abspath(DEFAULT_DOWNLOAD_DIR)]) == os.path.abspath(DEFAULT_DOWNLOAD_DIR):
                return src_path
        except Exception:
            pass

        filename = os.path.basename(src_path)
        dest_path = os.path.join(DEFAULT_DOWNLOAD_DIR, filename)
        
        if os.path.exists(dest_path) and os.path.abspath(dest_path) != src_path:
            name_without_ext, ext = os.path.splitext(filename)
            dest_path = os.path.join(DEFAULT_DOWNLOAD_DIR, f"{name_without_ext}_{int(time.time())}{ext}")
            
        try:
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dest_path)
            return dest_path
        except Exception:
            return src_path

    def start_reading(self, file_path: str):
        """开启摸鱼阅读：主界面保持显示不隐藏，支持同时打开多本小说"""
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "文件丢失", f"找不到小说文件：\n{file_path}")
            self.config_manager.remove_from_bookshelf(file_path)
            self.refresh_bookshelf()
            return

        self.config_manager.settings["last_file"] = file_path
        self.config_manager.save_immediately()

        # 检查是否已在活动摸鱼窗口池中
        if file_path in self.active_reading_windows:
            win = self.active_reading_windows[file_path]
            if win and hasattr(win, 'is_boss_hidden') and not win.is_boss_hidden:
                win.show()
                win.raise_()
                win.activateWindow()
                return

        mode = self.config_manager.settings.get("mode", "floating")
        if mode == "ide_pseudo":
            from src.ui.ide_pseudo_view import IDEPseudoView
            win = IDEPseudoView(self.config_manager, bookshelf_window=self)
        elif mode == "cad_pseudo":
            from src.ui.cad_pseudo_view import CADPseudoView
            win = CADPseudoView(self.config_manager, bookshelf_window=self)
        else:
            from src.ui.floating_view import FloatingView
            win = FloatingView(self.config_manager, bookshelf_window=self)

        # 触发加载并渲染小说文本
        win.load_file(file_path)
        self.active_reading_windows[file_path] = win
        win.show()

    def remove_book(self, file_path: str):
        self.config_manager.remove_from_bookshelf(file_path)
        self.refresh_bookshelf()

    def do_import_local_book(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择本地小说文件导入书架", "", "Novel Files (*.txt *.epub);;All Files (*)")
        if files:
            imported_count = 0
            for f in files:
                target_path = self.copy_file_to_downloads(f)
                self.config_manager.add_to_bookshelf(target_path)
                imported_count += 1
            self.refresh_bookshelf()
            QMessageBox.information(self, "导入成功", f"已成功将 {imported_count} 本小说保存至根目录 downloads/ 并加入书架！")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        count = 0
        for url in urls:
            f = url.toLocalFile()
            if os.path.exists(f) and (f.endswith('.txt') or f.endswith('.epub') or os.path.isdir(f)):
                target_path = self.copy_file_to_downloads(f)
                self.config_manager.add_to_bookshelf(target_path)
                count += 1
        if count > 0:
            self.refresh_bookshelf()
            QMessageBox.information(self, "拖拽导入成功", f"已自动将 {count} 本小说复制入库至根目录 downloads/ 文件夹中！")

    # ====== 搜书逻辑 =====
    def setup_connectivity_view(self):
        self.search_view_mode = "connectivity"
        self.search_table.setRowCount(0)
        self.search_table.setColumnCount(4)
        self.search_table.setHorizontalHeaderLabels(["书源名称", "连通状态", "响应延迟", "规则位次"])
        
        self.rule_test_states = {}
        for idx, rule in enumerate(self.client.rules):
            r_idx = rule.get('rule_index', idx)
            r_name = rule.get("name", "未知书源")
            self.rule_test_states[r_idx] = {
                "name": r_name, "rule_index": r_idx, "is_ok": False,
                "is_tested": False, "latency_ms": 999999, "latency_str": "-"
            }
        self.refresh_connectivity_table()

    def on_rule_tested(self, r_idx, r_name, is_ok, latency_ms):
        if getattr(self, 'search_view_mode', '') != "connectivity": return
        if r_idx in self.rule_test_states:
            st = self.rule_test_states[r_idx]
            st["is_tested"] = True
            st["is_ok"] = is_ok
            st["latency_ms"] = latency_ms if is_ok else 999999
            st["latency_str"] = f"{latency_ms} ms" if is_ok else "超时"
        self.refresh_connectivity_table()

    def refresh_connectivity_table(self):
        if getattr(self, 'search_view_mode', '') != "connectivity": return
        sorted_states = list(self.rule_test_states.values())
        def sort_key(st):
            if st["is_ok"]: priority = 0
            elif st["is_tested"]: priority = 1
            else: priority = 2
            return (priority, st["latency_ms"], st["rule_index"])

        sorted_states.sort(key=sort_key)
        self.search_table.setRowCount(len(sorted_states))
        for row, st in enumerate(sorted_states):
            self.search_table.setItem(row, 0, QTableWidgetItem(st["name"]))
            if st["is_ok"]:
                status_item = QTableWidgetItem("✅ 连通成功")
                status_item.setForeground(QColor("#2E7D32"))
            elif st["is_tested"]:
                status_item = QTableWidgetItem("❌ 超时/不可用")
                status_item.setForeground(QColor("#C62828"))
            else:
                status_item = QTableWidgetItem("⏳ 连接测试中...")
                status_item.setForeground(QColor("#888888"))
                
            self.search_table.setItem(row, 1, status_item)
            self.search_table.setItem(row, 2, QTableWidgetItem(st["latency_str"]))
            self.search_table.setItem(row, 3, QTableWidgetItem(f"规则 #{st['rule_index'] + 1}"))

    def setup_results_view(self):
        self.search_view_mode = "results"
        self.search_table.setRowCount(0)
        self.search_table.setColumnCount(4)
        self.search_table.setHorizontalHeaderLabels(["书名", "作者", "最新章节", "书源"])

    def do_search(self):
        now = time.time()
        if hasattr(self, 'last_search_trigger_time') and now - self.last_search_trigger_time < 0.3:
            return
        self.last_search_trigger_time = now

        if getattr(self, 'is_searching', False):
            self.cancel_search()
            return

        keyword = self.search_input.text().strip()
        if not keyword: return

        self.is_searching = True
        self.search_btn.setText("取消")
        self.search_results.clear()
        
        self.setup_connectivity_view()
        self.search_status_label.setText("正在全量并发测试 24 书源连通性...")
        
        self.search_worker = SearchWorker(self.client, keyword)
        self.search_worker.rule_tested_signal.connect(self.on_rule_tested)
        self.search_worker.item_found_signal.connect(self.on_search_item_found)
        self.search_worker.status_signal.connect(self.on_search_status)
        self.search_worker.finished_signal.connect(self.on_search_finished)
        self.search_worker.error_signal.connect(self.on_search_error)
        self.search_worker.start()

    def cancel_search(self):
        if hasattr(self, 'search_worker') and self.search_worker:
            self.search_worker.cancel()
            self.search_status_label.setText("正在强行打断连接...")
            self.search_btn.setEnabled(False)

    def on_search_item_found(self, item):
        if getattr(self, 'search_view_mode', '') == "connectivity":
            self.setup_results_view()
        row = self.search_table.rowCount()
        self.search_table.insertRow(row)
        self.search_table.setItem(row, 0, QTableWidgetItem(item.get("bookName", "未知")))
        self.search_table.setItem(row, 1, QTableWidgetItem(item.get("author", "未知")))
        self.search_table.setItem(row, 2, QTableWidgetItem(item.get("latestChapter", "")))
        self.search_table.setItem(row, 3, QTableWidgetItem(item.get("sourceName", "未知")))
        self.search_results.append(item)
        self.search_status_label.setText(f"搜索流式输出中... 已发现 {len(self.search_results)} 个结果")

    def on_search_status(self, msg):
        self.search_status_label.setText(msg)

    def on_search_finished(self, sorted_results):
        self.is_searching = False
        if getattr(self, 'search_view_mode', '') == "connectivity":
            self.setup_results_view()
        self.search_results = sorted_results
        self.search_table.setRowCount(len(self.search_results))
        for row, item in enumerate(self.search_results):
            self.search_table.setItem(row, 0, QTableWidgetItem(item.get("bookName", "未知")))
            self.search_table.setItem(row, 1, QTableWidgetItem(item.get("author", "未知")))
            self.search_table.setItem(row, 2, QTableWidgetItem(item.get("latestChapter", "")))
            self.search_table.setItem(row, 3, QTableWidgetItem(item.get("sourceName", "未知")))
            
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")
        self.search_status_label.setText(f"搜索完成，找到 {len(self.search_results)} 个可用结果。")

    def on_search_error(self, err_msg):
        self.is_searching = False
        self.search_status_label.setText(f"搜索错误: {err_msg}")
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")

    # ====== 下载管理 =====
    def do_add_download_task(self):
        selected = self.search_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先在列表中选中一本小说。")
            return

        row = selected[0].row()
        book_info = self.search_results[row]
        export_mode = self.mode_combo.currentData() or "epub"

        book_title = book_info.get('bookName', '未知')
        author_name = book_info.get('author', '未知')

        safe_title = re.sub(r'[\\/:*?"<>|]', '_', book_title)
        safe_author = re.sub(r'[\\/:*?"<>|]', '_', author_name)

        os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)

        # 静默自动落盘至项目根目录下的 downloads 文件夹中，不需要每次弹窗询问
        if export_mode == "epub":
            save_path = os.path.join(DEFAULT_DOWNLOAD_DIR, f"{safe_title}_{safe_author}.epub")
        elif export_mode == "dir":
            save_path = os.path.join(DEFAULT_DOWNLOAD_DIR, f"{safe_title}_{safe_author}")
        else: # txt
            save_path = os.path.join(DEFAULT_DOWNLOAD_DIR, f"{safe_title}_{safe_author}.txt")

        task_id = f"task_{int(time.time() * 1000)}"
        worker = DownloadWorker(self.client, task_id, book_info, save_path, export_mode=export_mode)
        
        t_row = self.task_table.rowCount()
        self.task_table.insertRow(t_row)
        
        title_item = QTableWidgetItem(f"{book_title} ({author_name})")
        title_item.setData(Qt.ItemDataRole.UserRole, task_id)
        title_item.setData(Qt.ItemDataRole.UserRole + 1, book_info.get("url", ""))
        self.task_table.setItem(t_row, 0, title_item)
        self.task_table.setItem(t_row, 1, QTableWidgetItem(export_mode.upper()))
        
        pbar = QProgressBar()
        pbar.setValue(0)
        self.task_table.setCellWidget(t_row, 2, pbar)
        
        st_item = QTableWidgetItem("⏳ 准备下载...")
        self.task_table.setItem(t_row, 3, st_item)
        
        btn_box = QWidget()
        btn_layout = QHBoxLayout(btn_box)
        btn_layout.setContentsMargins(2, 2, 2, 2)
        btn_layout.setSpacing(6)

        chk_auto = QCheckBox("🔄 追更")
        chk_auto.setToolTip("勾选后将开启后台独立线程每 30 分钟自动检查并增量更新最新章节")
        chk_auto.setStyleSheet("color: #64B5F6; font-size: 11px; font-weight: bold;")
        chk_auto.setChecked(False)

        def _apply_new_title_style(item, b_title, a_name, is_checked):
            if is_checked:
                item.setText(f"[🔄 追更中] {b_title} ({a_name})")
                item.setForeground(QColor("#7C4DFF"))  # 专属高亮紫色
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setText(f"{b_title} ({a_name})")
                item.setForeground(QColor("#FFFFFF"))
                font = item.font()
                font.setBold(False)
                item.setFont(font)

        def _on_new_auto_toggled(checked):
            val = 1 if checked else 0
            self.db_manager.set_auto_update(task_id, val)
            if task_id in self.download_tasks:
                self.download_tasks[task_id]["is_auto_update"] = val
            _apply_new_title_style(title_item, book_title, author_name, checked)

        chk_auto.toggled.connect(_on_new_auto_toggled)

        cancel_btn = QPushButton("❌ 取消")
        cancel_btn.setFixedWidth(70)
        cancel_btn.setFixedHeight(26)
        cancel_btn.setStyleSheet("background-color: #C62828; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
        cancel_btn.clicked.connect(lambda _, tid=task_id: self.cancel_download_task(tid))

        del_btn = QPushButton("🗑️ 清除")
        del_btn.setFixedWidth(70)
        del_btn.setFixedHeight(26)
        del_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
        del_btn.clicked.connect(lambda _, tid=task_id: self.remove_download_task(tid))

        btn_layout.addWidget(chk_auto)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(del_btn)
        self.task_table.setCellWidget(t_row, 4, btn_box)

        self.download_tasks[task_id] = {
            "worker": worker, "row": t_row, "save_path": save_path,
            "title": book_title, "author": author_name, "mode": export_mode,
            "url": book_info.get("url", ""), "source_name": book_info.get("sourceName", "未知"),
            "pbar": pbar, "st_item": st_item, "btn": cancel_btn, "del_btn": del_btn,
            "book_info": book_info
        }

        # SQLite 数据库落库
        task_data = {
            "task_id": task_id,
            "book_title": book_title,
            "author": author_name,
            "url": book_info.get("url", ""),
            "source_name": book_info.get("sourceName", "未知"),
            "export_mode": export_mode,
            "save_path": save_path,
            "status": "DOWNLOADING",
            "status_text": "⏳ 准备下载...",
            "progress_current": 0,
            "progress_total": 0,
            "rule": book_info.get("rule", {}),
            "book_info": book_info
        }
        self.db_manager.add_or_update_task(task_data)

        worker.progress_signal.connect(self.on_task_progress)
        worker.finished_signal.connect(self.on_task_finished)
        worker.error_signal.connect(self.on_task_error)
        worker.cancelled_signal.connect(self.on_task_cancelled)
        worker.start()

        self.tabs.setTabText(2, f"📥 下载管理 ({len(self.download_tasks)})")
        self.tabs.setCurrentIndex(2)

    def cancel_download_task(self, task_id: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            if info.get("worker"):
                info["worker"].cancel()
            info["st_item"].setText("正在打断连接...")
            info["btn"].setEnabled(False)

    def remove_download_task(self, task_id: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            if "worker" in info and info["worker"] and hasattr(info["worker"], "cancel"):
                worker = info["worker"]
                try: worker.progress_signal.disconnect()
                except Exception: pass
                try: worker.finished_signal.disconnect()
                except Exception: pass
                try: worker.error_signal.disconnect()
                except Exception: pass
                try: worker.cancelled_signal.disconnect()
                except Exception: pass
                worker.cancel()
                
            del self.download_tasks[task_id]
            self.db_manager.delete_task(task_id)

            # 延迟到下一个事件循环处理 removeRow，避免在 del_btn 自身的 clicked 事件句柄中同步销毁 del_btn 导致 Qt 事件循环死锁/卡顿
            def _remove_row():
                if hasattr(self, 'task_table') and self.task_table:
                    for r in range(self.task_table.rowCount()):
                        item = self.task_table.item(r, 0)
                        if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                            self.task_table.removeRow(r)
                            break
                    self.tabs.setTabText(2, f"📥 下载管理 ({len(self.download_tasks)})")

            QTimer.singleShot(0, _remove_row)

    def on_task_progress(self, task_id: str, current: int, total: int, status_text: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            info["st_item"].setText(status_text)
            if total > 0:
                info["pbar"].setMaximum(total)
                info["pbar"].setValue(current)
            self.db_manager.update_task_progress(task_id, status_text, current, total)

    def on_task_finished(self, task_id: str, save_path: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            info["st_item"].setText("✅ 已自动入库我的藏书")
            info["st_item"].setForeground(QColor("#2E7D32"))
            info["btn"].setText("✅ 完成")
            info["btn"].setEnabled(False)
            info["btn"].setFixedWidth(70)
            info["btn"].setFixedHeight(26)
            info["btn"].setStyleSheet("background-color: #2E7D32; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
            
            self.db_manager.update_task_status(task_id, "COMPLETED", "✅ 已自动入库我的藏书")

            # 自动登记到 ConfigManager 藏书库
            self.config_manager.add_to_bookshelf(save_path, {
                "title": info["title"], "author": info["author"], "format": info["mode"]
            })
            self.refresh_bookshelf()

    def on_task_error(self, task_id: str, err_msg: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            info["st_item"].setText(f"❌ 错误: {err_msg}")
            info["st_item"].setForeground(QColor("#C62828"))
            info["btn"].setText("重试")
            info["btn"].setEnabled(True)
            info["btn"].setFixedWidth(70)
            info["btn"].setFixedHeight(26)
            info["btn"].setStyleSheet("background-color: #0288D1; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
            try: info["btn"].clicked.disconnect()
            except Exception: pass
            info["btn"].clicked.connect(lambda _, tid=task_id: self.retry_download_task(tid))

            self.db_manager.update_task_status(task_id, "ERROR", f"❌ 错误: {err_msg}")

    def on_task_cancelled(self, task_id: str):
        if task_id in self.download_tasks:
            info = self.download_tasks[task_id]
            info["st_item"].setText("⛔ 已手动取消")
            info["st_item"].setForeground(QColor("#888888"))
            info["btn"].setText("重试")
            info["btn"].setEnabled(True)
            info["btn"].setFixedWidth(70)
            info["btn"].setFixedHeight(26)
            info["btn"].setStyleSheet("background-color: #0288D1; color: white; border-radius: 3px; font-size: 11px; font-weight: bold;")
            try: info["btn"].clicked.disconnect()
            except Exception: pass
            info["btn"].clicked.connect(lambda _, tid=task_id: self.retry_download_task(tid))

            self.db_manager.update_task_status(task_id, "CANCELLED", "⛔ 已手动取消")

    # ====== 系统设置页 =====
    def save_settings_tab(self):
        boss_key = self.boss_key_edit.keySequence().toString()
        hk_floating = self.hk_floating_edit.keySequence().toString()
        hk_ide = self.hk_ide_edit.keySequence().toString()
        hk_cad = self.hk_cad_edit.keySequence().toString()
        
        keys = [boss_key, hk_floating, hk_ide, hk_cad]
        valid_keys = [k for k in keys if k]
        if len(valid_keys) != len(set(valid_keys)):
            QMessageBox.critical(self, "防冲突警示", "检测到存在重复绑定的模式/老板键快捷键，请修改！")
            return

        self.config_manager.settings["boss_key"] = boss_key
        self.config_manager.settings["hk_floating"] = hk_floating
        self.config_manager.settings["hk_ide"] = hk_ide
        self.config_manager.settings["hk_cad"] = hk_cad
        
        self.config_manager.settings["hk_next_line"] = self.hk_next_line.keySequence().toString()
        self.config_manager.settings["hk_prev_line"] = self.hk_prev_line.keySequence().toString()
        self.config_manager.settings["hk_next_chap"] = self.hk_next_chap.keySequence().toString()
        self.config_manager.settings["hk_prev_chap"] = self.hk_prev_chap.keySequence().toString()
        self.config_manager.settings["hk_toggle_auto"] = self.hk_toggle_auto.keySequence().toString()
        self.config_manager.settings["auto_scroll_speed"] = self.auto_speed_spin.value()

        self.config_manager.save_immediately()
        QMessageBox.information(self, "设置成功", "系统设置与快捷键已成功保存！")

    # ====== 最小化托盘与防呆关闭事件 =====
    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized():
                if hasattr(self, 'tray_icon') and self.tray_icon:
                    self.tray_icon.show()
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event):
        """点击主界面关闭按钮 (X) 时：在没有在看的小说时直接彻底退出程序；在有摸鱼阅读时弹窗提示并提供彻底退出选项，彻底消除后台僵尸进程！"""
        active_titles = []
        for path, win in list(self.active_reading_windows.items()):
            if win and win.isVisible() and getattr(win, 'book', None):
                active_titles.append(win.book.title)

        if active_titles:
            book_list_str = "\n".join([f" • {t}" for t in active_titles])
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("🛡️ 退出确认 - 摸鱼阅读中")
            msg_box.setText(f"检测到当前有 {len(active_titles)} 本小说正在右下角摸鱼阅读中：\n{book_list_str}\n\n请选择关闭方式：")
            
            b_close_all = msg_box.addButton("❌ 彻底退出程序(关闭全部)", QMessageBox.ButtonRole.DestructiveRole)
            b_tray = msg_box.addButton("📌 仅缩小至托盘(后台继续阅读)", QMessageBox.ButtonRole.AcceptRole)
            b_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.exec()
            clicked = msg_box.clickedButton()
            
            if clicked == b_close_all:
                event.accept()
                self.quit_application()
            elif clicked == b_tray:
                event.ignore()
                self.hide()
            else:
                event.ignore()
        else:
            # 当没有在看的小说时，点击主界面的 X 直接【彻底退出程序】，不留任何后台进程！
            event.accept()
            self.quit_application()

    def quit_application(self):
        """彻底干净退出软件，释放所有后台监听线程与资源，拒绝僵尸进程"""
        for tid, info in list(getattr(self, 'download_tasks', {}).items()):
            if "worker" in info and hasattr(info["worker"], "cancel"):
                try: info["worker"].cancel()
                except Exception: pass
        if hasattr(self, 'search_worker') and self.search_worker:
            try: self.search_worker.cancel()
            except Exception: pass

        for path, win in list(self.active_reading_windows.items()):
            if win:
                try: win.close()
                except Exception: pass
        self.active_reading_windows.clear()

        # 停止全局老板键监听线程
        main_app = QApplication.instance()
        if hasattr(main_app, 'boss_mgr') and main_app.boss_mgr:
            try: main_app.boss_mgr.stop()
            except Exception: pass

        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()

        self.config_manager.save_immediately()
        QApplication.quit()
        os._exit(0)

    def force_quit_app(self):
        """托盘彻底退出"""
        self.quit_application()
