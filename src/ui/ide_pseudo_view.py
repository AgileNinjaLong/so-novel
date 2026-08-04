import datetime
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QMenu, QFileDialog, QDialog
from PyQt6.QtGui import QFont, QKeyEvent, QWheelEvent
from src.ui.base_window import BaseStealthWindow
from src.ui.chapter_dialog import ChapterDialog
from src.core.parser import NovelParser
from src.core.book import Book

class IDEPseudoView(BaseStealthWindow):
    switch_mode_signal = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(config_manager, parent)
        self.book: Book = None
        self.init_ui()

    def init_ui(self):
        self.resize(720, 240)
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        self.editor = QTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont("Consolas", 10))
        
        # 背景色设置为 RGB(51, 51, 51) / #333333, 配色贴合暗黑系 IDE/Terminal
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: rgb(51, 51, 51);
                color: #CCCCCC;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)

        layout.addWidget(self.editor)
        self.setLayout(layout)
        self.render_placeholder()

    def render_placeholder(self):
        sample_log = [
            "[INFO 10:42:01] Initializing background task daemon...",
            "[DEBUG 10:42:02] Loading module: core.network.service...",
            "# [DEBUG 10:42:03] NovelRead IDE Pseudo Mode - RGB(51,51,51) (F12 切换模式, 右键打开电子书)",
            "[INFO 10:42:04] Worker thread pool started with 8 threads."
        ]
        self.editor.setText("\n".join(sample_log))

    def load_file(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            self.editor.setText("[WARNING] 上次阅读的文件已被删除或移动，请右键重新选择文件。")
            return
        try:
            self.book = NovelParser.load_book(file_path)
            prog = self.config_mgr.get_progress(file_path)
            self.book.current_chapter_idx = prog.get("chapter_idx", 0)
            self.book.current_line_idx = prog.get("line_idx", 0)
            self.update_content()
        except Exception as e:
            self.editor.setText(f"[ERROR] Failed to parse file: {str(e)}")

    def update_content(self):
        if not self.book or not self.book.chapters:
            return

        chap = self.book.get_current_chapter()
        if not chap:
            return

        lines = chap.get_lines(line_length=60)
        output_logs = [
            f"[INFO {datetime.datetime.now().strftime('%H:%M:%S')}] Executing task: {self.book.title}.py",
            f"[DEBUG {datetime.datetime.now().strftime('%H:%M:%S')}] Active Chapter: [{chap.title}]",
            "--------------------------------------------------------------------------------"
        ]

        # 渲染近20行文字伪装为代码/日志
        start_idx = max(0, self.book.current_line_idx - 5)
        end_idx = min(len(lines), start_idx + 15)

        for i in range(start_idx, end_idx):
            prefix = f"# [DEBUG {datetime.datetime.now().strftime('%H:%M:%S')}] " if i != self.book.current_line_idx else ">>> # [FOCUS] "
            output_logs.append(f"{prefix}{lines[i]}")

        output_logs.append("--------------------------------------------------------------------------------")
        output_logs.append(f"[INFO {datetime.datetime.now().strftime('%H:%M:%S')}] Status: OK | Chapter Progress: {self.book.current_chapter_idx + 1}/{self.book.total_chapters}")

        self.editor.setText("\n".join(output_logs))
        
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
        chap = self.book.get_current_chapter()
        if chap:
            lines = chap.get_lines(60)
            if self.book.current_line_idx < len(lines) - 1:
                self.book.current_line_idx += 1
            else:
                self.book.next_chapter()
            self.update_content()

    def prev_line(self):
        if not self.book:
            return
        if self.book.current_line_idx > 0:
            self.book.current_line_idx -= 1
        else:
            if self.book.prev_chapter():
                chap = self.book.get_current_chapter()
                if chap:
                    lines = chap.get_lines(60)
                    self.book.current_line_idx = max(0, len(lines) - 1)
        self.update_content()

    def wheelEvent(self, event: QWheelEvent):
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
        switch_action = menu.addAction("🔄 切换至 极简透明悬浮窗 (F12)")

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
            QTimer.singleShot(10, self.open_chapter_dialog)
        elif action == quit_action:
            self.close()
