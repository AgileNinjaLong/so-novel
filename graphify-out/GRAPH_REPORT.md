# Graph Report - .  (2026-08-13)

## Corpus Check
- 245 files · ~178,918 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 981 nodes · 2477 edges · 67 communities (41 shown, 26 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 383 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 62|Community 62]]

## God Nodes (most connected - your core abstractions)
1. `BaseStealthWindow` - 94 edges
2. `BookshelfWindow` - 60 edges
3. `ForwardTextEdit` - 56 edges
4. `SoNovelClient` - 46 edges
5. `AppConfig` - 44 edges
6. `ConfigManager` - 43 edges
7. `SearchResult` - 25 edges
8. `DownloadDialog` - 25 edges
9. `DatabaseManager` - 24 edges
10. `Chapter` - 22 edges

## Surprising Connections (you probably didn't know these)
- `TestConfig` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestEncoding` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestParser` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestAutoUpdateVerification` --uses--> `ConfigManager`  [INFERRED]
  tests/test_auto_update_flow.py → src/core/config.py
- `TestAutoUpdateVerification` --uses--> `DatabaseManager`  [INFERRED]
  tests/test_auto_update_flow.py → src/core/db_manager.py

## Import Cycles
- None detected.

## Communities (67 total, 26 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (32): Chapter, ContentType, HttpClientContext, Crawler, HtmlExtractor, Source, Step, Document (+24 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (13): CalculatorPseudoView, ForwardTextEdit, DeepLTranslatePseudoView, GitDiffPseudoView, JenkinsCIPseudoView, JupyterPseudoView, LogcatPseudoView, MarkdownEditorPseudoView (+5 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (17): Book, BookContext, ChapterFormatter, ChapterRenderer, File, CrawlerPostHandler, EpubMergeHandler, HtmlTocHandler (+9 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (20): AutoCloseable, StepEngine, DslBootstrap, Entry, ExecutorRegistry, StepExecutor, JavaExecutor, JavaScriptExecutor (+12 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (22): HttpServlet, HttpServletRequest, HttpServletResponse, LocalBookItem, Object, Order, Override, Serializable (+14 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (15): Any, ConfigManager, QDialog, test_config_save_and_load(), test_last_file_handling(), test_auto_scroll_feature(), test_bookshelf_window_and_import(), test_cad_pseudo_view_toggle() (+7 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (17): Book, Chapter, 将章节内容高效拆分为适应摸鱼窄条/控制台的微型行，带缓存优化, EpubParser, NovelParser, PdfParser, TxtParser, TestConfig (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (7): QDragMoveEvent, QPoint, BaseStealthWindow, 实时响应快捷键或右键菜单，在当前获焦的摸鱼窗口中一键无缝切换 23 种伪装模式, 子类可重写，返回该模式下基于当前窗口宽度的单行最大字数, 子类可重写，返回该模式下基于当前窗口高度的最大可见行数, 抽象方法，子类必须实现。用于将 self.book, self.lines 和进度更新到 UI

### Community 8 - "Community 8"
Cohesion: 0.10
Nodes (7): CheckUpdateAction, AppConfigLoader, Props, Setting, EnvUtils, FileUtils, LangUtils

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (6): QKeyEvent, QMouseEvent, QTextEdit, QWheelEvent, CADCommandLineEdit, LogTextEdit

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (7): _get_js_ctx(), 对单本书源规则的目标 host 发起快速连通性响应测试 (单次 5.0s 超时)，返回 (is_ok, latency_ms), 当搜书过程中发现原本通过测试的书源断连时，立即打回并标记缓存失效, SoNovelClient, Event, Session, TestAuthorSearchAndChapterGap

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (5): ForwardTableWidget, DBDBeaverPseudoView, ExcelPseudoView, StockKlinePseudoView, SysMonitorPseudoView

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (6): QObject, TestAutoUpdateVerification, AutoUpdateWorker, get_resource_path(), 自动追更检索：软件开启默认执行一次，之后每 30 分钟轮询一次, SearchWorker

### Community 13 - "Community 13"
Cohesion: 0.16
Nodes (7): AggregatedSearchAction, AggregatedSearchTest, DownloadAction, Double, SearchResultsHandler, VersionProvider, SearchResult

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (5): ShowSourcesAction, OkHttpClientFactory, TuiLauncher, AppConfig, Main

### Community 15 - "Community 15"
Cohesion: 0.30
Nodes (7): Charset, CsvSource, DisplayName, ParameterizedTest, BookSourceCrawlTest, EncodingGarbledTest, ValueSource

### Community 16 - "Community 16"
Cohesion: 0.13
Nodes (3): QMainWindow, BookshelfWindow, 主窗口实时槽函数：精准同步更新章 + 行级别的实时阅读进度

### Community 18 - "Community 18"
Cohesion: 0.25
Nodes (4): List, Rule, SourceInfo, SourceUtils

### Community 19 - "Community 19"
Cohesion: 0.15
Nodes (4): QAbstractNativeEventFilter, NovelReadApp, BossKeyManager, WindowsNativeHotkeyFilter

### Community 20 - "Community 20"
Cohesion: 0.19
Nodes (3): DatabaseManager, SQLite 数据库管理器：持久化保存小说下载管理任务、书籍信息、作者、下载链接等核心元数据, TestDatabaseManager

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (5): EpubBuilder, 原生生成标准的 EPUB 电子书 (Zip 容器，含 mimetype, container.xml, content.opf, toc.ncx, XHTML, DownloadWorker, 使用独享物理 Session 抓取章节纯文本, SearchWorker

### Community 22 - "Community 22"
Cohesion: 0.23
Nodes (4): ClientReport, ClientReportRepository, ServletContextHandler, WebServer

### Community 23 - "Community 23"
Cohesion: 0.20
Nodes (3): QDropEvent, 自动将外部导入的小说复制一份存放于项目根目录 downloads/ 文件夹中, 开启摸鱼阅读：主界面保持显示不隐藏，支持同时打开多本小说

### Community 24 - "Community 24"
Cohesion: 0.24
Nodes (3): BatchDownloadAction, DSLParser, Result

### Community 25 - "Community 25"
Cohesion: 0.29
Nodes (4): run_benchmark(), run_all_sources_test(), test_dongtan(), DownloadWorker

### Community 27 - "Community 27"
Cohesion: 0.22
Nodes (3): Builder, Chapter, DownloadProgressInfo

### Community 31 - "Community 31"
Cohesion: 0.46
Nodes (7): copy_files(), download_jre(), extract_jre(), main(), package_artifacts(), run_maven(), release-windows.sh script

### Community 32 - "Community 32"
Cohesion: 0.33
Nodes (3): QThread, DebugClient, DummyWorker

## Knowledge Gaps
- **12 isolated node(s):** `fetch-github-releases.sh script`, `linux-install.sh script`, `release-linux.sh script`, `release-macos.sh script`, `run-linux.sh script` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `NovelParser` connect `Community 6` to `Community 16`, `Community 25`, `Community 12`, `Community 7`?**
  _High betweenness centrality (0.400) - this node is a cross-community bridge._
- **Why does `BaseStealthWindow` connect `Community 7` to `Community 1`, `Community 34`, `Community 35`, `Community 33`, `Community 36`, `Community 6`, `Community 5`, `Community 9`, `Community 11`, `Community 43`, `Community 17`, `Community 28`, `Community 29`?**
  _High betweenness centrality (0.308) - this node is a cross-community bridge._
- **Why does `BookshelfWindow` connect `Community 16` to `Community 5`, `Community 6`, `Community 37`, `Community 10`, `Community 43`, `Community 12`, `Community 19`, `Community 20`, `Community 21`, `Community 23`, `Community 28`, `Community 30`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `BaseStealthWindow` (e.g. with `CalculatorPseudoView` and `DBDBeaverPseudoView`) actually correct?**
  _`BaseStealthWindow` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `BookshelfWindow` (e.g. with `NovelReadApp` and `ConfigManager`) actually correct?**
  _`BookshelfWindow` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `ForwardTextEdit` (e.g. with `CalculatorPseudoView` and `DeepLTranslatePseudoView`) actually correct?**
  _`ForwardTextEdit` has 16 INFERRED edges - model-reasoned connections that need verification._
- **What connects `fetch-github-releases.sh script`, `linux-install.sh script`, `release-linux.sh script` to the rest of the system?**
  _31 weakly-connected nodes found - possible documentation gaps or missing edges._