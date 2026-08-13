# 搜索与下载引擎深度对齐规范文档 (Search & Download Engine Spec)

## 🎯 核心设计目标

本模块完全根据开源项目 **so-novel-main**（Java 语言）的底层源码（`SearchResultsHandler.java`、`SearchParser.java`、`TocParser.java`、`ChapterParser.java`、`Crawler.java`、`ChapterFilter.java` 及 `CrawlUtils.java`）进行 100% 逐行逻辑对齐与 Python 重构，确保搜书准确度、目录解析完整性与高并发下载稳定性达到完全一致。

---

## 🔍 一、搜索解析与算法对齐 (`src/core/sonovel_client.py`)

### 1. 完全匹配 302 重定向直跳详情页 (`SearchParser.java`)
- **场景描述**：部分小说网站在搜索完全匹配的精确关键词时，服务端会自动执行 HTTP 302 重定向直接跳转至图书详情页，此时页面中不包含 `search.result` 匹配列表。
- **对齐实现**：在 `_search_single_rule` 中，若提取的 `items` 列表为空，但页面能匹配到 `book.bookName` 选择器元素，则系统自动识别为详情页，直取 `bookName`、`author`、`latestChapter` 并将 `resp.url` 作为结果返回，杜绝搜索遗漏。

### 2. 非线性权重判定算法 (`SearchResultsHandler.java`)
- **算法细节**：预先计算搜索关键词与各搜索结果的 `bookName` 及 `author` 的 Levenshtein 文本相似度，并通过 `_compute_weight` 函数计算全量权值：
  - 短关键词（`len <= 4`）：应用 $s^3 \times 8$ 陡峭三次曲线；
  - 长关键词（`len >= 10`）：应用平滑加权曲线；
  - 自动对比全量结果的 `book_sim_list` 与 `author_sim_list` 权重和：若作者权重和更高（如搜索“唐家三少”、“忘语”），系统自动判定为作者维度搜书，将作者匹配度置顶。

---

## 📥 二、目录解析与全量去重对齐 (`get_toc`)

### 1. `toc.list` 容器选择器裁切 (`TocParser.java`)
- **根因分析**：许多书源在目录页顶部包含“最新章节”快捷列表（如 1000~1005 章），随后的“正文卷”才包含 1~1005 章。若不裁切 DOM 容器，会导致抓取顺序变成 `[1000, 1001... 1, 2, 3...]`，造成乱序与错位。
- **对齐实现**：在提取章节链接前，若规则指定了 `toc.list`（如 `#chapter-list`），优先隔离提取该 DOM 容器节点，彻底杜绝顶部重复块干扰。

### 2. 跨页目录自动拼接与 `urljoin`
- 若规则包含 `toc.nextPage`（支持按钮及 `<select>` 下拉菜单），提取 `next_url` 时自动使用 `urllib.parse.urljoin(resp.url, next_url)` 转换绝对路径，循环抓取多页目录。

### 3. 保序 URL 去重与 `isDesc` 倒序校正
- 使用 `seen_urls` 对章节 URL 进行保序去重；若规则标注 `toc.isDesc: true`，则执行 `unique_chapters.reverse()` 正向校正。

---

## ⚡ 三、高并发爬虫与退避补章对齐 (`DownloadWorker`)

### 1. 线程并发数与防刷限流 (`Crawler.java` & `CrawlUtils.java`)
- **并发数计算**：
  $$\text{concurrency} = \min(\text{rule.crawl.concurrency} \mid 50, \, 100, \, \text{toc\_size})$$
  若书源规则（如 `rate-limit.json`）指定了限流并发数（如 `5` 或 `1`），严格按规则收敛；
- **防刷随机休眠**：每条并发线程在发起 HTTP 请求前，注入 `random.uniform(minInterval, maxInterval)` 毫秒随机休眠；
- **Socket 连接池**：线程池绑定 50 槽位的 `HTTPAdapter` 连接池，复用 TCP Socket。

### 2. 3 轮指数递增退避补漏重试
- 在高并发主流程结束后，若存在因网络限流导致的缺章 `(本章下载失败)`，自动开启 **3 轮退避补全重试**（重试间隔逐轮递增 1.5s ~ 3.0s），保障最终落盘完整度 100%。

---

## 🧹 四、文本清洗与格式规范 (`ChapterFilter.java`)

1. **不可见控制字符清洗**：使用 `re.sub(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\ufeff]', '', text)` 擦除所有 Unicode 私有区与控制符；
2. **正文首行标题重复擦除**：若提取的正文开篇包含了与章节标题重叠的字样，自动裁剪擦除；
3. **动态 Referer / Host 注入**：每次请求根据目标域名自动注入 `Referer: http://<domain>/` 与 `Host`，绕过防盗链检查；
4. **`ignoreSsl` 旁路校验**：若规则标注 `ignoreSsl: true`，自动添加 `verify=False` 跳过失效 SSL 证书校验。
