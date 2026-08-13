# NovelRead 软件架构与模块设计文档

## 📌 项目概述

**NovelRead** 是一款基于 PyQt6 开发的办公摸鱼小说阅读与下载软件。项目深度对齐并重构了开源项目 **so-novel-main** 的搜索与下载引擎，支持全网 25 个主流书源的高并发检索、多格式落盘（EPUB / TXT / 离散目录）、23 种高频办公软件伪装模式无缝切换、SQLite 数据库持久化存储以及后台增量自动追更。

---

## 📂 核心目录与文件架构

```text
novelRead/
├── doc/                                # 📄 项目全量架构与技术文档目录
│   ├── ARCHITECTURE.md                 # 🏛️ 系统整体架构与设计文档
│   ├── SEARCH_AND_DOWNLOAD_ENGINE.md   # ⚙️ 搜索与下载引擎深度对齐技术规范
│   ├── STEALTH_MODES.md                # 🎨 23 种摸鱼伪装视图与事件转发文档
│   └── USER_MANUAL.md                  # 📖 用户使用手册与操作指南
├── src/                                # 💻 Python 源代码目录
│   ├── main.py                         # 程序启动入口，事件循环与全局单例初始化
│   ├── core/                           # ⚙️ 核心业务逻辑与网络引擎层
│   │   ├── sonovel_client.py           # 【核心】SoNovel 搜索/目录解析/单章爬虫引擎
│   │   ├── db_manager.py               # 【核心】SQLite 数据库持久化层 (novelread.db)
│   │   ├── config.py                   # 【核心】系统配置管理 (config.json)
│   │   ├── parser.py                   # 本地图书文件解析器 (TXT / EPUB)
│   │   └── epub_builder.py             # EPUB 电子书制作与标准化落盘
│   └── ui/                             # 🎨 用户界面与伪装视图层
│       ├── bookshelf_window.py         # 【核心】主窗口（书架/书城/下载管理/系统设置/自动追更）
│       ├── base_window.py              # 【核心】摸鱼伪装基类（模式切换/老板键/进度同步）
│       ├── stealth_views/              # 【核心】20 种高频办公软件伪装视图模块
│       │   ├── common.py               # 伪装子控件事件转发基类
│       │   ├── excel_view.py           # Microsoft Excel 伪装视图
│       │   ├── word_view.py            # Microsoft Word 伪装视图
│       │   ├── terminal_view.py        # Windows Terminal 伪装视图
│       │   ├── outlook_view.py         # Outlook 邮件伪装视图
│       │   ├── swagger_view.py         # Swagger API 文档伪装视图
│       │   └── ... (其余 15 种模块)
│       ├── floating_view.py            # 极简透明悬浮窗模式
│       ├── ide_pseudo_view.py          # VS Code 编辑器伪装模式
│       └── cad_pseudo_view.py          # CAD 图纸命令行伪装模式
├── SoNovel/
│   └── rules/                          # 25 个全网书源规则 JSON 数据库
├── testnovel/                          # 真实落盘小说对比评测目录
├── novelread.db                        # 本地 SQLite 数据库文件
└── config.json                         # 用户个性化配置文件
```

---

## 🏛️ 分层架构设计

系统采用严格的 **三层解耦架构**：

1. **网络与规则解析层 (`src/core/sonovel_client.py`)**：
   - 全网书源 JSON 规则的载入与校验；
   - 规则节点 `search` / `toc` / `chapter` / `crawl` 的 XPath / CSSSelector 提取；
   - 对齐 `so-novel-main` 的非线性文本相似度加权计算与重定向直跳处理。

2. **数据持久化层 (`src/core/db_manager.py` & `src/core/config.py`)**：
   - 使用 SQLite 存储下载任务历史、书源规则与增量追更状态；
   - 使用 `config.json` 存储藏书列表、行级别阅读位置索引与自定义快捷键绑定。

3. **UI 与摸鱼伪装呈现层 (`src/ui/`)**：
   - `BookshelfWindow`：主界面管理，四大 Tab 选项卡解耦；
   - `BaseStealthWindow` 与 `STEALTH_VIEW_MAP`：全套 23 种伪装模式的统一注册与一键无缝切换。
