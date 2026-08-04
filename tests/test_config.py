import os
import tempfile
import pytest
from src.core.config import ConfigManager

def test_config_save_and_load():
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
        tmp_path = tmp.name

    try:
        config = ConfigManager(config_path=tmp_path)
        config.settings["boss_key"] = "Ctrl+Shift+H"
        config.save_progress("D:/books/test.txt", chapter_idx=5, line_idx=12)
        config.save_immediately()

        # 重新加载验证
        config2 = ConfigManager(config_path=tmp_path)
        assert config2.settings["boss_key"] == "Ctrl+Shift+H"
        prog = config2.get_progress("D:/books/test.txt")
        assert prog["chapter_idx"] == 5
        assert prog["line_idx"] == 12
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_last_file_handling():
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp_cfg:
        cfg_path = tmp_cfg.name
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp_book:
        book_path = tmp_book.name

    try:
        config = ConfigManager(config_path=cfg_path)
        config.save_progress(book_path, 1, 1)
        assert config.get_last_file() == book_path

        # 删除临时书籍文件
        os.remove(book_path)

        # 再次获取，应该自动清除并返回 None
        assert config.get_last_file() is None
        assert config.settings["last_file"] == ""
    finally:
        if os.path.exists(cfg_path):
            os.remove(cfg_path)
        if os.path.exists(book_path):
            os.remove(book_path)

