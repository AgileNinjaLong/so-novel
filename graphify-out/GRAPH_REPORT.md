# Graph Report - .  (2026-08-12)

## Corpus Check
- Corpus is ~46,925 words - fits in a single context window. You may not need a graph.

## Summary
- 315 nodes · 620 edges · 16 communities (15 shown, 1 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 69 edges (avg confidence: 0.52)
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

## God Nodes (most connected - your core abstractions)
1. `BookshelfWindow` - 57 edges
2. `BaseStealthWindow` - 53 edges
3. `ConfigManager` - 36 edges
4. `SoNovelClient` - 31 edges
5. `DownloadDialog` - 25 edges
6. `Book` - 23 edges
7. `Chapter` - 22 edges
8. `FloatingView` - 18 edges
9. `CADPseudoView` - 16 edges
10. `IDEPseudoView` - 16 edges

## Surprising Connections (you probably didn't know these)
- `TestConfig` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestEncoding` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestParser` --uses--> `ConfigManager`  [INFERRED]
  tests/run_tests.py → src/core/config.py
- `TestConfig` --uses--> `Chapter`  [INFERRED]
  tests/run_tests.py → src/core/book.py
- `TestEncoding` --uses--> `Chapter`  [INFERRED]
  tests/run_tests.py → src/core/book.py

## Import Cycles
- None detected.

## Communities (16 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (9): QDragEnterEvent, QDropEvent, QMainWindow, QWidget, BookshelfWindow, 点击主界面关闭按钮 (X) 时：在没有在看的小说时直接彻底退出程序；在有摸鱼阅读时弹窗提示并提供彻底退出选项，彻底消除后台僵尸进程！, 彻底干净退出软件，释放所有后台监听线程与资源，拒绝僵尸进程, 自动将外部导入的小说复制一份存放于项目根目录 downloads/ 文件夹中 (+1 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (8): QDragMoveEvent, QMouseEvent, QPoint, BaseStealthWindow, 实时响应快捷键，在当前获焦的摸鱼窗口中一键切换伪装模式, 子类可重写，返回该模式下基于当前窗口宽度的单行最大字数, 子类可重写，返回该模式下基于当前窗口高度的最大可见行数, 抽象方法，子类必须实现。用于将 self.book, self.lines 和进度更新到 UI

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (15): Any, ConfigManager, QDialog, test_config_save_and_load(), test_last_file_handling(), test_auto_scroll_feature(), test_bookshelf_window_and_import(), test_cad_pseudo_view_toggle() (+7 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (15): Book, Chapter, 将章节内容高效拆分为适应摸鱼窄条/控制台的微型行，带缓存优化, EpubParser, NovelParser, PdfParser, TxtParser, TestConfig (+7 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (9): _get_js_ctx(), 对单本书源规则的目标 host 发起快速连通性响应测试 (单次 3.0s 超时)，返回 (is_ok, latency_ms), 当搜书过程中发现原本通过测试的书源断连时，立即打回并标记缓存失效, SoNovelClient, Event, QThread, Session, DebugClient (+1 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (5): QObject, DownloadDialog, DownloadWorker, 使用独享物理 Session 抓取章节纯文本, SearchWorker

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (5): EpubBuilder, 原生生成标准的 EPUB 电子书 (Zip 容器，含 mimetype, container.xml, content.opf, toc.ncx, XHTML, DownloadWorker, SearchWorker, FloatingView

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (7): QKeyEvent, QTextEdit, QWheelEvent, CADCommandLineEdit, CADPseudoView, IDEPseudoView, LogTextEdit

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (4): QAbstractNativeEventFilter, NovelReadApp, BossKeyManager, WindowsNativeHotkeyFilter

## Knowledge Gaps
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BaseStealthWindow` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 5`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.324) - this node is a cross-community bridge._
- **Why does `BookshelfWindow` connect `Community 0` to `Community 2`, `Community 3`, `Community 4`, `Community 6`, `Community 7`, `Community 8`?**
  _High betweenness centrality (0.318) - this node is a cross-community bridge._
- **Why does `SoNovelClient` connect `Community 4` to `Community 0`, `Community 2`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.205) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `BookshelfWindow` (e.g. with `NovelReadApp` and `ConfigManager`) actually correct?**
  _`BookshelfWindow` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `BaseStealthWindow` (e.g. with `Book` and `NovelParser`) actually correct?**
  _`BaseStealthWindow` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `ConfigManager` (e.g. with `NovelReadApp` and `TestConfig`) actually correct?**
  _`ConfigManager` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `SoNovelClient` (e.g. with `DebugClient` and `DummyWorker`) actually correct?**
  _`SoNovelClient` has 8 INFERRED edges - model-reasoned connections that need verification._