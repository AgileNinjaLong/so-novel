from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTextEdit, QTableWidget
from PyQt6.QtGui import QWheelEvent, QKeyEvent, QMouseEvent, QContextMenuEvent

class ForwardTextEdit(QTextEdit):
    """通用子控件鼠标与按键事件转发基类文本框"""
    def __init__(self, parent_view=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_view = parent_view
        self.setReadOnly(True)
        self.setMouseTracking(True)
        if self.viewport():
            self.viewport().setMouseTracking(True)

    def wheelEvent(self, event: QWheelEvent):
        if self.parent_view:
            if event.angleDelta().y() < 0:
                self.parent_view.next_line()
            else:
                self.parent_view.prev_line()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if self.parent_view:
            self.parent_view.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if self.parent_view and event.button() == Qt.MouseButton.LeftButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(), parent_pos.toPointF(), event.globalPosition(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.parent_view.mousePressEvent(pe)
            event.accept()
            return
        elif self.parent_view and event.button() == Qt.MouseButton.RightButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            cme = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, parent_pos.toPoint(), event.globalPosition().toPoint())
            self.parent_view.contextMenuEvent(cme)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.parent_view:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(), parent_pos.toPointF(), event.globalPosition(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.parent_view.mouseMoveEvent(pe)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.parent_view and event.button() == Qt.MouseButton.LeftButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(), parent_pos.toPointF(), event.globalPosition(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.parent_view.mouseReleaseEvent(pe)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ForwardTableWidget(QTableWidget):
    """通用子控件表格转发"""
    def __init__(self, parent_view=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_view = parent_view
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setMouseTracking(True)
        if self.viewport():
            self.viewport().setMouseTracking(True)

    def wheelEvent(self, event: QWheelEvent):
        if self.parent_view:
            if event.angleDelta().y() < 0:
                self.parent_view.next_line()
            else:
                self.parent_view.prev_line()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if self.parent_view:
            self.parent_view.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if self.parent_view and event.button() == Qt.MouseButton.LeftButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(), parent_pos.toPointF(), event.globalPosition(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.parent_view.mousePressEvent(pe)
            event.accept()
            return
        elif self.parent_view and event.button() == Qt.MouseButton.RightButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            cme = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, parent_pos.toPoint(), event.globalPosition().toPoint())
            self.parent_view.contextMenuEvent(cme)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.parent_view:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(), parent_pos.toPointF(), event.globalPosition(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.parent_view.mouseMoveEvent(pe)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.parent_view and event.button() == Qt.MouseButton.LeftButton:
            parent_pos = self.mapTo(self.parent_view, event.pos())
            pe = QMouseEvent(
                event.type(), parent_pos.toPointF(), event.globalPosition(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.parent_view.mouseReleaseEvent(pe)
            event.accept()
            return
        super().mouseReleaseEvent(event)
