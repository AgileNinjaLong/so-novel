import os
import tempfile
import pytest
from src.utils.encoding import detect_file_encoding

def test_detect_utf8_encoding():
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as tmp:
        tmp.write("第一章 摸鱼大作战\n这是一个UTF-8测试文本。".encode('utf-8'))
        tmp_path = tmp.name
    
    try:
        enc = detect_file_encoding(tmp_path)
        assert enc.lower() in ['utf-8', 'utf-8-sig', 'ascii']
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_detect_gbk_encoding():
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as tmp:
        tmp.write("第一章 斗帝陆大陆\n这是一个GBK编码的网络小说文本。".encode('gbk'))
        tmp_path = tmp.name
        
    try:
        enc = detect_file_encoding(tmp_path)
        assert enc.lower() in ['gb18030', 'gbk', 'gb2312']
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
