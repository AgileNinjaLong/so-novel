import datetime
import os
import re
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtGui import QFont, QWheelEvent, QKeyEvent, QMouseEvent, QContextMenuEvent, QColor

from src.ui.base_window import BaseStealthWindow

# 通用子控件鼠标与按键事件转发基类文本框
class ForwardTextEdit(QTextEdit):
    def __init__(self, parent_view=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_view = parent_view
        self.setReadOnly(True)

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


# 通用子控件表格转发
class ForwardTableWidget(QTableWidget):
    def __init__(self, parent_view=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_view = parent_view
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

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


# 1. Excel 电子表格伪装模式
class ExcelPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "excel_sheet"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 伪装 Excel 标题与公式栏
        self.header_lbl = QLabel("  📊 Microsoft Excel - [Data_Analysis_Report_2026.xlsx]   fx =SUM(C2:C100)")
        self.header_lbl.setStyleSheet("background-color: #107C41; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.header_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Row_ID", "Cell_Formula", "Data_Content", "Status_Flag"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                gridline-color: #333333;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #107C41;
                font-weight: bold;
                border: 1px solid #333333;
            }
        """)
        layout.addWidget(self.table)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.table.setRowCount(1)
            self.table.setItem(0, 2, QTableWidgetItem(error_msg))
            return
        if not self.book or not self.lines:
            return

        chap = self.book.get_current_chapter()
        title_str = chap.title if chap else "Sheet1"
        self.header_lbl.setText(f"  📊 Microsoft Excel - [{self.book.title}.xlsx] - Sheet: {title_str}   fx =CELL(\"contents\")")

        start = self.book.current_line_idx
        end = min(start + 15, len(self.lines))
        display_lines = self.lines[start:end]

        self.table.setRowCount(len(display_lines))
        for i, line_text in enumerate(display_lines):
            row_num = start + i + 1
            self.table.setItem(i, 0, QTableWidgetItem(f"R_{row_num:03d}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"=VAL(\"C{row_num}\")"))
            
            val_item = QTableWidgetItem(line_text)
            val_item.setForeground(QColor("#9CDCFE"))
            self.table.setItem(i, 2, val_item)
            self.table.setItem(i, 3, QTableWidgetItem("CALCULATED"))


# 2. Word 办公文档模式
class WordPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "word_doc"
        self.resize(700, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📄 Microsoft Word - [工作总结与季度规划草稿.docx]")
        self.title_lbl.setStyleSheet("background-color: #2B579A; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E24;
                color: #E0E0E0;
                border: 1px solid #2B579A;
                padding: 10px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        self.title_lbl.setText(f"  📄 Word - [{self.book.title}.docx] - {chap.title if chap else ''}")

        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        display_text = "\n".join(self.lines[start:end])
        self.editor.setText(f"【工作汇报与可行性方案】\n\n{display_text}")


# 3. PowerShell / Terminal 命令行伪装模式
class TerminalPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "terminal_cli"
        self.resize(720, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🖥️ Administrator: Windows PowerShell")
        self.title_lbl.setStyleSheet("background-color: #012456; color: white; font-weight: bold; font-size: 11px; padding: 3px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #012456;
                color: #CCCCCC;
                border: none;
                padding: 8px;
            }
        """)
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(f"PS C:\\System32> {error_msg}")
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 14, len(self.lines))

        logs = [
            "Windows PowerShell",
            "Copyright (C) Microsoft Corporation. All rights reserved.",
            "",
            f"PS C:\\Users\\Admin\\Projects\\{self.book.title}> Get-Content -Path .\\chapter_{self.book.current_chapter_idx + 1}.log"
        ]
        for line in self.lines[start:end]:
            logs.append(f"LOG >> {line}")

        logs.append(f"PS C:\\Users\\Admin\\Projects\\{self.book.title}> _")
        self.editor.setText("\n".join(logs))


# 4. Outlook 邮件客户端伪装模式
class OutlookPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "outlook_email"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  ✉️ Outlook - [RE: 关于本周工作进展与季度规划报告的讨论]")
        self.title_lbl.setStyleSheet("background-color: #0072C6; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Segoe UI", 10))
        self.editor.setStyleSheet("background-color: #1F1F1F; color: #D4D4D4; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        text = "\n".join(self.lines[start:end])

        mail_content = [
            f"发件人: manager@company.com",
            f"收件人: team@company.com",
            f"主题: RE: [{self.book.title}] {chap.title if chap else ''} 工作进展讨论",
            f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "----------------------------------------------------------------------",
            "各位同事：\n",
            text,
            "\n祝好，\n项目管理组"
        ]
        self.editor.setText("\n".join(mail_content))


# 5. Swagger / Postman API 接口文档伪装模式
class SwaggerPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "swagger_api"
        self.resize(750, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🔌 Swagger UI - RESTful API Specification v2.4")
        self.title_lbl.setStyleSheet("background-color: #89BF04; color: black; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1E1E1E; color: #B5CEA8; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))

        api_payload = [
            f"GET /api/v1/{self.book.title}/chapter/{self.book.current_chapter_idx + 1}",
            "Host: api.company.internal",
            "Accept: application/json",
            "HTTP/1.1 200 OK",
            "{",
            f'  "code": 200,',
            f'  "chapter_name": "{chap.title if chap else ""}",',
            '  "data": ['
        ]
        for line in self.lines[start:end]:
            api_payload.append(f'    "{line}",')
        api_payload.append("  ]")
        api_payload.append("}")
        self.editor.setText("\n".join(api_payload))


# 6. Git Commit Diff 版本控制伪装模式
class GitDiffPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "git_diff"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🔀 Git Commit Diff - commit [a8f93e2]")
        self.title_lbl.setStyleSheet("background-color: #F05032; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #181818; color: #CCCCCC; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 13, len(self.lines))

        diff_logs = [
            f"diff --git a/src/{self.book.title}.py b/src/{self.book.title}.py",
            "index 7f83a21..b912e45 100644",
            f"--- a/src/{self.book.title}.py",
            f"+++ b/src/{self.book.title}.py",
            f"@@ -{start+1},12 +{start+1},14 @@ {chap.title if chap else ''}"
        ]
        for idx, line in enumerate(self.lines[start:end]):
            prefix = "+" if idx % 2 == 0 else " "
            diff_logs.append(f"{prefix} {line}")

        self.editor.setText("\n".join(diff_logs))


# 7. Notion / Markdown 笔记伪装模式
class NotionPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "notion_markdown"
        self.resize(720, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📓 Notion Workspace - [项目架构设计与需求拆解]")
        self.title_lbl.setStyleSheet("background-color: #2F3437; color: #E3E3E3; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #191919; color: #D3D3D3; padding: 12px; line-height: 1.6;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))

        note_lines = [
            f"# {self.book.title} - {chap.title if chap else ''}",
            "## 📌 需求描述与架构拆解",
            "- [x] 完成架构复核",
            "- [ ] 推进单元测试覆盖率\n",
            "> " + "\n> ".join(self.lines[start:end])
        ]
        self.editor.setText("\n".join(note_lines))


# 8. PDF 阅读器 / 论文阅读模式
class PDFReaderPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "pdf_reader"
        self.resize(750, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📑 Adobe Acrobat Reader - [IEEE_Research_Paper_2026.pdf]")
        self.title_lbl.setStyleSheet("background-color: #DC382D; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Times New Roman", 10))
        self.editor.setStyleSheet("background-color: #222222; color: #E0E0E0; padding: 12px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        chap = self.book.get_current_chapter()
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))

        pdf_text = [
            f"Abstract — Research on {self.book.title} ({chap.title if chap else ''})\n",
            "1. INTRODUCTION\n",
            "\n".join(self.lines[start:end]),
            f"\n--- Page {self.book.current_chapter_idx + 1} of {len(self.book.chapters)} ---"
        ]
        self.editor.setText("\n".join(pdf_text))


# 9. 股票 K 线行情看板模式
class StockKlinePseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "stock_kline"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📈 同花顺金融终端 - [上证指数 3345.12 +1.25% 成交量 4500 亿]")
        self.title_lbl.setStyleSheet("background-color: #C62828; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["代码/时间", "开盘/收盘", "行情研报/分析文本", "涨跌幅"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #121212;
                color: #00E676;
                gridline-color: #222222;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #1E1E1E;
                color: #FF5252;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.table.setRowCount(1)
            self.table.setItem(0, 2, QTableWidgetItem(error_msg))
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        display_lines = self.lines[start:end]

        self.table.setRowCount(len(display_lines))
        for i, line_text in enumerate(display_lines):
            t_str = f"600{start+i:03d}"
            self.table.setItem(i, 0, QTableWidgetItem(t_str))
            self.table.setItem(i, 1, QTableWidgetItem(f"32.{i:02d} / 33.{i:02d}"))
            
            val_item = QTableWidgetItem(line_text)
            val_item.setForeground(QColor("#FF5252" if i % 2 == 0 else "#00E676"))
            self.table.setItem(i, 2, val_item)
            self.table.setItem(i, 3, QTableWidgetItem(f"+{1.2 + i*0.1:.2f}%"))


# 10. JSON 校验器伪装模式
class JSONValidatorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "json_validator"
        self.resize(720, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🔍 JSON Online Validator - Status: Valid JSON")
        self.title_lbl.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1E1E1E; color: #CE9178; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        
        json_lines = ['{', '  "status": 200,', '  "message": "success",', '  "payload": {']
        for line in self.lines[start:end]:
            json_lines.append(f'    "item_{len(json_lines)}": "{line}",')
        json_lines.append("  }")
        json_lines.append("}")
        self.editor.setText("\n".join(json_lines))


# 11. Windows 性能监视器模式
class SysMonitorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "sys_monitor"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📊 Windows Resource Monitor - CPU: 12%  MEM: 42%")
        self.title_lbl.setStyleSheet("background-color: #2D2D30; color: #00E676; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "Process Name", "Thread Activity Trace", "CPU %"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                gridline-color: #333333;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #00E676;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.table.setRowCount(1)
            self.table.setItem(0, 2, QTableWidgetItem(error_msg))
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        display_lines = self.lines[start:end]

        self.table.setRowCount(len(display_lines))
        for i, line_text in enumerate(display_lines):
            self.table.setItem(i, 0, QTableWidgetItem(f"{4000+i}"))
            self.table.setItem(i, 1, QTableWidgetItem("svchost.exe"))
            self.table.setItem(i, 2, QTableWidgetItem(line_text))
            self.table.setItem(i, 3, QTableWidgetItem(f"{0.5+i*0.1:.1f}%"))


# 12. 财务科学计算器伪装模式
class CalculatorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "calculator_gui"
        self.resize(650, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🧮 Financial Calculator v3.1")
        self.title_lbl.setStyleSheet("background-color: #4A4A4A; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1C1C1C; color: #00E676; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))
        
        calc_history = []
        for i, line in enumerate(self.lines[start:end]):
            calc_history.append(f"CALC [{i+1:02d}] >> 1500 * 1.05 = {1575+i*10}")
            calc_history.append(f"OUTPUT >> {line}\n")
        self.editor.setText("\n".join(calc_history))


# 13. SQL 数据库控制台模式
class DBDBeaverPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "database_dbeaver"
        self.resize(750, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🗄️ DBeaver Enterprise - [Script-1.sql @ production_db]")
        self.title_lbl.setStyleSheet("background-color: #37474F; color: #80CBC4; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.table = ForwardTableWidget(parent_view=self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["id", "sql_query_statement", "execution_result_text"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                gridline-color: #2D2D2D;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #263238;
                color: #80CBC4;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.table.setRowCount(1)
            self.table.setItem(0, 2, QTableWidgetItem(error_msg))
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        display_lines = self.lines[start:end]

        self.table.setRowCount(len(display_lines))
        for i, line_text in enumerate(display_lines):
            self.table.setItem(i, 0, QTableWidgetItem(f"{start+i+1}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"SELECT * FROM tbl_{start+i}"))
            
            val_item = QTableWidgetItem(line_text)
            val_item.setForeground(QColor("#CE9178"))
            self.table.setItem(i, 2, val_item)


# 14. Jupyter Notebook 模式
class JupyterPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "jupyter_notebook"
        self.resize(750, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🪐 Jupyter Notebook - [data_analysis_v2.ipynb] (PyTorch 2.1)")
        self.title_lbl.setStyleSheet("background-color: #F37626; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #191919; color: #D4D4D4; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))

        cells = []
        for i, line in enumerate(self.lines[start:end]):
            cells.append(f"In [{i+1}]: df.loc[{i}, 'summary_text']")
            cells.append(f"Out[{i}]: '{line}'\n")
        self.editor.setText("\n".join(cells))


# 15. DeepL 双语翻译模式
class DeepLTranslatePseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "deepl_translate"
        self.resize(760, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🌐 DeepL Translator - [English -> Chinese Simplified]")
        self.title_lbl.setStyleSheet("background-color: #0F2B46; color: #00B5E2; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #141C24; color: #E1E1E1; padding: 12px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))

        trans = ["【DeepL 实时智能翻译结果】\n"]
        for line in self.lines[start:end]:
            trans.append(f"ORIGINAL >> [Segment] {line}")
            trans.append(f"TRANSLATION >> {line}\n")
        self.editor.setText("\n".join(trans))


# 16. DevTools F12 控制台模式
class DevToolsPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "browser_devtools"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  🛠️ DevTools - Console / Network Inspection")
        self.title_lbl.setStyleSheet("background-color: #242424; color: #61AFEF; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #181818; color: #ABB2BF; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))

        logs = ["VM102:1 [Console.logTrace] App initialized successfully."]
        for line in self.lines[start:end]:
            logs.append(f"> {line}")
        self.editor.setText("\n".join(logs))


# 17. 企业工作群聊模式
class ChatTeamsPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "chat_teams"
        self.resize(720, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  💬 Microsoft Teams - [项目开发与需求同步群]")
        self.title_lbl.setStyleSheet("background-color: #464775; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #1F1F1F; color: #D4D4D4; padding: 10px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 10, len(self.lines))

        chats = [f"--- 消息历史 ({datetime.datetime.now().strftime('%H:%M')}) ---"]
        for i, line in enumerate(self.lines[start:end]):
            user = "项目经理" if i % 2 == 0 else "技术架构师"
            chats.append(f"[{user}]: {line}")
        self.editor.setText("\n".join(chats))


# 18. 服务器运行日志流模式
class LogcatPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "logcat_viewer"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📜 Server Log Stream - [tail -f /var/log/application.log]")
        self.title_lbl.setStyleSheet("background-color: #263238; color: #80D8FF; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #121212; color: #B0BEC5; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 13, len(self.lines))

        logs = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for line in self.lines[start:end]:
            logs.append(f"[{now_str}] [INFO] [Thread-Pool-1] {line}")
        self.editor.setText("\n".join(logs))


# 19. Typora / Markdown 编辑器模式
class MarkdownEditorPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "markdown_editor"
        self.resize(720, 430)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  📝 Typora - [README_Architecture.md]")
        self.title_lbl.setStyleSheet("background-color: #333333; color: white; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Microsoft YaHei", 10))
        self.editor.setStyleSheet("background-color: #252526; color: #D4D4D4; padding: 12px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))
        self.editor.setText(f"# {self.book.title}\n\n" + "\n\n".join(self.lines[start:end]))


# 20. Jenkins / CI 构建日志模式
class JenkinsCIPseudoView(BaseStealthWindow):
    def __init__(self, config_manager, bookshelf_window=None):
        super().__init__(config_manager, bookshelf_window=bookshelf_window)
        self.mode_name = "jenkins_ci"
        self.resize(750, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("  ⚙️ Jenkins Console Output - Pipeline #1042 [SUCCESS]")
        self.title_lbl.setStyleSheet("background-color: #335061; color: #43A047; font-weight: bold; font-size: 11px; padding: 4px;")
        layout.addWidget(self.title_lbl)

        self.editor = ForwardTextEdit(parent_view=self)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setStyleSheet("background-color: #1A1A1A; color: #43A047; padding: 8px;")
        layout.addWidget(self.editor)

    def render_view(self, error_msg: str = None):
        if error_msg:
            self.editor.setText(error_msg)
            return
        if not self.book or not self.lines:
            return
        start = self.book.current_line_idx
        end = min(start + 12, len(self.lines))

        logs = ["[INFO] --- maven-compiler-plugin:3.8.1:compile (default-compile) ---"]
        for line in self.lines[start:end]:
            logs.append(f"[BUILD-TRACE] {line}")
        logs.append("[INFO] BUILD SUCCESS")
        self.editor.setText("\n".join(logs))


# 模式映射注册工厂
STEALTH_VIEW_MAP = {
    "excel_sheet": ExcelPseudoView,
    "word_doc": WordPseudoView,
    "terminal_cli": TerminalPseudoView,
    "outlook_email": OutlookPseudoView,
    "swagger_api": SwaggerPseudoView,
    "git_diff": GitDiffPseudoView,
    "notion_markdown": NotionPseudoView,
    "pdf_reader": PDFReaderPseudoView,
    "stock_kline": StockKlinePseudoView,
    "json_validator": JSONValidatorPseudoView,
    "sys_monitor": SysMonitorPseudoView,
    "calculator_gui": CalculatorPseudoView,
    "database_dbeaver": DBDBeaverPseudoView,
    "jupyter_notebook": JupyterPseudoView,
    "deepl_translate": DeepLTranslatePseudoView,
    "browser_devtools": DevToolsPseudoView,
    "chat_teams": ChatTeamsPseudoView,
    "logcat_viewer": LogcatPseudoView,
    "markdown_editor": MarkdownEditorPseudoView,
    "jenkins_ci": JenkinsCIPseudoView,
}
