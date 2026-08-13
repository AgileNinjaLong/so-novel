import importlib

# 模版视图模块映射名
_VIEW_MODULE_MAP = {
    "excel_sheet": ("excel_view", "ExcelPseudoView"),
    "word_doc": ("word_view", "WordPseudoView"),
    "terminal_cli": ("terminal_view", "TerminalPseudoView"),
    "outlook_email": ("outlook_view", "OutlookPseudoView"),
    "swagger_api": ("swagger_view", "SwaggerPseudoView"),
    "git_diff": ("git_diff_view", "GitDiffPseudoView"),
    "notion_markdown": ("notion_view", "NotionPseudoView"),
    "pdf_reader": ("pdf_view", "PDFReaderPseudoView"),
    "stock_kline": ("stock_view", "StockKlinePseudoView"),
    "json_validator": ("json_view", "JSONValidatorPseudoView"),
    "sys_monitor": ("sysmon_view", "SysMonitorPseudoView"),
    "calculator_gui": ("calc_view", "CalculatorPseudoView"),
    "database_dbeaver": ("dbeaver_view", "DBDBeaverPseudoView"),
    "jupyter_notebook": ("jupyter_view", "JupyterPseudoView"),
    "deepl_translate": ("deepl_view", "DeepLTranslatePseudoView"),
    "browser_devtools": ("devtools_view", "DevToolsPseudoView"),
    "chat_teams": ("teams_view", "ChatTeamsPseudoView"),
    "logcat_viewer": ("logcat_view", "LogcatPseudoView"),
    "markdown_editor": ("markdown_view", "MarkdownEditorPseudoView"),
    "jenkins_ci": ("jenkins_view", "JenkinsCIPseudoView"),
}

class _StealthViewMapDict(dict):
    def __getitem__(self, key):
        if key in self:
            return super().__getitem__(key)
        if key in _VIEW_MODULE_MAP:
            mod_name, cls_name = _VIEW_MODULE_MAP[key]
            mod = importlib.import_module(f"src.ui.stealth_views.{mod_name}")
            cls = getattr(mod, cls_name)
            self[key] = cls
            return cls
        raise KeyError(key)

    def __contains__(self, key):
        return super().__contains__(key) or key in _VIEW_MODULE_MAP

STEALTH_VIEW_MAP = _StealthViewMapDict()
