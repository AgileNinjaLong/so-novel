import json
import os
import sys
import re
import urllib.parse
from typing import List, Dict, Any, Optional
import requests
from lxml import html
import threading

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发环境下，如果是从 src/core/sonovel_client.py 运行，尝试寻找根目录
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(base_dir, relative_path)
    if os.path.exists(path):
        return path
    return os.path.join(os.path.abspath('.'), relative_path)

RULES_DIR = get_resource_path(os.path.join("SoNovel", "rules"))

_js_lock = threading.Lock()
_js_ctx = None

def _get_js_ctx():
    global _js_ctx
    if _js_ctx is None:
        from py_mini_racer import MiniRacer
        _js_ctx = MiniRacer()
    return _js_ctx

class SoNovelClient:
    def __init__(self, rules_dir: str = RULES_DIR):
        self.rules = []
        if os.path.exists(rules_dir) and os.path.isdir(rules_dir):
            for file_name in sorted(os.listdir(rules_dir)):
                if file_name.endswith('.json') and "template" not in file_name.lower():
                    full_path = os.path.join(rules_dir, file_name)
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                self.rules.extend(data)
                    except Exception as e:
                        print(f"Error loading rule file {file_name}: {e}")
        
        # 赋予每一个规则固定的序号位次，用于确定性排序
        for idx, r in enumerate(self.rules):
            r['rule_index'] = idx

        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.session.headers.update(self.headers)

    def _parse_dict_string(self, data_str: str, keyword: str = "") -> dict:
        if not data_str or data_str == "{}":
            return {}
        data_str = data_str.strip("{}")
        payload = {}
        for pair in data_str.split(','):
            if ':' in pair:
                k, v = pair.split(':', 1)
                k = k.strip()
                v = v.strip().replace('%s', keyword)
                payload[k] = v
        return payload

    def _apply_js(self, text: str, js_code: str) -> str:
        if not js_code:
            return text
        try:
            with _js_lock:
                ctx = _get_js_ctx()
                # 将当前提取的文本变量绑定到 js 的 r 变量中
                ctx.eval(f"var r = {json.dumps(text)};")
                
                # 由于 SoNovel 的 js 是直接操作 r 变量，如 r=r.replace(...)
                # 所以我们需要执行完该语句后，返回 r 的最终值
                js_script = js_code + "\n r;"
                result = ctx.eval(js_script)
                return str(result)
        except Exception as e:
            print(f"JS 执行异常: {e}\nCode: {js_code}")
            return text

    def _select_elements(self, tree, selector: str):
        if not selector:
            return []
        try:
            if selector.startswith('//') or selector.startswith('./') or selector.startswith('(/'):
                return tree.xpath(selector)
            else:
                from lxml.cssselect import CSSSelector
                return CSSSelector(selector)(tree)
        except Exception:
            return []

    def _extract_text(self, tree, rule_str: str, base_url: str = "") -> str:
        if not tree or not rule_str:
            return ""

        js_code = ""
        if '@js:' in rule_str:
            rule_str, js_code = rule_str.split('@js:', 1)

        attr = None
        if '@' in rule_str and not rule_str.startswith('//') and ']' not in rule_str.split('@')[-1]:
            rule_str, attr = rule_str.split('@', 1)

        elements = self._select_elements(tree, rule_str) if rule_str else [tree]
        if not elements:
            return ""

        element = elements[0]
        if attr:
            text = element.get(attr, "")
            if attr.lower() in ('href', 'src') and base_url:
                text = urllib.parse.urljoin(base_url, text)
        else:
            if hasattr(element, 'text_content'):
                text = element.text_content().strip()
            elif isinstance(element, str): # xpath can return strings directly
                text = element.strip()
            else:
                text = str(element).strip()

        if js_code:
            text = self._apply_js(text, js_code)

        return text

    def _search_single_rule(self, rule: dict, keyword: str) -> List[Dict[str, Any]]:
        results = []
        if rule.get("disabled", False):
            return results
        search_rule = rule.get("search")
        if not search_rule or search_rule.get("disabled", False):
            return results

        url = search_rule.get("url", "").replace('%s', urllib.parse.quote(keyword))
        method = search_rule.get("method", "get").lower()
        data_str = search_rule.get("data", "")
        data = self._parse_dict_string(data_str, keyword)
        
        cookies_str = search_rule.get("cookies", "")
        cookies = {}
        if cookies_str:
            for pair in cookies_str.split(';'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    cookies[k.strip()] = v.strip()

        try:
            if method == "post":
                resp = self.session.post(url, data=data, cookies=cookies, timeout=10)
            else:
                resp = self.session.get(url, params=data, cookies=cookies, timeout=10)
            
            if resp.encoding.lower() in ['iso-8859-1', 'us-ascii']:
                resp.encoding = resp.apparent_encoding
            
            tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))
            items = self._select_elements(tree, search_rule.get("result", ""))
            
            for item in items:
                book_name = self._extract_text(item, search_rule.get("bookName"))
                author = self._extract_text(item, search_rule.get("author"))
                latest_chap = self._extract_text(item, search_rule.get("latestChapter"))
                
                book_url = self._extract_text(item, search_rule.get("bookName") + "@href", resp.url)
                if not book_url and hasattr(item, 'get'):
                    book_url = item.get("href", "")
                
                if book_name and book_url:
                    results.append({
                        "bookName": book_name,
                        "author": author,
                        "latestChapter": latest_chap,
                        "url": book_url,
                        "sourceName": rule.get("name"),
                        "rule": rule
                    })
        except Exception:
            pass
        return results

    def test_rule_connectivity(self, rule: dict) -> bool:
        """对单本书源规则的目标 host 发起快速连通性响应测试 (2.5s 超时)"""
        if rule.get("disabled", False):
            return False
        search_rule = rule.get("search", {})
        url = search_rule.get("url", "")
        if not url:
            return False
            
        try:
            parsed = urllib.parse.urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            resp = self.session.head(base_url, timeout=2.5, allow_redirects=True)
            return resp.status_code < 500
        except Exception:
            try:
                resp = self.session.get(url.replace('%s', 'test'), timeout=2.5)
                return resp.status_code < 500
            except Exception:
                return False

    def search(self, keyword: str, callback=None, status_callback=None, cancel_event=None) -> List[Dict[str, Any]]:
        import concurrent.futures
        import difflib
        
        # 阶段 1：高并发并行预检所有书源连通性 (20 线程并发，1-2秒内完成)
        valid_rules = []
        total_rules = len(self.rules)
        completed_count = 0
        lock = threading.Lock()
        
        def _test_task(rule):
            nonlocal completed_count
            if cancel_event and cancel_event.is_set():
                return None
            is_ok = self.test_rule_connectivity(rule)
            with lock:
                completed_count += 1
                if status_callback:
                    status_callback(f"正在并发测试书源连通性 [{completed_count}/{total_rules}]: {rule.get('name', '')} {'[可用]' if is_ok else '[不可用]'}")
            return rule if is_ok else None

        if status_callback:
            status_callback(f"开始对全量 {total_rules} 个书源发起高并发连通性预检...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(_test_task, rule): rule for rule in self.rules}
            for future in concurrent.futures.as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    if status_callback:
                        status_callback("用户已中途取消预检。")
                    return []
                try:
                    res = future.result()
                    if res:
                        valid_rules.append(res)
                except Exception:
                    pass

        # 重新按照原规则序号位次排序，保持书源权重的确定性
        valid_rules.sort(key=lambda r: r.get('rule_index', 999))

        if cancel_event and cancel_event.is_set():
            if status_callback:
                status_callback("用户已中途取消搜索。")
            return []

        if status_callback:
            status_callback(f"书源连通性预检完成！成功连通 {len(valid_rules)}/{total_rules} 个可用书源，正在检索...")

        # 阶段 2：在可用书源上开展高并发检索
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(self._search_single_rule, rule, keyword): rule for rule in valid_rules}
            for future in concurrent.futures.as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    if status_callback:
                        status_callback("搜索已取消。")
                    return []
                try:
                    res = future.result()
                    if res:
                        for r in res:
                            r['ratio'] = difflib.SequenceMatcher(None, keyword, r.get('bookName', '')).ratio()
                            r['rule_index'] = r.get('rule', {}).get('rule_index', 999)
                            if callback:
                                callback(r)
                        results.extend(res)
                except Exception:
                    pass

        # 确定性多维稳定排序：相似度降序 > 规则位次升序 > 书名升序 > 书源升序
        results.sort(key=lambda x: (-round(x['ratio'], 3), x.get('rule_index', 999), x.get('bookName', ''), x.get('sourceName', '')))

        # 稳定去重
        seen_keys = set()
        deduped = []
        for r in results:
            k = (r.get('bookName', ''), r.get('author', ''), r.get('sourceName', ''))
            if k not in seen_keys:
                seen_keys.add(k)
                deduped.append(r)

        return deduped

    def get_toc(self, book_url: str, rule: dict) -> List[Dict[str, str]]:
        toc_rule = rule.get("toc", {})
        chapters = []
        
        toc_url = toc_rule.get("url", "")
        if toc_url and '%s' in toc_url:
            # 从路径中提取最后一个连续数字作为小说 ID (兼容诸如笔趣阁365等站点的特殊目录结构)
            path = urllib.parse.urlparse(book_url).path
            m = re.findall(r'\d+', path)
            if m:
                toc_url = toc_url.replace('%s', m[-1])
            else:
                toc_url = book_url
        else:
            toc_url = book_url

        current_url = toc_url
        visited = set()

        while current_url and current_url not in visited:
            visited.add(current_url)
            try:
                resp = self.session.get(current_url, timeout=10)
                if resp.encoding.lower() in ['iso-8859-1', 'us-ascii']:
                    resp.encoding = resp.apparent_encoding
                
                tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))
                base_uri = toc_rule.get("baseUri", resp.url)
                if not base_uri:
                    base_uri = resp.url
                
                items = self._select_elements(tree, toc_rule.get("item", ""))
                
                for item in items:
                    if hasattr(item, 'text_content'):
                        title = item.text_content().strip()
                        link = item.get("href", "")
                        if link:
                            full_link = urllib.parse.urljoin(base_uri, link)
                            chapters.append({"title": title, "url": full_link})
                
                # 翻页
                next_page_rule = toc_rule.get("nextPage", "")
                if next_page_rule:
                    next_url = self._extract_text(tree, next_page_rule, resp.url)
                    if next_url and next_url != current_url and next_url.startswith("http"):
                        current_url = next_url
                        continue
                break
            except Exception as e:
                break
                
        if toc_rule.get("isDesc", False):
            chapters.reverse()
            
        return chapters

    def download_chapter(self, chapter_url: str, rule: dict) -> str:
        chap_rule = rule.get("chapter", {})
        content_parts = []
        current_url = chapter_url
        visited = set()

        while current_url and current_url not in visited:
            visited.add(current_url)
            resp = None
            # 自动重试机制（最多重试3次）
            for attempt in range(3):
                try:
                    resp = self.session.get(current_url, timeout=12)
                    if resp.status_code == 200:
                        break
                except Exception:
                    if attempt < 2:
                        import time
                        time.sleep(0.5 * (attempt + 1))
                    else:
                        # 尝试直连旁路重试（绕过本地可能拥堵的 127.0.0.1 代理）
                        try:
                            resp = requests.get(current_url, headers=self.headers, timeout=12, proxies={"http": None, "https": None})
                        except Exception:
                            pass

            if not resp or resp.status_code != 200:
                return "(本章下载失败，请稍后重新下载)"

            try:
                if resp.encoding.lower() in ['iso-8859-1', 'us-ascii']:
                    resp.encoding = resp.apparent_encoding
                
                # 若需要对整个响应体使用 @js 处理 (少见但可能)
                raw_html = resp.text

                tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))
                
                # 过滤标签
                filter_tags = [t.strip() for t in chap_rule.get("filterTag", "").split(',') if t.strip()]
                for tag in filter_tags:
                    for match in self._select_elements(tree, tag):
                        match.drop_tree()
                
                content_rule = chap_rule.get("content", "")
                js_code = ""
                if '@js:' in content_rule:
                    content_rule, js_code = content_rule.split('@js:', 1)

                content_nodes = self._select_elements(tree, content_rule)
                if not content_nodes:
                    break
                    
                node = content_nodes[0]
                
                # 处理内容：SoNovel 支持将 <br> 和段落标签转为 \n
                # lxml 会保留所有文字
                if js_code:
                    raw_inner_html = html.tostring(node, encoding='unicode', method='html')
                    processed_html = self._apply_js(raw_inner_html, js_code)
                    node = html.fromstring(processed_html)
                
                # 获取纯文本，替换 <br> 为 \n
                for br in node.xpath(".//br"):
                    br.tail = "\n" + (br.tail or "")
                for p in node.xpath(".//p"):
                    p.tail = "\n" + (p.tail or "")
                    
                text = node.text_content()
                
                # 过滤正则文本
                filter_txt = chap_rule.get("filterTxt", "")
                if filter_txt:
                    text = re.sub(filter_txt, '', text)
                    
                content_parts.append("\n".join([line.strip() for line in text.splitlines() if line.strip()]))
                
                # 章节分页
                next_page_rule = chap_rule.get("nextPage", "")
                if next_page_rule:
                    next_url = self._extract_text(tree, next_page_rule, resp.url)
                    if next_url and next_url != current_url and next_url.startswith("http"):
                        current_url = next_url
                        continue
                break
            except Exception:
                return "(本章解析失败)"
                
        return "\n".join(content_parts) if content_parts else "(本章暂无内容)"
