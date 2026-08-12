import sqlite3
import os
import json
import time
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".novelread", "novelread.db")

class DatabaseManager:
    """SQLite 数据库管理器：持久化保存小说下载管理任务、书籍信息、作者、下载链接等核心元数据"""
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS download_tasks (
                    task_id TEXT PRIMARY KEY,
                    book_title TEXT NOT NULL,
                    author TEXT,
                    url TEXT NOT NULL,
                    source_name TEXT,
                    export_mode TEXT,
                    save_path TEXT NOT NULL,
                    status TEXT,
                    status_text TEXT,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    rule_json TEXT,
                    book_info_json TEXT,
                    create_time TEXT,
                    update_time TEXT
                )
            """)
            conn.commit()

    def add_or_update_task(self, task: Dict[str, Any]):
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO download_tasks (
                    task_id, book_title, author, url, source_name, export_mode,
                    save_path, status, status_text, progress_current, progress_total,
                    rule_json, book_info_json, create_time, update_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    status_text=excluded.status_text,
                    progress_current=excluded.progress_current,
                    progress_total=excluded.progress_total,
                    update_time=excluded.update_time
            """, (
                task["task_id"],
                task.get("book_title", "未知"),
                task.get("author", "未知"),
                task.get("url", ""),
                task.get("source_name", "未知"),
                task.get("export_mode", "epub"),
                task.get("save_path", ""),
                task.get("status", "PENDING"),
                task.get("status_text", "⏳ 准备下载..."),
                task.get("progress_current", 0),
                task.get("progress_total", 0),
                json.dumps(task.get("rule", {}), ensure_ascii=False),
                json.dumps(task.get("book_info", {}), ensure_ascii=False),
                task.get("create_time", now_str),
                now_str
            ))
            conn.commit()

    def update_task_progress(self, task_id: str, status_text: str, current: int, total: int):
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE download_tasks SET
                    status_text = ?,
                    progress_current = ?,
                    progress_total = ?,
                    status = 'DOWNLOADING',
                    update_time = ?
                WHERE task_id = ?
            """, (status_text, current, total, now_str, task_id))
            conn.commit()

    def update_task_status(self, task_id: str, status: str, status_text: str):
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE download_tasks SET
                    status = ?,
                    status_text = ?,
                    update_time = ?
                WHERE task_id = ?
            """, (status, status_text, now_str, task_id))
            conn.commit()

    def delete_task(self, task_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM download_tasks WHERE task_id = ?", (task_id,))
            conn.commit()

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM download_tasks ORDER BY create_time DESC")
            rows = cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                if item.get("rule_json"):
                    try: item["rule"] = json.loads(item["rule_json"])
                    except Exception: item["rule"] = {}
                if item.get("book_info_json"):
                    try: item["book_info"] = json.loads(item["book_info_json"])
                    except Exception: item["book_info"] = {}
                result.append(item)
            return result
