import os
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QWidget, QMenu, QFileDialog, QMessageBox
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent

class BaseStealthWindow(QWidget):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_mgr = config_manager
        self.drag_position = QPoint()
        self.is_boss_hidden = False
        self.is_dialog_open = False
        
        self.active_opacity = self.config_mgr.settings.get("opacity", 0.85)
        self.idle_opacity = self.config_mgr.settings.get("idle_opacity", 0.20)

        self.setup_window_flags()

    def setup_window_flags(self):
        # 无边框 + 窗口置顶 + Tool类型(不占据主任务栏大图标)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setWindowOpacity(self.active_opacity)

    def enterEvent(self, event):
        if not self.is_dialog_open:
            self.setWindowOpacity(self.active_opacity)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_dialog_open:
            self.setWindowOpacity(self.idle_opacity)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.exists(file_path):
                self.load_file(file_path)

    def load_file(self, file_path: str):
        """子类覆盖实现"""
        pass

    def toggle_boss_key(self):
        """毫秒级老板键显示/隐藏"""
        if self.isVisible():
            self.hide()
            self.is_boss_hidden = True
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.is_boss_hidden = False
