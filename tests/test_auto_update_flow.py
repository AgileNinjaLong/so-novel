import unittest
import os
import tempfile
import time
from src.core.config import ConfigManager, DEFAULT_CONFIG_PATH
from src.core.db_manager import DatabaseManager, DEFAULT_DB_PATH
from src.core.sonovel_client import SoNovelClient
from src.ui.bookshelf_window import AutoUpdateWorker

class TestAutoUpdateVerification(unittest.TestCase):
    def test_paths_in_project_directory(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertTrue(DEFAULT_CONFIG_PATH.startswith(root_dir))
        self.assertTrue(DEFAULT_DB_PATH.startswith(root_dir))
        print(f"Verified Config Path: {DEFAULT_CONFIG_PATH}")
        print(f"Verified DB Path: {DEFAULT_DB_PATH}")

    def test_database_auto_update(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "test_novelread.db")
        db = DatabaseManager(db_path)

        task = {
            "task_id": "task_auto_1",
            "book_title": "测试追更小说",
            "author": "测试作者",
            "url": "https://example.com/book/1",
            "source_name": "测试书源",
            "export_mode": "txt",
            "save_path": "/tmp/test.txt",
            "status": "COMPLETED",
            "status_text": "✅ 已完成",
            "progress_current": 10,
            "progress_total": 10,
            "is_auto_update": 1
        }
        db.add_or_update_task(task)
        tasks = db.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["is_auto_update"], 1)

        db.set_auto_update("task_auto_1", 0)
        tasks = db.get_all_tasks()
        self.assertEqual(tasks[0]["is_auto_update"], 0)

        temp_dir.cleanup()

    def test_config_source_type_distinction(self):
        temp_dir = tempfile.TemporaryDirectory()
        cfg_path = os.path.join(temp_dir.name, "test_config.json")
        cfg = ConfigManager(cfg_path)

        p1 = os.path.abspath(os.path.join(temp_dir.name, "net.txt"))
        p2 = os.path.abspath(os.path.join(temp_dir.name, "local.txt"))

        # 模拟增加网络下载小说与本地导入小说
        cfg.add_to_bookshelf(p1, {
            "title": "网络小说", "author": "作者A", "format": "txt",
            "source_type": "network", "url": "http://example.com", "is_auto_update": 1
        })

        cfg.add_to_bookshelf(p2, {
            "title": "本地小说", "author": "作者B", "format": "txt",
            "source_type": "local", "is_auto_update": 0
        })

        shelf = cfg.get_bookshelf()
        self.assertEqual(shelf[p1]["source_type"], "network")
        self.assertEqual(shelf[p1]["is_auto_update"], 1)
        self.assertEqual(shelf[p2]["source_type"], "local")
        self.assertEqual(shelf[p2]["is_auto_update"], 0)

        temp_dir.cleanup()

if __name__ == "__main__":
    unittest.main()
