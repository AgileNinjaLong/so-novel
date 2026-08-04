import sys
import pytest
from PyQt6.QtWidgets import QApplication
from src.core.config import ConfigManager
from src.core.book import Chapter
from src.ui.floating_view import FloatingView
from src.ui.ide_pseudo_view import IDEPseudoView
from src.ui.chapter_dialog import ChapterDialog

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

def test_floating_view_toggle_boss_key(qapp, tmp_path):
    cfg_file = str(tmp_path / "cfg.json")
    cfg = ConfigManager(config_path=cfg_file)
    view = FloatingView(cfg)
    
    view.show()
    assert view.isVisible() is True

    # 触发老板键
    view.toggle_boss_key()
    assert view.isVisible() is False

    # 再次触发恢复
    view.toggle_boss_key()
    assert view.isVisible() is True

def test_ide_pseudo_view_toggle(qapp, tmp_path):
    cfg_file = str(tmp_path / "cfg.json")
    cfg = ConfigManager(config_path=cfg_file)
    ide_view = IDEPseudoView(cfg)

    ide_view.show()
    assert ide_view.isVisible() is True
    ide_view.toggle_boss_key()
    assert ide_view.isVisible() is False

def test_chapter_dialog(qapp):
    chapters = [Chapter(title=f"第{i}章", content="测试") for i in range(1, 50)]
    dialog = ChapterDialog(chapters, current_idx=5)
    assert dialog.list_widget.count() == 49
    # 模拟搜索过滤
    dialog.search_input.setText("10")
    dialog._do_filter()
    assert not dialog.list_widget.item(9).isHidden()
    assert dialog.list_widget.item(0).isHidden()

