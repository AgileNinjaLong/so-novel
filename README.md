# NovelRead - 摸鱼看小说软件 (Office Stealth Novel Reader)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green)
![Tests](https://img.shields.io/badge/Tests-pytest-brightgreen)

专为办公/开发环境设计的极简高隐蔽性桌面小说阅读器。支持市面常见格式（TXT / EPUB / PDF），拥有毫秒级全局老板键与多种伪装外观模式。

---

## 🌟 核心亮点与隐蔽模式

1. **极简透明悬浮窗 (Floating Strip Mode)**：
   * 无边框、极窄半透明文本行，可悬浮在 IDE 或 Word 上方。
   * 鼠标离开窗口自动隐形（降至 15% 透明度）。
2. **IDE / 控制台日志伪装 (IDE Pseudo Mode)**：
   * 按 **`F12`** 一键切换。
   * 界面伪装为 VS Code 终端控制台，小说文字自然混入 Python/C++ 调试日志与 `# [DEBUG]` 注释中。
3. **毫秒级全局老板键 (Boss Key)**：
   * 默认快捷键 **`Alt + Z`** 或 **`Esc`** 瞬间隐藏/恢复窗口，无任务栏残留。
4. **全格式智能解析与自动续读**：
   * **TXT**：智能编码识别（UTF-8, GBK, GB2312, UTF-16 防乱码），自动正则切分章节目录。
   * **EPUB**：提取 HTML/XHTML 网页文档，纯文本滤除及目录映射。
   * **PDF**：页面纯文本抽离流。
   * 自动保存每本书的最后阅读位置与章节。

---

## 📂 项目结构

```
novelRead/
├── gemini/                # 项目初期规格说明文件 (PM与架构师成果)
│   ├── SRS.md             # 软件需求规格说明书 (含黑盒测试矩阵)
│   └── SDS.md             # 软件设计规格说明书 (架构与技术选型)
├── src/                   # 核心源代码
│   ├── main.py            # 应用启动总入口
│   ├── core/              # 图书数据模型、解析引擎与配置持久化
│   ├── ui/                # PyQt6 摸鱼 UI 界面与老板键监听器
│   └── utils/             # 字符编码智能识别等工具库
├── tests/                 # pytest 单元测试套件
└── requirements.txt       # 项目依赖库清单
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行软件

```bash
python -m src.main
```

### 3. 操作快捷键

* **拖拽打开**：把 `.txt` / `.epub` / `.pdf` 文件直接拖进软件窗口即可打开。
* **`F12`**：切换【极简透明悬浮窗】与【IDE 伪装控制台】模式。
* **`Alt + Z` 或 `Esc`**：触发老板键（一秒完全隐形/重新唤醒）。
* **方向键 `←` / `→` / `↑` / `↓` 或 鼠标滚轮**：上一行 / 下一行 / 切章。
* **鼠标右键**：打开文件对话框、查看章节列表、退出。

---

## 🧪 运行单元测试 (Unit Testing)

所有核心解析逻辑、编码助手及 GUI mock 测试均可通过 `pytest` 自动化运行：

```bash
pytest -v
```
