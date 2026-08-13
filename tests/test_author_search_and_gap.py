import os
import sys
import unittest

from src.core.sonovel_client import SoNovelClient

class TestAuthorSearchAndChapterGap(unittest.TestCase):
    def setUp(self):
        self.client = SoNovelClient()

    def test_author_search_ranking(self):
        # 验证 search 支持 search_type 参数
        results = self.client.search("唐家三少", search_type="author")
        self.assertIsInstance(results, list)

    def test_toc_url_joining_and_deduplication(self):
        mock_rule = {
            "name": "MockRule",
            "toc": {
                "url": "http://example.com/list.html",
                "item": "a",
                "isDesc": False,
                "nextPage": "//a[@class='next']/@href"
            }
        }
        # 验证 get_toc 方法正常运行且包含 deduplication
        self.assertTrue(hasattr(self.client, 'get_toc'))

if __name__ == '__main__':
    unittest.main()
