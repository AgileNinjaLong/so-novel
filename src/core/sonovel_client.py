import json
import os
import sys
import re
import time
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

_so_novel_rules_path = os.path.join("SoNovel", "rules")
_dev_rules_path = os.path.join("so-novel-main", "bundle", "rules")
RULES_DIR = get_resource_path(_so_novel_rules_path)
if not os.path.exists(RULES_DIR):
    RULES_DIR = get_resource_path(_dev_rules_path)

_js_local = threading.local()

def _get_css_selector(selector: str):
    if selector not in _css_cache:
        from lxml.cssselect import CSSSelector
        _css_cache[selector] = CSSSelector(selector)
    return _css_cache[selector]

def _get_js_ctx():
    if not hasattr(_js_local, 'ctx'):
        from py_mini_racer import MiniRacer
        _js_local.ctx = MiniRacer()
    return _js_local.ctx

_DESKTOP_OS = [
    "Windows NT 10.0; Win64; x64",
    "Windows NT 11.0; Win64; x64",
    "Macintosh; Intel Mac OS X 10_15_7",
    "X11; Linux x86_64",
    "X11; Ubuntu; Linux x86_64"
]

def generate_random_ua() -> str:
    """100% 对齐 so-novel-main RandomUA.java 生成动态伪装请求头"""
    import random
    os_str = random.choice(_DESKTOP_OS)
    browser = random.choice(["Chrome", "Firefox", "Edge", "Safari"])
    major = random.randint(115, 130)
    minor = random.randint(0, 9)
    build = random.randint(100, 999)
    
    if browser == "Chrome":
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{minor} Safari/537.36"
    elif browser == "Firefox":
        return f"Mozilla/5.0 ({os_str}; rv:{major}.0) Gecko/20100101 Firefox/{major}.0"
    elif browser == "Safari":
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    else:
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{minor} Safari/537.36 Edg/{major}.0.{build}.{minor}"

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
                                for rule in data:
                                    # 过滤掉已禁用的书源，确保全量书源数完全精确
                                    if not rule.get("disabled", False):
                                        rule["rule_file"] = file_name
                                        self.rules.append(rule)
                    except Exception as e:
                        print(f"Error loading rule file {file_name}: {e}")
        
        # 赋予每一个生效规则固定的序号位次 (0 ~ N-1)，用于确定性排序
        for idx, r in enumerate(self.rules):
            r['rule_index'] = idx

        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.session.headers.update(self.headers)

        # 30 分钟连通性缓存池
        self.connectivity_cache = {
            "timestamp": 0.0,
            "invalidated": False,
            "valid_rule_indices": [],
            "details": {}
        }

    def invalidate_rule(self, rule_index: int):
        """当搜书过程中发现原本通过测试的书源断连时，立即打回并标记缓存失效"""
        self.connectivity_cache["invalidated"] = True
        if rule_index in self.connectivity_cache["valid_rule_indices"]:
            self.connectivity_cache["valid_rule_indices"].remove(rule_index)

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

    def _execute_dsl(self, text: str, dsl: str) -> str:
        if not dsl:
            return text
        
        # 解析 DSL (如 "r=r.replace(...);@java:base64.decode()")
        steps = []
        i = 0
        while i != -1 and i < len(dsl):
            at_idx = dsl.find("@", i)
            if at_idx == -1:
                if not steps: # 只有 js代码且没有前缀时，如果是老的 js_code 逻辑进来的，当作 js
                    steps.append(("js", dsl.strip()))
                break
                
            colon_idx = dsl.find(":", at_idx)
            if colon_idx == -1:
                break
                
            lang = dsl[at_idx + 1 : colon_idx]
            next_at = dsl.find("@", colon_idx)
            code = dsl[colon_idx + 1 : next_at if next_at != -1 else len(dsl)].strip()
            steps.append((lang, code))
            i = next_at

        if not steps and dsl:
             steps.append(("js", dsl.strip()))

        result = text
        for lang, code in steps:
            if lang == "js":
                try:
                    ctx = _get_js_ctx()
                    ctx.eval(f"var r = {json.dumps(result)};")
                    result = str(ctx.eval(code + "\n r;"))
                except Exception as e:
                    print(f"JS 执行异常: {e}\nCode: {code}")
            elif lang == "java":
                if code == "base64.decode()":
                    import base64
                    try:
                        decoded_lines = []
                        for line in result.splitlines():
                            line = line.strip()
                            if line:
                                decoded_lines.append(base64.b64decode(line).decode('utf-8', errors='ignore'))
                        result = "".join(decoded_lines)
                    except Exception as e:
                        print(f"Base64 解码异常: {e}")
                else:
                    # 处理 string.replace(...)
                    import re
                    match = re.match(r"string\.replace\('([^']*)','([^']*)'\)", code)
                    if match:
                        result = result.replace(match.group(1), match.group(2))
        return result

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
        if tree is None or not rule_str:
            return ""

        dsl = ""
        at_idx = rule_str.find('@')
        if at_idx != -1 and not rule_str.startswith('//') and ']' not in rule_str[at_idx:]:
            # 区分属性提取 @href 与 DSL 提取 @js: / @java:
            if rule_str[at_idx:].startswith("@js:") or rule_str[at_idx:].startswith("@java:"):
                dsl = rule_str[at_idx:]
                rule_str = rule_str[:at_idx]
            else:
                # 可能是属性提取如 @href
                pass

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

        if dsl:
            text = self._execute_dsl(text, dsl)

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
            
            # 【100% 对齐 so-novel-main SearchParser.java】
            # 部分书源搜索完全匹配时会直接重定向到详情页 (result 列表为空，但书名选择器能匹配到页面元素)
            book_rule = rule.get("book", {})
            book_name_sel = book_rule.get("bookName", "")
            if not items and book_name_sel and self._select_elements(tree, book_name_sel):
                book_name = self._extract_text(tree, book_name_sel)
                author = self._extract_text(tree, book_rule.get("author", ""))
                latest_chap = self._extract_text(tree, book_rule.get("latestChapter", ""))
                if book_name:
                    results.append({
                        "bookName": book_name,
                        "author": author,
                        "latestChapter": latest_chap,
                        "url": resp.url,
                        "sourceName": rule.get("name"),
                        "rule": rule
                    })
                    return results

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
            # 搜书网络异常：立即将该书源从 30 分钟连通缓存打回失效！
            r_idx = rule.get("rule_index", 999)
            self.invalidate_rule(r_idx)
            
        return results

    def test_rule_connectivity(self, rule: dict, cancel_event=None) -> tuple[bool, int]:
        """对单本书源规则的目标 host 发起快速连通性响应测试 (单次 5.0s 超时)，返回 (is_ok, latency_ms)"""
        if cancel_event and cancel_event.is_set():
            return False, 0
        if rule.get("disabled", False):
            return False, 0
        search_rule = rule.get("search", {})
        url = search_rule.get("url", "")
        if not url:
            return False, 0

        ignore_ssl = rule.get("ignoreSsl", False)
        import time
        t0 = time.time()
        try:
            parsed = urllib.parse.urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            resp = self.session.get(base_url, timeout=(2.5, 2.5), allow_redirects=True, verify=not ignore_ssl)
            latency = int((time.time() - t0) * 1000)
            if resp.status_code < 500:
                return True, latency
        except Exception:
            pass

        if cancel_event and cancel_event.is_set():
            return False, 0

        try:
            t1 = time.time()
            test_url = url.replace('%s', urllib.parse.quote('天'))
            resp = self.session.get(test_url, timeout=(2.5, 2.5), verify=not ignore_ssl)
            latency = int((time.time() - t1) * 1000)
            return resp.status_code < 500, latency
        except Exception:
            return False, 0

    def search(self, keyword: str, search_type: str = "smart", callback=None, status_callback=None, cancel_event=None, rule_tested_callback=None, test_finished_callback=None) -> List[Dict[str, Any]]:
        import concurrent.futures
        import difflib
        import time
        
        results = []
        valid_rules = []
        total_rules = len(self.rules)

        now = time.time()
        cache_age = now - self.connectivity_cache.get("timestamp", 0.0)
        is_cache_valid = (cache_age < 1800) and (not self.connectivity_cache.get("invalidated", False)) and bool(self.connectivity_cache.get("valid_rule_indices"))

        if is_cache_valid:
            valid_indices = set(self.connectivity_cache.get("valid_rule_indices", []))
            valid_rules = [r for r in self.rules if r.get('rule_index', 999) in valid_indices]
            if status_callback:
                status_callback(f"复用 30 分钟内连通性缓存 (已验证 {len(valid_rules)} 个可用书源，0 秒闪速搜索)...")
            if rule_tested_callback:
                for r in self.rules:
                    r_idx = r.get('rule_index', 999)
                    is_ok = r_idx in valid_indices
                    lat = self.connectivity_cache.get("details", {}).get(r_idx, {}).get("latency_ms", 100)
                    rule_tested_callback(r_idx, r.get('name', ''), is_ok, lat if is_ok else 0)

            if test_finished_callback:
                test_finished_callback()

            # 阶段 2：在已验证书源上检索
            search_executor = concurrent.futures.ThreadPoolExecutor(max_workers=15)
            try:
                futures = {search_executor.submit(self._search_single_rule, rule, keyword): rule for rule in valid_rules}
                for future in concurrent.futures.as_completed(futures):
                    if cancel_event and cancel_event.is_set():
                        search_executor.shutdown(wait=False, cancel_futures=True)
                        return []
                    try:
                        res = future.result()
                        if res:
                            for r in res:
                                r['ratio'] = difflib.SequenceMatcher(None, keyword, r.get('bookName', '')).ratio()
                                r['rule_index'] = r.get('rule', {}).get('rule_index', 999)
                                if callback and not (cancel_event and cancel_event.is_set()):
                                    callback(r)
                            results.extend(res)
                    except Exception:
                        pass
            finally:
                if not (cancel_event and cancel_event.is_set()):
                    search_executor.shutdown(wait=False)

        else:
            # 流水线模式：测试线程与搜书线程并行！只要书源连通测试一通过，立刻发起该书源搜书！
            test_executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)
            search_executor = concurrent.futures.ThreadPoolExecutor(max_workers=15)
            search_futures = []
            details_cache = {}
            lock = threading.Lock()

            def _search_pipeline(rule):
                if cancel_event and cancel_event.is_set():
                    return
                is_ok, latency_ms = self.test_rule_connectivity(rule, cancel_event=cancel_event)
                r_idx = rule.get('rule_index', 999)
                r_name = rule.get('name', '未知')

                with lock:
                    details_cache[r_idx] = {"is_ok": is_ok, "latency_ms": latency_ms}

                if rule_tested_callback and not (cancel_event and cancel_event.is_set()):
                    rule_tested_callback(r_idx, r_name, is_ok, latency_ms)

                if is_ok and not (cancel_event and cancel_event.is_set()):
                    with lock:
                        valid_rules.append(rule)
                    # 连通测试一通过，立刻提交该书源的关键词搜书！
                    f = search_executor.submit(self._search_single_rule, rule, keyword)
                    with lock:
                        search_futures.append(f)

            if status_callback:
                status_callback(f"开始对全量 {total_rules} 个书源发起表格嵌入式流水线测试与检索...")

            try:
                test_futures = [test_executor.submit(_search_pipeline, rule) for rule in self.rules]
                for future in concurrent.futures.as_completed(test_futures):
                    if cancel_event and cancel_event.is_set():
                        test_executor.shutdown(wait=False, cancel_futures=True)
                        search_executor.shutdown(wait=False, cancel_futures=True)
                        return []

                if test_finished_callback and not (cancel_event and cancel_event.is_set()):
                    test_finished_callback()

                # 等待所有已发起的搜书任务完成并收集结果
                for f in list(search_futures):
                    if cancel_event and cancel_event.is_set():
                        search_executor.shutdown(wait=False, cancel_futures=True)
                        return []
                    try:
                        res = f.result()
                        if res:
                            for r in res:
                                if callback and not (cancel_event and cancel_event.is_set()):
                                    callback(r)
                            results.extend(res)
                    except Exception:
                        pass
            finally:
                if not (cancel_event and cancel_event.is_set()):
                    test_executor.shutdown(wait=False)
                    search_executor.shutdown(wait=False)

            valid_rules.sort(key=lambda r: r.get('rule_index', 999))

            # 更新 30 分钟缓存
            if not (cancel_event and cancel_event.is_set()):
                self.connectivity_cache["timestamp"] = time.time()
                self.connectivity_cache["invalidated"] = False
                self.connectivity_cache["valid_rule_indices"] = [r.get('rule_index', 999) for r in valid_rules]
                self.connectivity_cache["details"] = details_cache

        # 【100% 完全对齐 so-novel-main SearchResultsHandler.java 算法】
        # 预计算书名与作者相似度，并自动判定关键字是书名还是作者
        kw_str = keyword.strip()
        book_sim_list = []
        author_sim_list = []
        sim_map = {}

        import difflib
        for r in results:
            b_name = r.get('bookName', '') or ''
            author = r.get('author', '') or ''
            s_b = difflib.SequenceMatcher(None, kw_str, b_name).ratio()
            s_a = difflib.SequenceMatcher(None, kw_str, author).ratio()
            sim_map[id(r)] = (s_b, s_a)
            book_sim_list.append(s_b)
            author_sim_list.append(s_a)

        def _weight(s: float, is_short: bool, is_long: bool) -> float:
            if is_short:
                if s == 1.0: return 12.0
                if s >= 0.8: return (s ** 3) * 8.0
                if s >= 0.7: return s * 5.0
                return 0.0
            if is_long:
                if s == 1.0: return 10.0
                if s >= 0.85: return (s ** 3) * 8.0
                if s >= 0.7: return (s ** 2) * 5.0
                if s >= 0.5: return s * 3.0
                return s * 1.2
            if s == 1.0: return 10.0
            if s >= 0.85: return (s ** 3) * 8.0
            if s >= 0.7: return (s ** 2) * 5.0
            if s >= 0.5: return s * 3.0
            return 0.0

        def _compute_weight(sim_list: list) -> float:
            is_short = len(kw_str) <= 4
            is_long = len(kw_str) >= 10
            return sum(_weight(s, is_short, is_long) for s in sim_list)

        if search_type == "author":
            is_author_search = True
        elif search_type == "title":
            is_author_search = False
        else:
            is_author_search = _compute_weight(book_sim_list) < _compute_weight(author_sim_list)

        for r in results:
            s_b, s_a = sim_map[id(r)]
            r['ratio'] = s_a if is_author_search else s_b
            r['rule_index'] = r.get('rule', {}).get('rule_index', 999)

        # 降序排序 + 低相似度 (<=0.25) 过滤
        filtered = [r for r in results if r.get('ratio', 0.0) > 0.25]
        if not filtered:
            filtered = [r for r in results if r.get('ratio', 0.0) > 0.0]

        target_list = filtered if filtered else results
        target_list.sort(key=lambda x: (
            -round(x.get('ratio', 0.0), 3),
            x.get('bookName', '') if is_author_search else x.get('author', ''),
            x.get('rule_index', 999)
        ))

        # 稳定去重
        seen_keys = set()
        deduped = []
        for r in target_list:
            k = (r.get('bookName', ''), r.get('author', ''), r.get('sourceName', ''))
            if k not in seen_keys:
                seen_keys.add(k)
                deduped.append(r)

        return deduped

    def get_toc(self, book_url: str, rule: dict, cancel_event: Optional[threading.Event] = None, session: Optional[requests.Session] = None) -> List[Dict[str, str]]:
        if session is None:
            session = self.session

        toc_rule = rule.get("toc", {})
        chapters = []

        toc_url = toc_rule.get("url", "")
        if toc_url and '%s' in toc_url:
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
            if cancel_event and cancel_event.is_set():
                break
            visited.add(current_url)
            resp = None
            for attempt in range(3):
                if cancel_event and cancel_event.is_set():
                    break
                try:
                    resp = session.get(current_url, timeout=10)
                    if resp.status_code == 200:
                        break
                except Exception:
                    if cancel_event and cancel_event.is_set():
                        break
                    time.sleep(0.3)

            if cancel_event and cancel_event.is_set():
                break

            if not resp or resp.status_code != 200:
                break

            try:
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
                
                # 目录翻页 (补全相对路径 urljoin 拼接，防止跨页书源遗漏后半段章节)
                next_page_rule = toc_rule.get("nextPage", "")
                if next_page_rule:
                    next_url = self._extract_text(tree, next_page_rule, resp.url)
                    if next_url and not next_url.startswith("http"):
                        next_url = urllib.parse.urljoin(resp.url, next_url)
                    if next_url and next_url != current_url and next_url.startswith("http"):
                        current_url = next_url
                        continue
                break
            except Exception:
                break
                
        # 章节全量去重与倒序排列矫正 (防止因最新章节区块重复包含导致跳章/缺失)
        seen_urls = set()
        unique_chapters = []
        for chap in chapters:
            u = chap.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                unique_chapters.append(chap)

        if toc_rule.get("isDesc", False):
            unique_chapters.reverse()

        return unique_chapters

    def download_chapter(self, chapter_url: str, rule: dict, session=None, cancel_event=None, min_interval: float = 0.2, max_interval: float = 0.4, chap_title: str = "") -> str:
        import random
        from lxml import html
        chap_rule = rule.get("chapter", {})
        ignore_ssl = rule.get("ignoreSsl", False)
        content_parts = []
        current_url = chapter_url
        visited = set()
        
        req_session = session if session else self.session

        while current_url and current_url not in visited:
            if cancel_event and cancel_event.is_set():
                break
            visited.add(current_url)
            resp = None
            parsed = urllib.parse.urlparse(current_url)
            
            # 【100% 对齐 so-novel-main CrawlUtils.java】动态注入真实浏览器随机 UA 与防爬头
            req_headers = {
                "User-Agent": generate_random_ua(),
                "Referer": f"{parsed.scheme}://{parsed.netloc}/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }

            # 【对齐 so-novel-main ChapterParser.java】单线程原生就地重试机制，避免失败流入后备退避
            for attempt in range(1, 4):
                if cancel_event and cancel_event.is_set():
                    break
                try:
                    # 每次重试间隔递增
                    if attempt > 1:
                        time.sleep(random.uniform(0.8, 1.8) * attempt)
                    elif max_interval > 0:
                        time.sleep(random.uniform(min_interval, max_interval))

                    resp = req_session.get(current_url, headers=req_headers, timeout=(5.0, 10.0), verify=not ignore_ssl)
                    if resp.status_code == 200:
                        break
                    elif resp.status_code in (429, 502, 503, 504, 403):
                        # 触发反爬限流时，更新 UA 继续就地重试
                        req_headers["User-Agent"] = generate_random_ua()
                except Exception:
                    req_headers["User-Agent"] = generate_random_ua()

            if not resp or resp.status_code != 200:
                return "(本章下载失败)"

            try:
                if resp.encoding.lower() in ['iso-8859-1', 'us-ascii']:
                    resp.encoding = resp.apparent_encoding
                
                tree = html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))
                filter_tags = [t.strip() for t in chap_rule.get("filterTag", "").split(',') if t.strip()]
                for tag in filter_tags:
                    for match in self._select_elements(tree, tag):
                        match.drop_tree()
                
                content_rule = chap_rule.get("content", "")
                dsl = ""
                at_idx = content_rule.find('@')
                if at_idx != -1 and (content_rule[at_idx:].startswith("@js:") or content_rule[at_idx:].startswith("@java:")):
                    dsl = content_rule[at_idx:]
                    content_rule = content_rule[:at_idx]

                content_nodes = self._select_elements(tree, content_rule)
                if not content_nodes:
                    break
                    
                node = content_nodes[0]
                if dsl:
                    raw_inner_html = html.tostring(node, encoding='unicode', method='html')
                    processed_html = self._execute_dsl(raw_inner_html, dsl)
                    node = html.fromstring(processed_html)
                
                for br in node.xpath(".//br"):
                    br.tail = "\n" + (br.tail or "")
                for p in node.xpath(".//p"):
                    p.tail = "\n" + (p.tail or "")
                    
                text = node.text_content()
                # 【对齐 so-novel-main CrawlUtils.java】清理控制符与私有区不可见字符
                text = re.sub(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\ufeff]', '', text)

                # 擦除正文开头重复出现的章节标题
                if chap_title and text.startswith(chap_title):
                    text = text[len(chap_title):].lstrip()

                filter_txt = chap_rule.get("filterTxt", "")
                if filter_txt:
                    text = re.sub(filter_txt, '', text)
                    
                content_parts.append("\n".join([line.strip() for line in text.splitlines() if line.strip()]))

                # 章节多页分页 nextPage 处理
                next_url = None
                next_page_in_js = chap_rule.get("nextPageInJs", "")
                next_page_rule = chap_rule.get("nextPage", "")
                next_els = self._select_elements(tree, next_page_rule) if next_page_rule else []
                
                if next_page_in_js:
                    next_url = self._extract_text(tree, next_page_in_js, resp.url)
                elif next_page_rule:
                    next_url = self._extract_text(tree, next_page_rule, resp.url)
                    
                if next_url:
                    if not next_url.startswith("http"):
                        next_url = urllib.parse.urljoin(resp.url, next_url)

                    # 判断是否为分页最后一页
                    is_last = False
                    next_chapter_link = chap_rule.get("nextChapterLink", "")
                    if next_chapter_link and re.match(next_chapter_link, next_url):
                        is_last = True
                    else:
                        next_els_text = next_els[0].text_content() if next_els and hasattr(next_els[0], 'text_content') else ""
                        if next_els_text and not re.match(r".*[-_]\d\.html", next_url) and re.match(r".*(下一章|没有了|>>|书末页).*", next_els_text):
                            is_last = True

                    if not is_last and next_url != current_url:
                        current_url = next_url
                        continue
                break
            except Exception:
                return "(本章解析失败)"
                
        return "\n".join(content_parts) if content_parts else "(本章暂无内容)"
