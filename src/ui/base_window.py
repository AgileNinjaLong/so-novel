import os
import sys
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QRect
from PyQt6.QtWidgets import QWidget, QMenu, QFileDialog, QDialog
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QKeyEvent, QMouseEvent, QCursor, QWheelEvent, QShortcut, QKeySequence

from src.core.parser import NovelParser
from src.core.book import Book
from src.ui.chapter_dialog import ChapterDialog
from src.ui.settings_dialog import SettingsDialog
from src.ui.download_dialog import DownloadDialog

ALL_STEALTH_MODES = [
    ("floating", "📖 极简透明悬浮窗模式", "hk_floating", "Ctrl+1"),
    ("ide_pseudo", "💻 VS Code 代码编辑器模式", "hk_ide", "Ctrl+2"),
    ("cad_pseudo", "📐 CAD 建筑图纸命令行模式", "hk_cad", "Ctrl+3"),
    ("excel_sheet", "📊 Excel 电子表格模式", "hk_excel", ""),
    ("word_doc", "📄 Word 办公文档草稿模式", "hk_word", ""),
    ("terminal_cli", "🖥️ PowerShell 终端日志模式", "hk_terminal", ""),
    ("outlook_email", "✉️ Outlook 工作邮件客户端模式", "hk_outlook", ""),
    ("swagger_api", "🔌 Swagger API 接口文档模式", "hk_swagger", ""),
    ("git_diff", "🔀 Git Commit Diff 版本控制模式", "hk_git", ""),
    ("notion_markdown", "📓 Notion / Markdown 工作笔记模式", "hk_notion", ""),
    ("pdf_reader", "📑 PDF 学术论文阅读器模式", "hk_pdf", ""),
    ("stock_kline", "📈 股票 K 线行情看板模式", "hk_stock", ""),
    ("json_validator", "🔍 JSON 格式化报文校验模式", "hk_json", ""),
    ("sys_monitor", "📊 任务管理器性能监控模式", "hk_sysmon", ""),
    ("calculator_gui", "🧮 财务科学计算器模式", "hk_calc", ""),
    ("database_dbeaver", "🗄️ SQL 数据库控制台结果集", "hk_db", ""),
    ("jupyter_notebook", "🪐 Jupyter Data Science Notebook", "hk_jupyter", ""),
    ("deepl_translate", "🌐 DeepL 双语对照翻译模式", "hk_deepl", ""),
    ("browser_devtools", "🛠️ Chrome DevTools F12 控制台", "hk_devtools", ""),
    ("chat_teams", "💬 企业工作群聊日志模式", "hk_teams", ""),
    ("logcat_viewer", "📜 服务器运行日志流模式", "hk_logcat", ""),
    ("markdown_editor", "📝 Typora Markdown 编辑器模式", "hk_typora", ""),
    ("jenkins_ci", "⚙️ Jenkins CI 自动化构建日志模式", "hk_jenkins", "")
]

class BaseStealthWindow(QWidget):
    switch_mode_signal = pyqtSignal()
    file_loaded_signal = pyqtSignal(str)
    settings_changed_signal = pyqtSignal()
    progress_updated_signal = pyqtSignal(str, int, int, int)  # (file_path, chapter_idx, line_idx, total_lines)

    def __init__(self, config_manager, parent=None, bookshelf_window=None):
        super().__init__(parent)
        self.config_mgr = config_manager
        self.bookshelf_window = bookshelf_window
        self.drag_position = QPoint()
        self.is_boss_hidden = False
        self.is_dialog_open = False
        
        self.book: Book = None
        self.lines = []
        
        self.border_width = 8
        self.resizing = False
        self.drag_edge = 0
        self.drag_start_geometry = QRect()
        self.drag_start_pos = QPoint()
        
        self.active_opacity = self.config_mgr.settings.get("opacity", 0.85)
        self.idle_opacity = self.config_mgr.settings.get("idle_opacity", 0.20)

        self.reading_shortcuts = []

        self.is_auto_scrolling = False
        self.auto_scroll_timer = QTimer(self)
        self.auto_scroll_timer.timeout.connect(self._on_auto_scroll_timeout)

        self.setup_window_flags()
        self.reload_reading_shortcuts()

    def reload_reading_shortcuts(self):
        for sc in self.reading_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.reading_shortcuts.clear()

        # 动态读取 21 种摸鱼伪装模式的快捷键配置（新增模式初始化不设定快捷键，由人工自定义绑定）
        for m_key, m_name, m_setting, default_hk in ALL_STEALTH_MODES:
            hk_val = self.config_mgr.settings.get(m_setting, default_hk)
            if hk_val:
                sc = QShortcut(QKeySequence(hk_val), self)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(lambda k=m_key: self.switch_to_mode(k))
                self.reading_shortcuts.append(sc)

        # 读取自定义阅读控制快捷键
        hk_next_line = self.config_mgr.settings.get("hk_next_line", "Down")
        hk_prev_line = self.config_mgr.settings.get("hk_prev_line", "Up")
        hk_next_chap = self.config_mgr.settings.get("hk_next_chap", "PageDown")
        hk_prev_chap = self.config_mgr.settings.get("hk_prev_chap", "PageUp")
        hk_toggle_auto = self.config_mgr.settings.get("hk_toggle_auto", "Ctrl+Space")

        if hk_next_line:
            sc = QShortcut(QKeySequence(hk_next_line), self)
            sc.activated.connect(self.next_line)
            self.reading_shortcuts.append(sc)
        
        if hk_prev_line:
            sc = QShortcut(QKeySequence(hk_prev_line), self)
            sc.activated.connect(self.prev_line)
            self.reading_shortcuts.append(sc)

        if hk_next_chap:
            sc = QShortcut(QKeySequence(hk_next_chap), self)
            sc.activated.connect(self._jump_next_chap)
            self.reading_shortcuts.append(sc)
        
        if hk_prev_chap:
            sc = QShortcut(QKeySequence(hk_prev_chap), self)
            sc.activated.connect(self._jump_prev_chap)
            self.reading_shortcuts.append(sc)

        if hk_toggle_auto:
            sc = QShortcut(QKeySequence(hk_toggle_auto), self)
            sc.activated.connect(self.toggle_auto_scroll)
            self.reading_shortcuts.append(sc)

        # 实时加减速控制按键 = / + 与 -
        for key in ["=", "+"]:
            sc_speed_up = QShortcut(QKeySequence(key), self)
            sc_speed_up.activated.connect(self.speed_up_auto_scroll)
            self.reading_shortcuts.append(sc_speed_up)

        sc_slow_down = QShortcut(QKeySequence("-"), self)
        sc_slow_down.activated.connect(self.slow_down_auto_scroll)
        self.reading_shortcuts.append(sc_slow_down)

        # 绑定固定功能
        sc_esc = QShortcut(QKeySequence("Esc"), self)
        sc_esc.activated.connect(self.toggle_boss_key)
        self.reading_shortcuts.append(sc_esc)

    def switch_to_mode(self, new_mode: str):
        """实时响应快捷键或右键菜单，在当前获焦的摸鱼窗口中一键无缝切换 23 种伪装模式"""
        if not self.config_mgr:
            return
        curr_mode = getattr(self, 'mode_name', self.config_mgr.settings.get("mode", "floating"))
        self.config_mgr.settings["mode"] = new_mode
        self.config_mgr.save_immediately()

        if curr_mode == new_mode:
            return

        book_path = self.book.file_path if (self.book and hasattr(self.book, 'file_path')) else None

        from src.ui.stealth_views import STEALTH_VIEW_MAP
        from src.ui.floating_view import FloatingView
        view_cls = STEALTH_VIEW_MAP.get(new_mode, FloatingView)
        new_win = view_cls(self.config_mgr, bookshelf_window=self.bookshelf_window)

        if self.bookshelf_window:
            new_win.progress_updated_signal.connect(self.bookshelf_window.on_reading_progress_updated)

        if self.book:
            new_win.book = self.book
            new_win.update_content()
            if self.bookshelf_window and hasattr(self.bookshelf_window, 'active_reading_windows'):
                if book_path:
                    self.bookshelf_window.active_reading_windows[book_path] = new_win
        elif book_path and os.path.exists(book_path):
            new_win.load_file(book_path)
            if self.bookshelf_window and hasattr(self.bookshelf_window, 'active_reading_windows'):
                self.bookshelf_window.active_reading_windows[book_path] = new_win

        self.stop_auto_scroll()
        self.close()
        new_win.show()
        new_win.raise_()
        new_win.activateWindow()

    def toggle_auto_scroll(self):
        if self.is_auto_scrolling:
            self.stop_auto_scroll()
        else:
            self.start_auto_scroll()

    def start_auto_scroll(self):
        if not self.book or not self.book.chapters:
            return
        self.is_auto_scrolling = True
        self.auto_scroll_timer.setInterval(16)  # 60 FPS 匀速连续帧率
        self.auto_scroll_timer.start()
        self.update_content()

    def stop_auto_scroll(self):
        self.is_auto_scrolling = False
        self.auto_scroll_timer.stop()
        self.update_content()

    def reset_auto_scroll_timer(self):
        """用户人工按键/滚动操作时，保持匀速推进"""
        if hasattr(self, 'scroll_y'):
            self.scroll_y = 0.0

    def speed_up_auto_scroll(self):
        curr = float(self.config_mgr.settings.get("auto_scroll_speed", 8.0))
        new_val = min(50.0, round(curr + 1.0, 1))
        self.config_mgr.settings["auto_scroll_speed"] = new_val
        self.config_mgr.save_immediately()
        self.update_content()

    def slow_down_auto_scroll(self):
        curr = float(self.config_mgr.settings.get("auto_scroll_speed", 8.0))
        new_val = max(1.0, round(curr - 1.0, 1))
        self.config_mgr.settings["auto_scroll_speed"] = new_val
        self.config_mgr.save_immediately()
        self.update_content()

    def _on_auto_scroll_timeout(self):
        if not self.is_auto_scrolling or not self.book or not self.book.chapters:
            return
            
        speed_px_per_sec = float(self.config_mgr.settings.get("auto_scroll_speed", 8.0))
        speed_per_frame = speed_px_per_sec / 60.0
        
        if not hasattr(self, 'scroll_y'):
            self.scroll_y = 0.0
            
        self.scroll_y += speed_per_frame
        
        line_height = getattr(self, 'line_height', 24)
        if self.scroll_y >= line_height:
            self.scroll_y -= line_height
            if self.lines:
                if self.book.current_line_idx < len(self.lines) - 1:
                    self.book.current_line_idx += 1
                else:
                    if not self.book.next_chapter():
                        self.stop_auto_scroll()
                    else:
                        self.recalculate_lines(self.book.get_current_chapter())
                        self.book.current_line_idx = 0
            self.save_and_emit_progress()
        else:
            self.render_view()

    def save_and_emit_progress(self):
        if not self.book or not self.book.file_path:
            return
        
        total_l = len(self.lines) if self.lines else 1
        if self.book.current_line_idx < 0:
            self.book.current_line_idx = 0
        elif self.book.current_line_idx >= total_l:
            self.book.current_line_idx = max(0, total_l - 1)

        # 1. 实时精准落盘保存行级别记忆进度
        self.config_mgr.save_progress(
            self.book.file_path,
            self.book.current_chapter_idx,
            self.book.current_line_idx
        )

        # 2. 实时发射 PyQt 信号给 BookshelfWindow 槽函数同步更新主界面
        self.progress_updated_signal.emit(
            self.book.file_path,
            self.book.current_chapter_idx,
            self.book.current_line_idx,
            total_l
        )

    def _jump_next_chap(self):
        if self.book and self.book.next_chapter():
            self.update_content()
            
    def _jump_prev_chap(self):
        if self.book and self.book.prev_chapter():
            self.update_content()

    def setup_window_flags(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)  # 开启鼠标追踪以更新边缘光标
        self.setWindowOpacity(self.active_opacity)

    def resizeEvent(self, event):
        """窗口改变大小时触发自适应重排"""
        super().resizeEvent(event)
        self.update_content()

    def get_line_length(self) -> int:
        """子类可重写，返回该模式下基于当前窗口宽度的单行最大字数"""
        return self.config_mgr.settings.get("line_length", 35)

    def get_visible_lines_count(self) -> int:
        """子类可重写，返回该模式下基于当前窗口高度的最大可见行数"""
        return 1

    def recalculate_lines(self, chap):
        """默认基于字数切分，子类可覆盖为像素级排版"""
        self.lines = chap.get_lines(line_length=self.get_line_length())

    def render_view(self, error_msg: str = None):
        """抽象方法，子类必须实现。用于将 self.book, self.lines 和进度更新到 UI"""
        raise NotImplementedError("Subclasses must implement render_view()")

    def update_opacity_by_hover(self):
        if self.is_dialog_open:
            self.setWindowOpacity(self.active_opacity)
            return
        cursor_pos = QCursor.pos()
        if self.frameGeometry().contains(cursor_pos):
            self.setWindowOpacity(self.active_opacity)
        else:
            self.setWindowOpacity(self.idle_opacity)

    def enterEvent(self, event):
        self.setWindowOpacity(self.active_opacity)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_dialog_open:
            self.setWindowOpacity(self.idle_opacity)
        super().leaveEvent(event)

    def get_resize_edge(self, pos: QPoint) -> int:
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        b = self.border_width
        edge = 0
        if x <= b: edge |= Qt.Edge.LeftEdge.value
        if x >= w - b: edge |= Qt.Edge.RightEdge.value
        if y <= b: edge |= Qt.Edge.TopEdge.value
        if y >= h - b: edge |= Qt.Edge.BottomEdge.value
        return edge

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_edge = self.get_resize_edge(event.pos())
            if self.drag_edge != 0:
                self.resizing = True
                self.drag_start_geometry = self.geometry()
                self.drag_start_pos = event.globalPosition().toPoint()
            else:
                self.resizing = False
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.resizing = False
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # 1. 无按键悬停时，更新边缘缩放光标
        if not event.buttons():
            edge = self.get_resize_edge(event.pos())
            if edge in (Qt.Edge.TopEdge.value | Qt.Edge.LeftEdge.value, Qt.Edge.BottomEdge.value | Qt.Edge.RightEdge.value):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge in (Qt.Edge.TopEdge.value | Qt.Edge.RightEdge.value, Qt.Edge.BottomEdge.value | Qt.Edge.LeftEdge.value):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif edge in (Qt.Edge.LeftEdge.value, Qt.Edge.RightEdge.value):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge in (Qt.Edge.TopEdge.value, Qt.Edge.BottomEdge.value):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # 2. 按住左键拖拽时
        if event.buttons() == Qt.MouseButton.LeftButton:
            if getattr(self, 'resizing', False):
                delta = event.globalPosition().toPoint() - self.drag_start_pos
                g = self.drag_start_geometry
                new_rect = QRect(g)
                
                if self.drag_edge & Qt.Edge.LeftEdge.value:
                    new_rect.setLeft(min(g.left() + delta.x(), g.right() - 200))
                if self.drag_edge & Qt.Edge.RightEdge.value:
                    new_rect.setRight(max(g.right() + delta.x(), g.left() + 200))
                if self.drag_edge & Qt.Edge.TopEdge.value:
                    new_rect.setTop(min(g.top() + delta.y(), g.bottom() - 36))
                if self.drag_edge & Qt.Edge.BottomEdge.value:
                    new_rect.setBottom(max(g.bottom() + delta.y(), g.top() + 36))
                    
                self.setGeometry(new_rect)
            else:
                self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if not file_path:
                    file_path = url.toString()
                    if file_path.startswith("file:///"):
                        file_path = file_path[8:]
                file_path = os.path.normpath(file_path)
                if os.path.exists(file_path):
                    event.acceptProposedAction()
                    self.load_file(file_path)
                    break

    def load_file(self, file_path: str, notify: bool = True):
        if not file_path or not os.path.exists(file_path):
            self.render_view(error_msg="[提示] 上次阅读的文件已被删除或移动，请重新选择文件。")
            return
        try:
            self.book = NovelParser.load_book(file_path)
            if not self.book.chapters:
                self.render_view(error_msg="[提示] 该文件暂无文字内容。")
                return

            prog = self.config_mgr.get_progress(file_path)
            chap_idx = prog.get("chapter_idx", 0)
            line_idx = prog.get("line_idx", 0)

            if chap_idx >= len(self.book.chapters) or chap_idx < 0:
                chap_idx = 0
                line_idx = 0

            self.book.current_chapter_idx = chap_idx
            chap = self.book.get_current_chapter()
            if chap:
                self.recalculate_lines(chap)
                if 0 <= line_idx < len(self.lines):
                    self.book.current_line_idx = line_idx
                else:
                    self.book.current_line_idx = 0
            else:
                self.book.current_line_idx = 0

            self.render_view()
            self.save_and_emit_progress()
            if notify:
                self.file_loaded_signal.emit(file_path)
        except Exception as e:
            self.render_view(error_msg=f"[错误] 解析失败: {str(e)}")

    def update_content(self):
        if not self.book or not self.book.chapters:
            return
        chap = self.book.get_current_chapter()
        if not chap:
            return

        self.recalculate_lines(chap)
        
        if self.book.current_line_idx >= len(self.lines) or self.book.current_line_idx < 0:
            self.book.current_line_idx = 0

        self.render_view()
        self.save_and_emit_progress()

    def jump_to_chapter(self, idx: int):
        if self.book and 0 <= idx < len(self.book.chapters):
            self.book.current_chapter_idx = idx
            self.book.current_line_idx = 0
            self.update_content()

    def next_line(self):
        if not self.book:
            return
        self.reset_auto_scroll_timer()
        if self.book.current_line_idx < len(self.lines) - 1:
            self.book.current_line_idx += 1
            self.update_content()
        else:
            if self.book.next_chapter():
                self.update_content()

    def prev_line(self):
        if not self.book:
            return
        self.reset_auto_scroll_timer()
        if self.book.current_line_idx > 0:
            self.book.current_line_idx -= 1
            self.update_content()
        else:
            if self.book.prev_chapter():
                chap = self.book.get_current_chapter()
                if chap:
                    self.lines = chap.get_lines(self.get_line_length())
                    self.book.current_line_idx = max(0, len(self.lines) - 1)
                self.update_content()

    def wheelEvent(self, event: QWheelEvent):
        if not self.book:
            return
        self.reset_auto_scroll_timer()
        delta = event.angleDelta().y()
        if delta < 0:
            self.next_line()
        else:
            self.prev_line()

    def keyPressEvent(self, event: QKeyEvent):
        if not self.book:
            super().keyPressEvent(event)
            return
        self.reset_auto_scroll_timer()
        
        # 快捷键精准监听 (Ctrl+1 / Ctrl+2 / Ctrl+3 模式切换)
        modifiers = event.modifiers()
        key = event.key()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_1:
                self.switch_to_mode("floating")
                return
            elif key == Qt.Key.Key_2:
                self.switch_to_mode("ide_pseudo")
                return
            elif key == Qt.Key.Key_3:
                self.switch_to_mode("cad_pseudo")
                return

        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.next_line()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.prev_line()
        elif key == Qt.Key.Key_PageDown:
            if self.book and self.book.next_chapter():
                self.update_content()
        elif key == Qt.Key.Key_PageUp:
            if self.book and self.book.prev_chapter():
                self.update_content()
        elif key == Qt.Key.Key_Escape:
            self.toggle_boss_key()
        else:
            super().keyPressEvent(event)

    def open_chapter_dialog(self):
        if not self.book or not self.book.chapters:
            return
        self.is_dialog_open = True
        self.setWindowOpacity(self.active_opacity)
        dialog = ChapterDialog(self.book.chapters, self.book.current_chapter_idx, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            self.jump_to_chapter(dialog.selected_index)
        self.is_dialog_open = False
        self.update_opacity_by_hover()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181C;
                color: #FFFFFF;
                border: 1px solid #2D2D3A;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0D47A1;
                color: #FFFFFF;
            }
        """)

        bookshelf_action = menu.addAction("📚 返回主书架")
        exit_reading_action = menu.addAction("🚪 退出当前摸鱼模式")
        
        menu.addSeparator()

        # 🎨 切换摸鱼伪装模式 (子菜单展示全套 21 种摸鱼伪装模式)
        mode_menu = menu.addMenu("🎨 切换摸鱼伪装模式")
        mode_menu.setStyleSheet("""
            QMenu {
                background-color: #18181C;
                color: #FFFFFF;
                border: 1px solid #2D2D3A;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0D47A1;
                color: #FFFFFF;
            }
        """)

        mode_actions = {}
        for m_key, m_name, m_setting, default_hk in ALL_STEALTH_MODES:
            hk_val = self.config_mgr.settings.get(m_setting, default_hk)
            label = f"{m_name} ({hk_val})" if hk_val else m_name
            act = mode_menu.addAction(label)
            mode_actions[act] = m_key

        chap_action = None
        if self.book and self.book.chapters:
            menu.addSeparator()
            chap_action = menu.addAction(f"📖 章节目录 (共 {len(self.book.chapters)} 章)")
                
        menu.addSeparator()
        hk_auto = self.config_mgr.settings.get("hk_toggle_auto", "Ctrl+Space")
        if self.is_auto_scrolling:
            auto_action = menu.addAction(f"⏸️ 暂停自动翻页 ({hk_auto})")
        else:
            auto_action = menu.addAction(f"▶️ 开启自动翻页 ({hk_auto})")

        boss_info = menu.addAction(f"🛡️ 老板键: {self.config_mgr.settings.get('boss_key', 'Alt+Z')}")
        boss_info.setEnabled(False)

        action = menu.exec(event.globalPos())
        if action in mode_actions:
            self.switch_to_mode(mode_actions[action])
        elif action == bookshelf_action:
            self.stop_auto_scroll()
            if self.bookshelf_window:
                self.bookshelf_window.refresh_bookshelf()
                self.bookshelf_window.show_main_window()
        elif action == exit_reading_action:
            self.stop_auto_scroll()
            if self.bookshelf_window and hasattr(self.bookshelf_window, 'active_reading_windows'):
                for path, win in list(self.bookshelf_window.active_reading_windows.items()):
                    if win == self:
                        del self.bookshelf_window.active_reading_windows[path]
                self.bookshelf_window.refresh_bookshelf()
                self.bookshelf_window.show_main_window()
            self.close()
        elif chap_action and action == chap_action:
            QTimer.singleShot(10, self.open_chapter_dialog)
        elif action == auto_action:
            self.toggle_auto_scroll()

    def toggle_boss_key(self):
        if self.isVisible():
            if self.is_auto_scrolling:
                self.stop_auto_scroll()
            self.hide()
            self.is_boss_hidden = True
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.is_boss_hidden = False
            self.setWindowOpacity(self.active_opacity)
