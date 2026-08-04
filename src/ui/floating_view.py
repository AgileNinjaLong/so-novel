from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QMenu, QFileDialog, QDialog
from PyQt6.QtGui import QFont, QWheelEvent, QKeyEvent
from src.ui.base_window import BaseStealthWindow
from src.ui.chapter_dialog import ChapterDialog
from src.core.parser import NovelParser
from src.core.book import Book

class FloatingView(BaseStealthWindow):
    switch_mode_signal = pyqtSignal()  # 触发与 IDE 伪装模式切换

    def __init__(self, config_manager, parent=None):
        super().__init__(config_manager, parent)
        self.book: Book = None
        self.lines = []
        self.init_ui()

    def init_ui(self):
        self.resize(600, 36)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 4, 10, 4)

        self.label = QLabel("NovelRead | 右键打开文件或直接拖拽小说到此处")
        self.label.setWordWrap(False)
        
        font_size = self.config_mgr.settings.get("font_size", 11)
        font_family = self.config_mgr.settings.get("font_family", "Microsoft YaHei")
        font_color = self.config_mgr.settings.get("font_color", "#333333")
        bg_color = self.config_mgr.settings.get("bg_color", "#FFFFFF")

        self.setFont(QFont(font_family, font_size))
        self.setStyleSheet(f"""
            QLabel {{
                color: {font_color};
                background-color: {bg_color};
                border-radius: 4px;
                padding: 2px 8px;
            }}
        """)

        layout.addWidget(self.label)
        self.setLayout(layout)

    def load_file(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            self.label.setText("提示：上次阅读的文件已不存在，请重新打开")
            return
        try:
            self.book = NovelParser.load_book(file_path)
            prog = self.config_mgr.get_progress(file_path)
            self.book.current_chapter_idx = prog.get("chapter_idx", 0)
            self.book.current_line_idx = prog.get("line_idx", 0)
            self.update_content()
        except Exception as e:
            self.label.setText(f"打开文件失败: {str(e)}")

    def update_content(self):
        if not self.book or not self.book.chapters:
            return

        chap = self.book.get_current_chapter()
        if not chap:
            return

        line_len = self.config_mgr.settings.get("line_length", 35)
        self.lines = chap.get_lines(line_length=line_len)

        if self.book.current_line_idx >= len(self.lines):
            self.book.current_line_idx = max(0, len(self.lines) - 1)

        current_line_text = self.lines[self.book.current_line_idx] if self.lines else ""
        total_chaps = self.book.total_chapters
        progress_pct = int(((self.book.current_chapter_idx + 1) / total_chaps) * 100) if total_chaps else 0

        text = f"[{chap.title}] {current_line_text}  ({progress_pct}%)"
        self.label.setText(text)
        
        # 异步/防抖保存进度
        self.config_mgr.save_progress(
            self.book.file_path,
            self.book.current_chapter_idx,
            self.book.current_line_idx
        )

    def wheelEvent(self, event: QWheelEvent):
        if not self.book:
            return
        delta = event.angleDelta().y()
        if delta < 0:  # 下滚 -> 下一行
            self.next_line()
        else:          # 上滚 -> 上一行
            self.prev_line()

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
                # 滚到上一章末尾
                chap = self.book.get_current_chapter()
                if chap:
                    self.lines = chap.get_lines(self.config_mgr.settings.get("line_length", 35))
                    self.book.current_line_idx = max(0, len(self.lines) - 1)
                self.update_content()

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
        elif key == Qt.Key.Key_F12:
            self.switch_mode_signal.emit()
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
        open_action = menu.addAction("📂 打开电子书 (TXT/EPUB/PDF)")
        switch_action = menu.addAction("🔄 切换至 IDE 伪装模式 (F12)")
        
        chap_action = None
        if self.book and self.book.chapters:
            menu.addSeparator()
            chap_action = menu.addAction(f"📖 章节目录 (共 {len(self.book.chapters)} 章)")
                
        menu.addSeparator()
        boss_info = menu.addAction(f"🛡️ 老板键: {self.config_mgr.settings.get('boss_key', 'Alt+Z')}")
        boss_info.setEnabled(False)
        quit_action = menu.addAction("❌ 退出软件")

        action = menu.exec(event.globalPos())
        if action == open_action:
            self.is_dialog_open = True
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择电子书", "", "Books (*.txt *.epub *.pdf)"
            )
            self.is_dialog_open = False
            if file_path:
                self.load_file(file_path)
        elif action == switch_action:
            self.switch_mode_signal.emit()
        elif chap_action and action == chap_action:
            # 延迟10ms呼出，等右键菜单完全关闭
            QTimer.singleShot(10, self.open_chapter_dialog)
        elif action == quit_action:
            self.close()

    def jump_to_chapter(self, idx: int):
        if self.book and 0 <= idx < len(self.book.chapters):
            self.book.current_chapter_idx = idx
            self.book.current_line_idx = 0
            self.update_content()
