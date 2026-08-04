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

        # 重新加载验证
        config2 = ConfigManager(config_path=tmp_path)
        assert config2.settings["boss_key"] == "Ctrl+Shift+H"
        prog = config2.get_progress("D:/books/test.txt")
        assert prog["chapter_idx"] == 5
        assert prog["line_idx"] == 12
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
