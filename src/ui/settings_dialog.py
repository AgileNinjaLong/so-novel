from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QKeySequenceEdit, QFormLayout, QMessageBox
)
from PyQt6.QtGui import QKeySequence

class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_mgr = config_manager
        self.setWindowTitle("⚙️ 快捷键绑定设置")
        self.resize(360, 220)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        
        self.boss_key_edit = QKeySequenceEdit(self)
        self.boss_key_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("boss_key", "Alt+Z")))
        
        self.hk_floating_edit = QKeySequenceEdit(self)
        self.hk_floating_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_floating", "Ctrl+1")))
        
        self.hk_ide_edit = QKeySequenceEdit(self)
        self.hk_ide_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_ide", "Ctrl+2")))
        
        self.hk_cad_edit = QKeySequenceEdit(self)
        self.hk_cad_edit.setKeySequence(QKeySequence(self.config_mgr.settings.get("hk_cad", "Ctrl+3")))

        form_layout.addRow("🛡️ 全局老板键 (隐身):", self.boss_key_edit)
        form_layout.addRow("📖 透明悬浮窗模式:", self.hk_floating_edit)
        form_layout.addRow("💻 IDE 伪装模式:", self.hk_ide_edit)
        form_layout.addRow("📐 CAD 伪装模式:", self.hk_cad_edit)

        layout.addLayout(form_layout)

        # 按钮栏
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        cancel_btn = QPushButton("取消")

        save_btn.clicked.connect(self.save_settings)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # QSS
        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D30;
                color: #CCCCCC;
            }
            QLabel {
                color: #CCCCCC;
                font-size: 13px;
            }
            QKeySequenceEdit {
                background-color: #1E1E1E;
                color: #569CD6;
                border: 1px solid #3C3C3C;
                border-radius: 3px;
                padding: 4px;
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

        # 防冲突校验
        keys = [boss_key, hk_floating, hk_ide, hk_cad]
        valid_keys = [k for k in keys if k] # Filter empty sequences
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
        self.config_mgr.save_immediately()
        
        QMessageBox.information(self, "设置成功", "快捷键已保存！(部分全局快捷键可能需要重启生效)")
        self.accept()
