import os
import tempfile
import pytest
from src.core.book import Book, Chapter
from src.core.parser import NovelParser, TxtParser

def test_chapter_get_lines():
    chap = Chapter(title="第一章", content="这是第一句话。\n这是第二句话超级长长长长长长长长长长长长长长长长长长长长长长长长。")
    lines = chap.get_lines(line_length=15)
    assert len(lines) > 2
    assert "这是第一句话。" in lines[0]

def test_txt_parser_with_chapters():
    content = """
第一章 初始之地
少年走在雪地上。

第二章 觉醒时刻
风暴忽然刮起。
"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as tmp:
        tmp.write(content.strip())
        tmp_path = tmp.name

    try:
        book = NovelParser.load_book(tmp_path)
        assert book.format == "txt"
        assert len(book.chapters) == 2
        assert book.chapters[0].title == "第一章 初始之地"
        assert "少年走在雪地上。" in book.chapters[0].content
        assert book.chapters[1].title == "第二章 觉醒时刻"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_txt_parser_without_chapters():
    content = "这是一段没有明显章节分割符的小说正文内容。" * 200
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        book = NovelParser.load_book(tmp_path)
        assert len(book.chapters) >= 1
        assert "第 1 页" in book.chapters[0].title
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
