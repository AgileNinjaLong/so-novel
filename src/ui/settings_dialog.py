from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QKeySequenceEdit, QFormLayout, QMessageBox, QGroupBox
)
from PyQt6.QtGui import QKeySequence

class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_mgr = config_manager
        self.setWindowTitle("⚙️ 快捷键绑定设置")
        self.resize(420, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ----------------- 组1：模式切换与全局 -----------------
        group_mode = QGroupBox("模式与全局切换按键")
        form_mode = QFormLayout()
        
        self.boss_key_edit = QKeySequenceEdit(self)
        self.boss_key_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("boss_key", "Alt+Z")))
        self.hk_floating_edit = QKeySequenceEdit(self)
        self.hk_floating_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_floating", "Ctrl+1")))
        self.hk_ide_edit = QKeySequenceEdit(self)
        self.hk_ide_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_ide", "Ctrl+2")))
        self.hk_cad_edit = QKeySequenceEdit(self)
        self.hk_cad_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_cad", "Ctrl+3")))

        form_mode.addRow("🛡️ 老板键 (全局隐身):", self.boss_key_edit)
        form_mode.addRow("📖 极简透明模式:", self.hk_floating_edit)
        form_mode.addRow("💻 IDE 伪装模式:", self.hk_ide_edit)
        form_mode.addRow("📐 CAD 伪装模式:", self.hk_cad_edit)
        group_mode.setLayout(form_mode)
        main_layout.addWidget(group_mode)

        # ----------------- 组2：阅读控制 -----------------
        group_read = QGroupBox("阅读与翻页操作按键")
        form_read = QFormLayout()
        
        self.hk_next_line = QKeySequenceEdit(self)
        self.hk_next_line.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_next_line", "Down")))
        self.hk_prev_line = QKeySequenceEdit(self)
        self.hk_prev_line.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_prev_line", "Up")))
        self.hk_next_chap = QKeySequenceEdit(self)
        self.hk_next_chap.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_next_chap", "PageDown")))
        self.hk_prev_chap = QKeySequenceEdit(self)
        self.hk_prev_chap.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_prev_chap", "PageUp")))

        form_read.addRow("⬇️ 下一行:", self.hk_next_line)
        form_read.addRow("⬆️ 上一行:", self.hk_prev_line)
        form_read.addRow("⏭️ 下一章:", self.hk_next_chap)
        form_read.addRow("⏮️ 上一章:", self.hk_prev_chap)
        group_read.setLayout(form_read)
        main_layout.addWidget(group_read)

        # ----------------- 按钮栏 -----------------
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        cancel_btn = QPushButton("取消")

        save_btn.clicked.connect(self.save_settings)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        # QSS 样式
        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D30;
                color: #CCCCCC;
            }
            QGroupBox {
                color: #569CD6;
                font-weight: bold;
                border: 1px solid #3F3F46;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QLabel {
                color: #CCCCCC;
                font-size: 13px;
            }
            QKeySequenceEdit {
                background-color: #1E1E1E;
                color: #4EC9B0;
                border: 1px solid #3C3C3C;
                border-radius: 3px;
                padding: 4px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
        """)

    def save_settings(self):
        boss_key = self.boss_key_edit.keySequence().toString()
        hk_floating = self.hk_floating_edit.keySequence().toString()
        hk_ide = self.hk_ide_edit.keySequence().toString()
        hk_cad = self.hk_cad_edit.keySequence().toString()
        
        hk_next_line = self.hk_next_line.keySequence().toString()
        hk_prev_line = self.hk_prev_line.keySequence().toString()
        hk_next_chap = self.hk_next_chap.keySequence().toString()
        hk_prev_chap = self.hk_prev_chap.keySequence().toString()

        # 防冲突校验 (同组或跨组都不允许重复，除非是空值)
        keys = [
            boss_key, hk_floating, hk_ide, hk_cad, 
            hk_next_line, hk_prev_line, hk_next_chap, hk_prev_chap
        ]
        valid_keys = [k for k in keys if k]
        if len(valid_keys) != len(set(valid_keys)):
            QMessageBox.critical(self, "快捷键冲突", "检测到重复的快捷键设置，请修改后重试！")
            return

        if not boss_key:
            QMessageBox.warning(self, "无效设置", "老板键不能为空！")
            return

        self.config_mgr.settings["boss_key"] = boss_key
        self.config_mgr.settings["hk_floating"] = hk_floating
        self.config_mgr.settings["hk_ide"] = hk_ide
        self.config_mgr.settings["hk_cad"] = hk_cad
        
        self.config_mgr.settings["hk_next_line"] = hk_next_line
        self.config_mgr.settings["hk_prev_line"] = hk_prev_line
        self.config_mgr.settings["hk_next_chap"] = hk_next_chap
        self.config_mgr.settings["hk_prev_chap"] = hk_prev_chap
        
        self.config_mgr.save_immediately()
        
        QMessageBox.information(self, "设置成功", "快捷键已保存！(阅读控制快捷键立即生效，全局键需重启)")
        self.accept()
