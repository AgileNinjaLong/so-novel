from src.ui.stealth_views.floating_view import FloatingView
from src.ui.stealth_views.ide_pseudo_view import IDEPseudoView
from src.ui.stealth_views.cad_pseudo_view import CADPseudoView
from src.ui.stealth_views.excel_view import ExcelPseudoView
from src.ui.stealth_views.word_view import WordPseudoView
from src.ui.stealth_views.terminal_view import TerminalPseudoView
from src.ui.stealth_views.outlook_view import OutlookPseudoView
from src.ui.stealth_views.swagger_view import SwaggerPseudoView
from src.ui.stealth_views.git_diff_view import GitDiffPseudoView
from src.ui.stealth_views.notion_view import NotionPseudoView
from src.ui.stealth_views.pdf_view import PDFReaderPseudoView
from src.ui.stealth_views.stock_view import StockKlinePseudoView
from src.ui.stealth_views.json_view import JSONValidatorPseudoView
from src.ui.stealth_views.sysmon_view import SysMonitorPseudoView
from src.ui.stealth_views.calc_view import CalculatorPseudoView
from src.ui.stealth_views.dbeaver_view import DBDBeaverPseudoView
from src.ui.stealth_views.jupyter_view import JupyterPseudoView
from src.ui.stealth_views.deepl_view import DeepLTranslatePseudoView
from src.ui.stealth_views.devtools_view import DevToolsPseudoView
from src.ui.stealth_views.teams_view import ChatTeamsPseudoView
from src.ui.stealth_views.logcat_view import LogcatPseudoView
from src.ui.stealth_views.markdown_view import MarkdownEditorPseudoView
from src.ui.stealth_views.jenkins_view import JenkinsCIPseudoView

STEALTH_VIEW_MAP = {
    "floating": FloatingView,
    "ide_pseudo": IDEPseudoView,
    "cad_pseudo": CADPseudoView,
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
