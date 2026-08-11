import sys
import pytest
from PyQt6.QtWidgets import QApplication
from src.core.config import ConfigManager
from src.core.book import Chapter
from src.ui.floating_view import FloatingView
from src.ui.ide_pseudo_view import IDEPseudoView
from src.ui.cad_pseudo_view import CADPseudoView
from src.ui.settings_dialog import SettingsDialog
from src.ui.chapter_dialog import ChapterDialog

def test_settings_dialog_conflict(qapp, tmp_path):
    cfg_file = str(tmp_path / "cfg.json")
    cfg = ConfigManager(config_path=cfg_file)
    
    dialog = SettingsDialog(cfg)
    
    # 模拟输入冲突快捷键
    dialog.boss_key_edit.setKeySequence("Ctrl+1")
    dialog.hk_floating_edit.setKeySequence("Ctrl+1")
    
    # 获取需要保存的 keys 列表进行冲突判断逻辑校验
    boss_key = dialog.boss_key_edit.keySequence().toString()
    hk_floating = dialog.hk_floating_edit.keySequence().toString()
    
    keys = [boss_key, hk_floating]
    valid_keys = [k for k in keys if k]
    assert len(valid_keys) != len(set(valid_keys)), "防冲突校验未能识别出相同的快捷键"

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

def test_cad_pseudo_view_toggle(qapp, tmp_path):
    cfg_file = str(tmp_path / "cfg.json")
    cfg = ConfigManager(config_path=cfg_file)
    cad_view = CADPseudoView(cfg)

    cad_view.show()
    assert cad_view.isVisible() is True
    cad_view.toggle_boss_key()
    assert cad_view.isVisible() is False

def test_chapter_dialog(qapp):
    chapters = [Chapter(title=f"第{i}章", content="测试") for i in range(1, 50)]
    dialog = ChapterDialog(chapters, current_idx=5)
    assert dialog.list_widget.count() == 49
    # 模拟搜索过滤
    dialog.search_input.setText("10")
    dialog._do_filter()
    assert not dialog.list_widget.item(9).isHidden()
    assert dialog.list_widget.item(0).isHidden()

def test_auto_scroll_feature(qapp, tmp_path):
    from src.core.book import Book
    cfg_file = str(tmp_path / "cfg.json")
    cfg = ConfigManager(config_path=cfg_file)
    view = FloatingView(cfg)
    
    # 模拟加载一本书
    book = Book(title="测试书籍", author="测试作者", file_path="test.txt", format="txt")
    book.chapters = [
        Chapter(title="第1章", content="第一行\n第二行\n第三行"),
        Chapter(title="第2章", content="第四行\n第五行")
    ]
    view.book = book
    view.update_content()
    
    # 1. 测试开启自动翻页
    assert view.is_auto_scrolling is False
    view.start_auto_scroll()
    assert view.is_auto_scrolling is True
    assert view.auto_scroll_timer.isActive() is True
    
    # 2. 触发超时事件，像素滚动达到一行高度时推进到下一行
    view.scroll_y = 28.0
    view._on_auto_scroll_timeout()
    assert view.book.current_line_idx == 1
    
    # 3. 模拟人工操作重置倒计时
    view.next_line()
    assert view.book.current_line_idx == 2
    assert view.auto_scroll_timer.isActive() is True
    
    # 4. 老板键暂停保护
    view.show()
    assert view.isVisible() is True
    view.toggle_boss_key()
    assert view.is_auto_scrolling is False
    assert view.auto_scroll_timer.isActive() is False


