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

class BaseStealthWindow(QWidget):
    switch_mode_signal = pyqtSignal()
    file_loaded_signal = pyqtSignal(str)
    settings_changed_signal = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_mgr = config_manager
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

        self.setup_window_flags()
        self.reload_reading_shortcuts()

    def reload_reading_shortcuts(self):
        for sc in self.reading_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.reading_shortcuts.clear()

        # 读取自定义阅读控制快捷键
        hk_next_line = self.config_mgr.settings.get("hk_next_line", "Down")
        hk_prev_line = self.config_mgr.settings.get("hk_prev_line", "Up")
        hk_next_chap = self.config_mgr.settings.get("hk_next_chap", "PageDown")
        hk_prev_chap = self.config_mgr.settings.get("hk_prev_chap", "PageUp")

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

        # 绑定固定功能
        sc_esc = QShortcut(QKeySequence("Esc"), self)
        sc_esc.activated.connect(self.toggle_boss_key)
        self.reading_shortcuts.append(sc_esc)

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
            self.book.current_line_idx = line_idx

            self.update_content()
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
        self.config_mgr.save_progress(
            self.book.file_path,
            self.book.current_chapter_idx,
            self.book.current_line_idx
        )

    def jump_to_chapter(self, idx: int):
        if self.book and 0 <= idx < len(self.book.chapters):
            self.book.current_chapter_idx = idx
            self.book.current_line_idx = 0
            self.update_content()

    def next_line(self):
        if not self.book:
            return
        if self.book.current_line_idx < len(self.lines) - 1:
            self.book.current_line_idx += 1
            self.update_content()
        else:
            if self.book.next_chapter():
                self.update_content()

    def prev_line(self):
        if not self.book:
            return
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
        delta = event.angleDelta().y()
        if delta < 0:
            self.next_line()
        else:
            self.prev_line()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
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
        from PyQt6.QtWidgets import QApplication
        from src.ui.download_dialog import DownloadDialog

        menu = QMenu(self)
        open_action = menu.addAction("📂 打开本地电子书 (TXT/EPUB/PDF)")
        download_action = menu.addAction("🌐 搜索/下载网络小说 (SoNovel)")
        
        chap_action = None
        if self.book and self.book.chapters:
            menu.addSeparator()
            chap_action = menu.addAction(f"📖 章节目录 (共 {len(self.book.chapters)} 章)")
                
        menu.addSeparator()
        settings_action = menu.addAction("⚙️ 快捷键绑定设置")
        boss_info = menu.addAction(f"🛡️ 隐身键: {self.config_mgr.settings.get('boss_key', 'Alt+Z')}")
        boss_info.setEnabled(False)
        quit_action = menu.addAction("❌ 退出软件")

        action = menu.exec(event.globalPos())
        if action == open_action:
            self.is_dialog_open = True
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择电子书", "", "Books (*.txt *.epub *.pdf);;All Files (*)"
            )
            self.is_dialog_open = False
            if file_path:
                self.load_file(file_path)
        elif action == download_action:
            self.is_dialog_open = True
            self.setWindowOpacity(self.active_opacity)
            dialog = DownloadDialog(self)
            dialog.exec()
            self.is_dialog_open = False
            self.update_opacity_by_hover()
        elif chap_action and action == chap_action:
            QTimer.singleShot(10, self.open_chapter_dialog)
        elif action == settings_action:
            self.is_dialog_open = True
            self.setWindowOpacity(self.active_opacity)
            dialog = SettingsDialog(self.config_mgr, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.settings_changed_signal.emit()
            self.is_dialog_open = False
            self.update_opacity_by_hover()
        elif action == quit_action:
            QApplication.instance().quit()

    def toggle_boss_key(self):
        if self.isVisible():
            self.hide()
            self.is_boss_hidden = True
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.is_boss_hidden = False
            self.setWindowOpacity(self.active_opacity)
