import unittest
import os
import tempfile
from src.core.db_manager import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_novelread.db")
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_get_delete_task(self):
        task = {
            "task_id": "task_1001",
            "book_title": "剑来",
            "author": "烽火戏诸侯",
            "url": "https://example.com/book/123/",
            "source_name": "东滩小说",
            "export_mode": "epub",
            "save_path": "/tmp/jianlai.epub",
            "status": "COMPLETED",
            "status_text": "✅ 已自动入库我的藏书",
            "progress_current": 100,
            "progress_total": 100,
            "rule": {"name": "东滩小说"},
            "book_info": {"bookName": "剑来", "author": "烽火戏诸侯"}
        }

        self.db.add_or_update_task(task)
        tasks = self.db.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "task_1001")
        self.assertEqual(tasks[0]["book_title"], "剑来")
        self.assertEqual(tasks[0]["author"], "烽火戏诸侯")
        self.assertEqual(tasks[0]["url"], "https://example.com/book/123/")

        self.db.update_task_status("task_1001", "CANCELLED", "⛔ 已手动取消")
        tasks = self.db.get_all_tasks()
        self.assertEqual(tasks[0]["status"], "CANCELLED")
        self.assertEqual(tasks[0]["status_text"], "⛔ 已手动取消")

        self.db.delete_task("task_1001")
        tasks = self.db.get_all_tasks()
        self.assertEqual(len(tasks), 0)

if __name__ == "__main__":
    unittest.main()
