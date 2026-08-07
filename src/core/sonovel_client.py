import json
import os
import re
import urllib.parse
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

RULES_PATH = os.path.join("SoNovel", "rules", "main.json")

class SoNovelClient:
    def __init__(self, rules_path: str = RULES_PATH):
        self.rules = []
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
        
        # 默认 headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

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

    def _extract_text(self, element, selector: str):
        if not element or not selector:
            return ""
        
        attr = None
        if '@' in selector:
            selector, attr = selector.split('@', 1)
            
        nodes = element.select(selector) if selector else [element]
        if not nodes:
            return ""
            
        if attr:
            return nodes[0].get(attr, "")
        else:
            return nodes[0].get_text(strip=True)
            
    def _extract_link(self, element, selector: str, base_url: str):
        if not element or not selector:
            return ""
        # 很多书源的 url 默认在 a 标签的 href 中
        attr = "href"
        if '@' in selector:
            selector, attr = selector.split('@', 1)
            
        nodes = element.select(selector) if selector else [element]
        if not nodes:
            return ""
        link = nodes[0].get(attr, "")
        return urllib.parse.urljoin(base_url, link)

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        results = []
        for rule in self.rules:
            if rule.get("disabled", False):
                continue
            search_rule = rule.get("search")
            if not search_rule or search_rule.get("disabled", False):
                continue

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
                    resp = requests.post(url, data=data, headers=self.headers, cookies=cookies, timeout=10)
                else:
                    resp = requests.get(url, params=data, headers=self.headers, cookies=cookies, timeout=10)
                
                # 尝试猜测正确编码
                if resp.encoding == 'ISO-8859-1':
                    resp.encoding = resp.apparent_encoding
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                items = soup.select(search_rule.get("result", ""))
                
                for item in items:
                    book_name = self._extract_text(item, search_rule.get("bookName"))
                    author = self._extract_text(item, search_rule.get("author"))
                    latest_chap = self._extract_text(item, search_rule.get("latestChapter"))
                    
                    # 小说详情页或目录页链接
                    book_url = self._extract_link(item, search_rule.get("bookName"), resp.url)
                    
                    if book_name and book_url:
                        results.append({
                            "bookName": book_name,
                            "author": author,
                            "latestChapter": latest_chap,
                            "url": book_url,
                            "sourceName": rule.get("name"),
                            "rule": rule
                        })
            except Exception as e:
                # 屏蔽超时等网络错误，继续下一个书源
                continue
                
        return results

    def get_toc(self, book_url: str, rule: dict) -> List[Dict[str, str]]:
        toc_rule = rule.get("toc", {})
        try:
            resp = requests.get(book_url, headers=self.headers, timeout=10)
            if resp.encoding == 'ISO-8859-1':
                resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            items = soup.select(toc_rule.get("item", ""))
            chapters = []
            base_uri = toc_rule.get("baseUri", resp.url)
            if not base_uri:
                base_uri = resp.url
            
            for item in items:
                title = item.get_text(strip=True)
                link = item.get("href")
                if link:
                    full_link = urllib.parse.urljoin(base_uri, link)
                    chapters.append({"title": title, "url": full_link})
                    
            if toc_rule.get("isDesc", False):
                chapters.reverse()
                
            return chapters
        except Exception as e:
            return []

    def download_chapter(self, chapter_url: str, rule: dict) -> str:
        chap_rule = rule.get("chapter", {})
        try:
            resp = requests.get(chapter_url, headers=self.headers, timeout=10)
            if resp.encoding == 'ISO-8859-1':
                resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 过滤标签
            filter_tags = [t.strip() for t in chap_rule.get("filterTag", "").split(',') if t.strip()]
            for tag in filter_tags:
                for match in soup.find_all(tag):
                    match.decompose()
            
            content_node = soup.select_one(chap_rule.get("content", ""))
            if not content_node:
                return "章节内容为空或解析失败。"
                
            text = content_node.get_text(separator="\n")
            
            # 过滤正则文本
            filter_txt = chap_rule.get("filterTxt", "")
            if filter_txt:
                text = re.sub(filter_txt, '', text)
                
            return "\n".join([line.strip() for line in text.splitlines() if line.strip()])
        except Exception as e:
            return f"下载章节异常: {e}"
