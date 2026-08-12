# Graph Report - .  (2026-08-12)

## Corpus Check
- Corpus is ~40,882 words - fits in a single context window. You may not need a graph.

## Summary
- 259 nodes · 425 edges · 48 communities
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 43 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Book & Chapter Core Models|Book & Chapter Core Models]]
- [[_COMMUNITY_Book & Chapter Core Models|Book & Chapter Core Models]]
- [[_COMMUNITY_Book & Chapter Core Models|Book & Chapter Core Models]]
- [[_COMMUNITY_GUI Mock & Unit Testing|GUI Mock & Unit Testing]]
- [[_COMMUNITY_SoNovel Integration & Rules|SoNovel Integration & Rules]]
- [[_COMMUNITY_App Launch & Mode Switching|App Launch & Mode Switching]]
- [[_COMMUNITY_Downloader & Search UI|Downloader & Search UI]]
- [[_COMMUNITY_Config & Progress Storage|Config & Progress Storage]]

## God Nodes (most connected - your core abstractions)
1. `BaseStealthWindow` - 52 edges
2. `ConfigManager` - 26 edges
3. `Book` - 23 edges
4. `Chapter` - 22 edges
5. `SoNovelClient` - 22 edges
6. `DownloadDialog` - 16 edges
7. `NovelReadApp` - 14 edges
8. `FloatingView` - 14 edges
9. `ChapterDialog` - 13 edges
10. `CADPseudoView` - 12 edges

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

## Communities (48 total, 0 thin omitted)

### Community 0 - "Book & Chapter Core Models"
Cohesion: 0.09
Nodes (10): QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent, QPoint, QWidget, BaseStealthWindow, 子类可重写，返回该模式下基于当前窗口宽度的单行最大字数 (+2 more)

### Community 1 - "Book & Chapter Core Models"
Cohesion: 0.12
Nodes (15): Book, Chapter, 将章节内容高效拆分为适应摸鱼窄条/控制台的微型行，带缓存优化, EpubParser, NovelParser, PdfParser, TxtParser, TestConfig (+7 more)

### Community 2 - "Book & Chapter Core Models"
Cohesion: 0.09
Nodes (8): QDialog, test_auto_scroll_feature(), test_chapter_dialog(), test_floating_view_toggle_boss_key(), test_settings_dialog_conflict(), ChapterDialog, FloatingView, SettingsDialog

### Community 3 - "GUI Mock & Unit Testing"
Cohesion: 0.10
Nodes (9): QKeyEvent, QTextEdit, QWheelEvent, test_cad_pseudo_view_toggle(), test_ide_pseudo_view_toggle(), CADCommandLineEdit, CADPseudoView, IDEPseudoView (+1 more)

### Community 4 - "SoNovel Integration & Rules"
Cohesion: 0.15
Nodes (6): Any, _get_js_ctx(), SoNovelClient, QThread, DebugClient, DummyWorker

### Community 5 - "App Launch & Mode Switching"
Cohesion: 0.14
Nodes (4): QAbstractNativeEventFilter, NovelReadApp, BossKeyManager, WindowsNativeHotkeyFilter

### Community 6 - "Downloader & Search UI"
Cohesion: 0.14
Nodes (4): QObject, DownloadDialog, DownloadWorker, SearchWorker

### Community 7 - "Config & Progress Storage"
Cohesion: 0.22
Nodes (3): ConfigManager, test_config_save_and_load(), test_last_file_handling()

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BaseStealthWindow` connect `Book & Chapter Core Models` to `Book & Chapter Core Models`, `Book & Chapter Core Models`, `GUI Mock & Unit Testing`, `Downloader & Search UI`?**
  _High betweenness centrality (0.397) - this node is a cross-community bridge._
- **Why does `DownloadDialog` connect `Downloader & Search UI` to `Book & Chapter Core Models`, `Book & Chapter Core Models`, `SoNovel Integration & Rules`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Why does `SoNovelClient` connect `SoNovel Integration & Rules` to `Downloader & Search UI`?**
  _High betweenness centrality (0.145) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `BaseStealthWindow` (e.g. with `Book` and `NovelParser`) actually correct?**
  _`BaseStealthWindow` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `ConfigManager` (e.g. with `NovelReadApp` and `TestConfig`) actually correct?**
  _`ConfigManager` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Book` (e.g. with `EpubParser` and `NovelParser`) actually correct?**
  _`Book` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `Chapter` (e.g. with `EpubParser` and `NovelParser`) actually correct?**
  _`Chapter` has 7 INFERRED edges - model-reasoned connections that need verification._