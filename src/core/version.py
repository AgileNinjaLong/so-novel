"""
NovelRead 语义化版本控制模块 (Semantic Versioning 2.0.0)
规范: MAJOR.MINOR.PATCH
- MAJOR (主版本号): 架构重构或不兼容大变更
- MINOR (次版本号): 新增加向下兼容的重大功能 (全Tab主书架、系统图标、多任务并发下载)
- PATCH (修订版本号): 向下兼容的缺陷修复与问题攻坚
"""

VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_PATCH = 0

__version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
APP_NAME = "NovelRead"
APP_TITLE = "摸鱼看小说"
FULL_VERSION_STRING = f"{APP_TITLE} v{__version__}"
RELEASE_DATE = "2026-08-12"
BUILD_AUTHOR = "Google DeepMind Antigravity Team"
