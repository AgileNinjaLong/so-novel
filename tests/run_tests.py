import unittest
import os
import sys
import tempfile

# 确保项目根目录在 pythonpath 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.encoding import detect_file_encoding
from src.core.book import Book, Chapter
from src.core.parser import NovelParser, TxtParser
from src.core.config import ConfigManager

class TestEncoding(unittest.TestCase):
    def test_detect_utf8_encoding(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as tmp:
            tmp.write("第一章 摸鱼大作战\n这是一个UTF-8测试文本。".encode('utf-8'))
            tmp_path = tmp.name
        try:
            enc = detect_file_encoding(tmp_path)
            self.assertIn(enc.lower(), ['utf-8', 'utf-8-sig', 'ascii'])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_detect_gbk_encoding(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as tmp:
            tmp.write("第一章 斗帝陆大陆\n这是一个GBK编码的网络小说文本。".encode('gbk'))
            tmp_path = tmp.name
        try:
            enc = detect_file_encoding(tmp_path)
            self.assertIn(enc.lower(), ['gb18030', 'gbk', 'gb2312'])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

class TestParser(unittest.TestCase):
    def test_chapter_get_lines(self):
        chap = Chapter(title="第一章", content="这是第一句话。\n这是第二句话超级长长长长长长长长长长长长长长长长长长长长长长长长。")
        lines = chap.get_lines(line_length=15)
        self.assertGreater(len(lines), 2)
        self.assertIn("这是第一句话。", lines[0])

    def test_txt_parser_with_chapters(self):
        content = "第一章 初始之地\n少年走在雪地上。\n\n第二章 觉醒时刻\n风暴忽然刮起。"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            book = NovelParser.load_book(tmp_path)
            self.assertEqual(book.format, "txt")
            self.assertEqual(len(book.chapters), 2)
            self.assertEqual(book.chapters[0].title, "第一章 初始之地")
            self.assertIn("少年走在雪地上。", book.chapters[0].content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

class TestConfig(unittest.TestCase):
    def test_config_save_and_load(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
            tmp_path = tmp.name
        try:
            config = ConfigManager(config_path=tmp_path)
            config.settings["boss_key"] = "Ctrl+Shift+H"
            config.save_progress("D:/books/test.txt", chapter_idx=5, line_idx=12)
            config.save_immediately()

            config2 = ConfigManager(config_path=tmp_path)
            self.assertEqual(config2.settings["boss_key"], "Ctrl+Shift+H")
            prog = config2.get_progress("D:/books/test.txt")
            self.assertEqual(prog["chapter_idx"], 5)
            self.assertEqual(prog["line_idx"], 12)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main(verbosity=2)
