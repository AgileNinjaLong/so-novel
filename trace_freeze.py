import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread
from src.core.sonovel_client import SoNovelClient
import concurrent.futures

class DebugClient(SoNovelClient):
    def _search_single_rule(self, rule, keyword):
        name = rule.get("name", "Unknown")
        print(f"[{name}] Starting...")
        try:
            import requests
            from lxml import html
            import urllib.parse
            
            search_rule = rule.get("search", {})
            url = search_rule.get("url", "").replace('%s', urllib.parse.quote(keyword))
            method = search_rule.get("method", "get").lower()
            data = self._parse_dict_string(search_rule.get("data", ""), keyword)
            
            print(f"[{name}] Requesting...")
            if method == "post":
                resp = requests.post(url, data=data, headers=self.headers, timeout=10)
            else:
                resp = requests.get(url, params=data, headers=self.headers, timeout=10)
                
            print(f"[{name}] Request done, status: {resp.status_code}. Parsing...")
            if resp.encoding.lower() in ['iso-8859-1', 'us-ascii']:
                resp.encoding = resp.apparent_encoding
            
            tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))
            print(f"[{name}] Selecting items...")
            items = self._select_elements(tree, search_rule.get("result", ""))
            print(f"[{name}] Items found: {len(items)}")
            return []
        except Exception as e:
            print(f"[{name}] Error: {e}")
            return []

class DummyWorker(QThread):
    def run(self):
        c = DebugClient()
        c.search("斗破")

app = QApplication(sys.argv)
worker = DummyWorker()
worker.start()

import threading
def timeout():
    import time
    time.sleep(15)
    print("Timeout!")
    app.quit()
threading.Thread(target=timeout, daemon=True).start()
app.exec()
