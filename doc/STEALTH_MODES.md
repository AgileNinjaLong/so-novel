# 23 种办公摸鱼伪装视图与事件转发规范文档

## 📌 设计理念

为了在办公场景下达到 100% 的高隐蔽性，NovelRead 提供了 **全套 23 种高频办公软件伪装阅读模式**。用户可通过右键上下文菜单子菜单或自定义快捷键在一瞬间将当前阅读窗口无缝切换为对应办公软件界面。

---

## 🎨 全套 23 种伪装模式注册表

全量伪装视图模块分布在 `src/ui/stealth_views/` 目录下（每个模式独立为单独的 Python 模块），统一由 `STEALTH_VIEW_MAP` 进行全量注册：

| 模式标识 Key | 伪装软件名称 | 对应模块文件 | UI 伪装元素特征 |
| :--- | :--- | :--- | :--- |
| `floating` | 📖 极简透明悬浮窗模式 | `src/ui/floating_view.py` | 纯透明背景、单/双行文本匀速向上滚动 |
| `ide_pseudo` | 💻 VS Code 编辑器模式 | `src/ui/ide_pseudo_view.py` | 代码行号、控制台输出日志与状态栏 |
| `cad_pseudo` | 📐 CAD 建筑图纸命令行模式 | `src/ui/cad_pseudo_view.py` | 纯黑底、Command 命令行提示符 |
| `excel_sheet` | 📊 Microsoft Excel 电子表格 | `src/ui/stealth_views/excel_view.py` | 绿色标题栏、表格网格、`fx` 公式栏 |
| `word_doc` | 📄 Microsoft Word 文档 | `src/ui/stealth_views/word_view.py` | 蓝色标题栏、工作汇报格式与排版 |
| `terminal_cli` | 🖥️ Windows Terminal / PowerShell | `src/ui/stealth_views/terminal_view.py` | 深蓝底色、`PS C:\System32>` 提示符 |
| `outlook_email` | ✉️ Outlook 邮件客户端 | `src/ui/stealth_views/outlook_view.py` | 邮件发件人/收件人/主题与分割线 |
| `swagger_api` | 🔌 Swagger UI API 文档 | `src/ui/stealth_views/swagger_view.py` | 绿色标签、JSON 响应体负载 |
| `git_diff` | 🔀 Git Commit Diff 提交对比 | `src/ui/stealth_views/git_diff_view.py` | `diff --git` 标识、`+` 代码新增行高亮 |
| `notion_markdown` | 📓 Notion 工作区笔记 | `src/ui/stealth_views/notion_view.py` | Markdown 块引用、Task 勾选框 |
| `pdf_reader` | 📑 Adobe Acrobat PDF 阅读器 | `src/ui/stealth_views/pdf_view.py` | 红色标题栏、IEEE 论文排版格式 |
| `stock_kline` | 📈 同花顺/通达信股票行情 | `src/ui/stealth_views/stock_view.py` | 上证指数红绿大盘、股票代码表格 |
| `json_validator` | 🔍 JSON Online Validator | `src/ui/stealth_views/json_view.py` | 语法高亮 JSON 结构树 |
| `sys_monitor` | 📊 Windows 资源监视器 | `src/ui/stealth_views/sysmon_view.py` | 进程 PID、内存/CPU 使用率网格 |
| `calculator_gui` | 🧮 金融计算器工具 | `src/ui/stealth_views/calc_view.py` | 计算历史栈、打印日志输出 |
| `database_dbeaver` | 🗄️ DBeaver 数据库客户端 | `src/ui/stealth_views/dbeaver_view.py` | SQL 查询编辑器、ResultSet 数据表 |
| `jupyter_notebook` | 🪐 Jupyter Notebook 交互式笔记本 | `src/ui/stealth_views/jupyter_view.py` | `In [1]:` / `Out [1]:` 代码单元格 |
| `deepl_translate` | 🌐 DeepL 智能翻译器 | `src/ui/stealth_views/deepl_view.py` | 双语对照、实时翻译面板 |
| `browser_devtools` | 🛠️ Chrome DevTools 开发者工具 | `src/ui/stealth_views/devtools_view.py` | Console 控制台轨迹与警告日志 |
| `chat_teams` | 💬 Microsoft Teams 沟通群 | `src/ui/stealth_views/teams_view.py` | 团队消息对话历史列表 |
| `logcat_viewer` | 📜 Server Log Stream 日志流 | `src/ui/stealth_views/logcat_view.py` | 时间戳与 `[INFO] [Thread]` 跟踪 |
| `markdown_editor` | 📝 Typora Markdown 编辑器 | `src/ui/stealth_views/markdown_view.py` | `#` 标题层级与文档预读 |
| `jenkins_ci` | ⚙️ Jenkins CI/CD 构建控制台 | `src/ui/stealth_views/jenkins_view.py` | `[BUILD-TRACE]` 构建日志输出 |

---

## 🖱️ 事件无缝转发与自由拖拽机制 (`src/ui/stealth_views/common.py`)

为了使复杂的伪装 UI（如包含 `QTableWidget` 或 `QTextEdit` 的界面）在鼠标点击、拖拽和滚轮滚动时依然能像普通无边框窗口一样随意无缝拖拽和翻页：

- 实现了 `ForwardTextEdit` 与 `ForwardTableWidget` 事件转发基类；
- 将子控件的 `mousePressEvent`、`mouseMoveEvent`、`mouseReleaseEvent`、`wheelEvent` 及 `contextMenuEvent` 全部重映射回宿主 `BaseStealthWindow`；
- 保证了在全套 23 种模式下：
  - **按住鼠标左键** 均可自由拖拽窗口位置；
  - **滚轮上下滚动** 均可精准按行推进阅读位置；
  - **鼠标右键点击** 均可弹出切换伪装模式与全局设置的右键上下文菜单。

---

## 🔄 实时阅读进度与快捷键绑决

1. **进度无缝同步**：每次模式切换（调用 `switch_to_mode`）时，新创建的伪装视图会自动将 `progress_updated_signal` 绑定至主书架 `BookshelfWindow.on_reading_progress_updated`，保证切换前后阅读进度一字不丢；
2. **全局老板键 (`Alt+Z`)**：触发时瞬间隐藏或唤醒全部打开的摸鱼阅读窗口；
3. **快捷键自定义**：所有 23 种模式均可在系统设置页（Tab 4）的 `QScrollArea` 中自由绑定专属快捷键。
