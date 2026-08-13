# Graph Report - .  (2026-08-13)

## Corpus Check
- 77 files · ~52,227 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 454 nodes · 921 edges · 32 communities (15 shown, 17 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 112 edges (avg confidence: 0.52)
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

## God Nodes (most connected - your core abstractions)
1. `BaseStealthWindow` - 77 edges
2. `BookshelfWindow` - 62 edges
3. `ConfigManager` - 40 edges
4. `SoNovelClient` - 35 edges
5. `DownloadDialog` - 25 edges
6. `ForwardTextEdit` - 25 edges
7. `DatabaseManager` - 24 edges
8. `Book` - 23 edges
9. `Chapter` - 22 edges
10. `FloatingView` - 19 edges

## Surprising Connections (you probably didn't know these)
- `TestConfig` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestEncoding` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestParser` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestAutoUpdateVerification` --uses--> `ConfigManager`  [INFERRED]
  tests/test_auto_update_flow.py → src/core/config.py
- `TestAutoUpdateVerification` --uses--> `SoNovelClient`  [INFERRED]
  tests/test_auto_update_flow.py → src/core/sonovel_client.py

## Import Cycles
- None detected.

## Communities (32 total, 17 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (12): QDragEnterEvent, QDropEvent, QMainWindow, QTableWidget, QWidget, BookshelfWindow, 主窗口实时槽函数：精准同步更新章 + 行级别的实时阅读进度, 自动将外部导入的小说复制一份存放于项目根目录 downloads/ 文件夹中 (+4 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (16): Any, ConfigManager, QDialog, test_config_save_and_load(), test_last_file_handling(), test_auto_scroll_feature(), test_bookshelf_window_and_import(), test_cad_pseudo_view_toggle() (+8 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (10): DatabaseManager, SQLite 数据库管理器：持久化保存小说下载管理任务、书籍信息、作者、下载链接等核心元数据, TestAutoUpdateVerification, TestDatabaseManager, AutoUpdateWorker, DownloadWorker, get_resource_path(), 自动追更检索：软件开启默认执行一次，之后每 30 分钟轮询一次 (+2 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (11): QKeyEvent, QMouseEvent, QTextEdit, QWheelEvent, CADCommandLineEdit, IDEPseudoView, LogTextEdit, DBDBeaverPseudoView (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (7): QDragMoveEvent, QPoint, BaseStealthWindow, 实时响应快捷键或右键菜单，在当前获焦的摸鱼窗口中一键无缝切换 21 种伪装模式, 子类可重写，返回该模式下基于当前窗口宽度的单行最大字数, 子类可重写，返回该模式下基于当前窗口高度的最大可见行数, 抽象方法，子类必须实现。用于将 self.book, self.lines 和进度更新到 UI

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (15): Book, Chapter, 将章节内容高效拆分为适应摸鱼窄条/控制台的微型行，带缓存优化, EpubParser, NovelParser, PdfParser, TxtParser, TestConfig (+7 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (6): EpubBuilder, 原生生成标准的 EPUB 电子书 (Zip 容器，含 mimetype, container.xml, content.opf, toc.ncx, XHTML, DownloadDialog, DownloadWorker, 使用独享物理 Session 抓取章节纯文本, SearchWorker

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (9): _get_js_ctx(), 对单本书源规则的目标 host 发起快速连通性响应测试 (单次 3.0s 超时)，返回 (is_ok, latency_ms), 当搜书过程中发现原本通过测试的书源断连时，立即打回并标记缓存失效, SoNovelClient, Event, QThread, Session, DebugClient (+1 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (5): QAbstractNativeEventFilter, QObject, NovelReadApp, BossKeyManager, WindowsNativeHotkeyFilter

## Knowledge Gaps
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BaseStealthWindow` connect `Community 4` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 5`, `Community 6`, `Community 9`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`, `Community 17`, `Community 18`, `Community 19`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 24`?**
  _High betweenness centrality (0.518) - this node is a cross-community bridge._
- **Why does `BookshelfWindow` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 5`, `Community 6`, `Community 7`, `Community 8`?**
  _High betweenness centrality (0.250) - this node is a cross-community bridge._
- **Why does `DownloadDialog` connect `Community 6` to `Community 0`, `Community 1`, `Community 4`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `BaseStealthWindow` (e.g. with `Book` and `NovelParser`) actually correct?**
  _`BaseStealthWindow` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `BookshelfWindow` (e.g. with `NovelReadApp` and `ConfigManager`) actually correct?**
  _`BookshelfWindow` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `ConfigManager` (e.g. with `NovelReadApp` and `TestConfig`) actually correct?**
  _`ConfigManager` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `SoNovelClient` (e.g. with `TestAutoUpdateVerification` and `DebugClient`) actually correct?**
  _`SoNovelClient` has 10 INFERRED edges - model-reasoned connections that need verification._