# 摸鱼看小说软件 (NovelRead) - 软件设计规格说明书 (SDS)

**文档版本**：v1.0  
**撰写角色**：系统架构师 (System Architect)  
**创建日期**：2026-08-04  
**存放目录**：`gemini/SDS.md`  

---

## 1. 技术选型与语言明确 (Technology Stack Selection)

根据 SRS 中对“高隐蔽性”、“轻量化低内存”、“毫秒级老板键响应”及“多样化文件格式解析”的明确要求，架构组对主流桌面开发方案进行了对比评估：

| 方案 | 开发语言与框架 | 优点 | 缺点 | 评估结论 |
| :--- | :--- | :--- | :--- | :--- |
| 方案 A | **Python 3.10+ & PyQt6 / PySide6** | 1. 窗口操控极强（透明度、无边框、置顶、老板键）。<br>2. 电子书解析生态极为丰富（`chardet`, `ebooklib`, `pypdf`）。<br>3. 开发维护速度快，迭代方便。 | 需打包为单文件可执行文件（PyInstaller/Nuitka）。 | **推荐方案 (首选)** |
| 方案 B | **Rust & Tauri 2.0 (React/TS)** | 体积极小（<15MB），内存占用极低（<30MB）。 | EPUB/MOBI 原生 Rust 解析器集成较繁琐。 | 备选方案 |
| 方案 C | **Node.js & Electron** | 前端开发极其方便。 | 内存占用过高（>150MB），容易被察觉。 | 不推荐 |

### **明确确定：本项目开发语言与核心框架**
*   **核心语言**：`Python 3.10+`
*   **GUI 框架**：`PyQt6` (用于高精度的透明度、无边框悬浮窗、置顶、老板键及事件监听)
*   **格式解析依赖**：
    *   `chardet` / `charset_normalizer`：TXT 文件字符编码智能识别（防乱码）
    *   `ebooklib` + `BeautifulSoup4`：EPUB 电子书结构解析与 DOM 抽取
    *   `pypdf`：PDF 纯文本流提取
    *   `keyboard` 或 `PyQt6` 全局事件拦截：全局老板键 (Boss Key)
*   **持久化**：`JSON` / `SQLite` 本地化配置与阅读进度索引

---

## 2. 系统整体架构设计 (System Architecture)

系统采用典型的 **三层架构（数据解析层 - 业务控制层 - 界面伪装层）**，架构图如下：

```
+-----------------------------------------------------------------------+
|                           GUI 展示与伪装层                            |
|  +---------------------+  +--------------------+  +----------------+  |
|  | 极简透明悬浮窗 View |  | Dev/IDE 代码伪装 View|  | Excel表格伪装View|  |
|  +---------------------+  +--------------------+  +----------------+  |
|                                    ^                                  |
+------------------------------------|----------------------------------+
                                     | Event & Data Binding
+------------------------------------v----------------------------------+
|                            业务逻辑控制层                              |
|  +---------------------+  +--------------------+  +----------------+  |
|  | 窗口控制器 (WinCtrl)|  | 老板键响应 (BossKey)|  | 阅读进度管理器 |  |
|  +---------------------+  +--------------------+  +----------------+  |
|                                    ^                                  |
+------------------------------------|----------------------------------+
                                     | Abstract Book Models
+------------------------------------v----------------------------------+
|                            格式解析引擎层                             |
|  +--------------+  +---------------+  +--------------+  +----------+  |
|  | TXT Parser   |  | EPUB Parser   |  | MOBI Parser  |  |PDF Parser|  |
|  +--------------+  +---------------+  +--------------+  +----------+  |
+-----------------------------------------------------------------------+
                                     ^
                                     | File Stream
                           +-------------------+
                           |  本地电子书文件   |
                           +-------------------+
```

---

## 3. 核心模块详细设计

### 3.0 解析层与视图层的绝对解耦验证 (Decoupling Verification)
> **架构声明**：当前的架构已完成绝对解耦。底层引擎 `NovelParser` 返回标准化的 `Book` 与 `Chapter` 数据模型；中层调度由 `ConfigManager` 控制进度。
> 无论未来新增多少种伪装模式（如已新增的 `CADPseudoView` 或未来的 Excel/Web 伪装），都**完全不需要**修改或引用中间解析器代码。各个新模式只需继承 `BaseStealthWindow`，实现各自的 `render_view()` 方法即可将文本展示到界面，严格符合开闭原则（OCP）。

### 3.1 数据解析与模型层 (Parser Engine)

统一抽取基础数据模型 `Book` 与 `Chapter`：

```python
class Chapter:
    title: str       # 章节标题
    content: str     # 章节纯文本内容
    index: int       # 章节序号

class Book:
    title: str             # 书名
    author: str            # 作者
    format: str            # 格式 (txt, epub, mobi, pdf)
    chapters: List[Chapter]# 章节列表
    current_chapter: int   # 当前读取章节
    current_position: int  # 当前读取位置/光标
```

#### 各格式解析策略：
1.  **TXT 解析器 (`TxtParser`)**：
    *   读取文件前 10KB 字节流，使用 `chardet` 判别编码（UTF-8, GBK 等）。
    *   使用正则表达式 `r'^(第[零一二三四五六七八九十百千万0-9]+[章回节集].*|Chapter\s+\d+.*)'` 进行分章提取。若无匹配项，则按固定字数（如 2000 字）切分为虚拟章节。
2.  **EPUB 解析器 (`EpubParser`)**：
    *   利用 `ebooklib` 解包 `.epub` 容器，提取 `ITEM_DOCUMENT`。
    *   通过 `BeautifulSoup` 过滤 `<style>`、`<script>` 及图片标签，输出纯净文本与 TOC 目录映射。
3.  **PDF 解析器 (`PdfParser`)**：
    *   利用 `pypdf.PdfReader` 按页读取文本，拼接为小说流。

### 3.2 窗口控制与伪装层 (Stealth Window Engine)

1.  **极简悬浮窗属性设置 (PyQt6)**：
    *   窗口标志：`Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool`（不在任务栏显示大图标）。
    *   半透明效果：`self.setWindowOpacity(alpha)` (支持 0.1~1.0 调节)。
    *   鼠标无缝划过变暗/透明度降至最隐秘状态。
2.  **IDE / CAD 伪装控制模式**：
    *   渲染模板库：内置 VS Code 终端控制台样式、AutoCAD 命令栏样式等。
3.  **快捷键路由中心 (`HotkeyManager` & `SettingsDialog`)**：
    *   移除固定硬编码，采用 `QShortcut` 实现每个摸鱼模式（如极简窗、IDE、CAD）专属局部快捷键映射。
    *   老板键通过 Win32 `RegisterHotKey` 实现原生免干扰监听。
    *   提供独立图形化界面 `SettingsDialog`，包含按键捕获控件（KeySequenceEdit）及实时防冲突校验逻辑。

### 3.3 状态与进度持久化 (Storage Module)

数据存放在用户本地配置目录 `~/.novelread/config.json` 或 `history.json` 中：
```json
{
  "settings": {
    "boss_key": "Alt+Z",
    "opacity": 0.85,
    "theme": "floating_strip",
    "font_size": 12
  },
  "history": {
    "D:/books/斗破苍穹.txt": {
      "chapter_index": 15,
      "character_offset": 340,
      "last_read_time": "2026-08-04 10:30:00"
    }
  }
}
```

### 3.4 SoNovel 聚合抓取引擎与多格式导出合成 (SoNovel Aggregator & Exporters)

```
                       +-----------------------------+
                       |   SoNovelClient Search UI   |
                       +-----------------------------+
                                      |
                     +---------------------------------+
                     |   SoNovelClient.search()        |
                     |  (ThreadPoolExecutor max=15)    |
                     +---------------------------------+
                                      |
                     +---------------------------------+
                     | Stable Sorting Engine           |
                     | (Score DESC > Source > Name)    |
                     +---------------------------------+
                                      |
                     +---------------------------------+
                     | DownloadWorker (Multi-threaded) |
                     +---------------------------------+
                                      |
             +------------------------+------------------------+
             |                        |                        |
             v                        v                        v
    +-----------------+      +------------------+     +------------------+
    | TXT Single File |      | EPUB Builder     |     | Multi-Chapter    |
    | (Merged Text)   |      | (ZipContainer)   |     | Directory (.txt) |
    +-----------------+      +------------------+     +------------------+
```

1. **确定性稳定排序引擎 (Deterministic Search Ranking Engine)**：
   * 为了解决多线程异步返回导致搜书列表两次搜索顺序不一致问题，建立三元组排序函数：
     `Score = ratio * 1000 - source_priority_weight`
   * 在搜索流式吐出和最终 `on_search_finished` 中，统一基于（相似度得分 > 规则权重 > 书源名称）进行 `stable_sort` 归一化处理。

2. **多格式合成器 (`EpubBuilder` & `MultiFileExporter`)**：
   * **TXT 单文件模式**：拼接全局纯文本带章节分界符。
   * **EPUB 电子书模式**：原生产生 `mimetype`, `META-INF/container.xml`, `OEBPS/content.opf`, `OEBPS/toc.ncx` 及 XHTML 章节模板，使用 `zipfile.ZipFile` 打包压制成标准 `.epub` 电子书。
   * **章节独立拆分模式**：在指定保存目录下创建小说同名文件夹，按照 `0001_第1章.txt` 顺序离散落盘。

---

## 4. 目录与代码结构规划

项目根路径结构规范：

```
novelRead/
├── gemini/                # 项目需求与设计文档目录 (SRS & SDS)
│   ├── SRS.md             # 软件需求规格说明书
│   └── SDS.md             # 软件设计规格说明书
├── src/                   # 源代码目录
│   ├── main.py            # 应用启动入口
│   ├── core/              # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── book.py        # 数据模型 (Book, Chapter)
│   │   ├── parser.py      # 文件解析引擎 (TXT, EPUB, PDF)
│   │   └── config.py      # 配置与历史记录管理
│   ├── ui/                # UI 界面与伪装组件
│   │   ├── __init__.py
│   │   ├── base_window.py # 基础无边框/悬浮窗口
│   │   ├── floating_view.py# 极简透明悬浮窗视图
│   │   ├── ide_pseudo_view.py # IDE伪装代码视图
│   │   └── boss_key.py    # 老板键全局监听器
│   └── utils/             # 工具函数
│       └── encoding.py    # 编码识别助手
├── tests/                 # 单元测试与集成测试代码
│   ├── __init__.py
│   ├── test_encoding.py   # 编码识别单元测试
│   ├── test_parser.py     # 电子书解析引擎单元测试
│   ├── test_config.py     # 配置与读写单测
│   └── test_gui_mock.py   # GUI核心逻辑 Mock 测试
├── requirements.txt       # 项目依赖库清单
└── README.md              # 项目说明文档
```

---

## 5. 开发路线图与演进计划

1.  **阶段一：基础设施构建**：创建依赖清单，实现核心数据模型及 TXT/EPUB 解析器。
2.  **阶段二：UI与摸鱼控制开发**：实现 PyQt6 极简透明悬浮窗、老板键与 IDE 伪装模式。
3.  **阶段三：格式扩展与调试**：完善 MOBI/PDF 支持，集成配置持久化与快捷键解绑。
4.  **阶段四：打包与交付**：进行多格式小说测试、内存与响应时间调优。
