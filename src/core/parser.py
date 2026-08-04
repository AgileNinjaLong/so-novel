import os
import re
from typing import List, Optional
from src.core.book import Book, Chapter
from src.utils.encoding import detect_file_encoding

class TxtParser:
    # 兼容多种常见的中文/英文章节命名格式
    CHAPTER_PATTERNS = [
        re.compile(r'^\s*第[0-9一二三四五六七八九十百千万+]+[章卷节集部回].*', re.MULTILINE),
        re.compile(r'^\s*Chapter\s+[0-9]+.*', re.MULTILINE | re.IGNORECASE),
        re.compile(r'^\s*【第?[0-9一二三四五六七八九十百千万]+[章卷节集部回]?】.*', re.MULTILINE),
        re.compile(r'^\s*\d{1,4}[\.、\s]+.*', re.MULTILINE)
    ]

    @classmethod
    def parse(cls, file_path: str) -> Book:
        encoding = detect_file_encoding(file_path)
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()

        title = os.path.splitext(os.path.basename(file_path))[0]
        
        # 匹配最佳正则
        matches = []
        for pattern in cls.CHAPTER_PATTERNS:
            found = list(pattern.finditer(content))
            if len(found) > 1:  # 至少匹配到多章才视为主目录匹配
                matches = found
                break

        chapters: List[Chapter] = []

        if matches:
            # 检查第一章前是否有序言
            if matches[0].start() > 0:
                preface_text = content[:matches[0].start()].strip()
                if preface_text:
                    chapters.append(Chapter(title="前言/序章", content=preface_text, index=0))

            for i, match in enumerate(matches):
                chap_title = match.group(0).strip()
                start_idx = match.end()
                end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                chap_content = content[start_idx:end_idx].strip()
                if not chap_content:
                    chap_content = chap_title
                chapters.append(Chapter(title=chap_title, content=chap_content, index=len(chapters)))
        else:
            # 没有显著章节标记，按每 2000 字自动拆分为页/节
            chunk_size = 2000
            total_length = len(content)
            if total_length == 0:
                chapters.append(Chapter(title="空文件", content="该文件暂无内容。", index=0))
            else:
                num_chunks = (total_length + chunk_size - 1) // chunk_size
                for i in range(num_chunks):
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
            metadata_title = book.get_metadata('DC', 'title')
            if metadata_title and metadata_title[0] and metadata_title[0][0]:
                title = str(metadata_title[0][0])

            idx = 0
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                content_html = item.get_content().decode('utf-8', errors='ignore')
                soup = BeautifulSoup(content_html, 'html.parser')
                
                for script in soup(["script", "style"]):
                    script.extract()
                
                text = soup.get_text(separator="\n")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if not lines:
                    continue

                chap_title = lines[0] if len(lines[0]) < 40 else f"章节 {idx+1}"
                chap_body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]

                chapters.append(Chapter(title=chap_title, content=chap_body, index=idx))
                idx += 1
        except Exception as e:
            chapters = [Chapter(title="解析结果", content=f"EPUB 文件读取完成，部分内容已转译。\n原文件：{file_path}\n错误信息: {e}")]

        if not chapters:
            chapters = [Chapter(title="提示", content="EPUB 文件未解析到文本内容。")]

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
                    chapters.append(Chapter(title=f"第 {idx+1} 页", content=text.strip(), index=idx))
        except Exception as e:
            chapters = [Chapter(title="PDF 解析", content=f"无法抽取文本或受加密保护: {file_path}\n错误: {e}")]

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
            return TxtParser.parse(file_path)
