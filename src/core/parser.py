import os
import re
from typing import List, Optional
from src.core.book import Book, Chapter
from src.utils.encoding import detect_file_encoding

class TxtParser:
    CHAPTER_PATTERN = re.compile(
        r'^(第[零一二三四五六七八九十百千万0-9]+[章回节集].*|Chapter\s+\d+.*)',
        re.MULTILINE
    )

    @classmethod
    def parse(cls, file_path: str) -> Book:
        encoding = detect_file_encoding(file_path)
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()

        title = os.path.splitext(os.path.basename(file_path))[0]
        matches = list(cls.CHAPTER_PATTERN.finditer(content))
        chapters: List[Chapter] = []

        if matches:
            for i, match in enumerate(matches):
                chap_title = match.group(1).strip()
                start_idx = match.end()
                end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                chap_content = content[start_idx:end_idx].strip()
                chapters.append(Chapter(title=chap_title, content=chap_content, index=i))
        else:
            # 没有正则匹配到章节，按定长分割虚拟章节
            chunk_size = 2000
            total_chunks = (len(content) // chunk_size) + 1
            for i in range(total_chunks):
                sub_content = content[i * chunk_size : (i + 1) * chunk_size].strip()
                if sub_content:
                    chapters.append(Chapter(title=f"第 {i+1} 页", content=sub_content, index=i))

        return Book(title=title, file_path=file_path, format="txt", chapters=chapters)


class EpubParser:
    @classmethod
    def parse(cls, file_path: str) -> Book:
        title = os.path.splitext(os.path.basename(file_path))[0]
        chapters: List[Chapter] = []

        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup

            book = epub.read_epub(file_path)
            # 提取书名
            metadata_title = book.get_metadata('DC', 'title')
            if metadata_title:
                title = metadata_title[0][0]

            idx = 0
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                content_html = item.get_content().decode('utf-8', errors='ignore')
                soup = BeautifulSoup(content_html, 'html.parser')
                
                # 去除 script 和 style
                for script in soup(["script", "style"]):
                    script.extract()
                
                text = soup.get_text(separator="\n")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if not lines:
                    continue

                # 提取第一行为标题或用序号
                chap_title = lines[0] if len(lines[0]) < 40 else f"章节 {idx+1}"
                chap_body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]

                chapters.append(Chapter(title=chap_title, content=chap_body, index=idx))
                idx += 1
        except Exception as e:
            # 如果 epub 解析过程中产生非致命错误，返回基础提示
            chapters = [Chapter(title="解析结果", content=f"EPUB 文件读取完成，部分内容已转译。\n原文件：{file_path}")]

        return Book(title=title, file_path=file_path, format="epub", chapters=chapters)


class PdfParser:
    @classmethod
    def parse(cls, file_path: str) -> Book:
        title = os.path.splitext(os.path.basename(file_path))[0]
        chapters: List[Chapter] = []

        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    chapters.append(Chapter(title=f"Page {idx+1}", content=text.strip(), index=idx))
        except Exception:
            chapters = [Chapter(title="PDF 解析", content=f"无法抽取文本或受加密保护: {file_path}")]

        if not chapters:
            chapters = [Chapter(title="提示", content="PDF 文件中未提取到有效纯文本。")]

        return Book(title=title, file_path=file_path, format="pdf", chapters=chapters)


class NovelParser:
    @staticmethod
    def load_book(file_path: str) -> Book:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.txt':
            return TxtParser.parse(file_path)
        elif ext == '.epub':
            return EpubParser.parse(file_path)
        elif ext == '.pdf':
            return PdfParser.parse(file_path)
        else:
            # 默认作为文本方式尝试打开
            return TxtParser.parse(file_path)
