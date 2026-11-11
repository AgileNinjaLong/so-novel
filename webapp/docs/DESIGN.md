# 设计说明

## 目标与约束

需求可以拆成四条硬约束：

1. 后端**引用**两个上游项目，不自己实现站点解析；
2. 前端能**下拉切换来源**，且两个来源实质是不同插件；
3. **一旦切换**，其他正在使用的来源必须停用（或者选择「下载结束之后再切」）；
4. 下载**单线程**；多用户同时使用时明确显示「排队中」。

## 为什么两个插件的接入方式不同

| | so-novel | 番茄下载器 |
| --- | --- | --- |
| 上游 CLI 能力 | `--url` + `--ext`，非交互、一次下载一本 | `--download` 被上游禁用；`--update` 只能更新本地已存在的书 |
| 采用的接入面 | 子进程调用 CLI | 子进程起 `--server`，走其 HTTP API |
| 依据 | `CliLauncher` 只有两个业务参数，满足「全本下载」 | 上游明确禁止 CLI 新建下载，Web API 是其官方交互面 |

结论：能用 CLI 的用 CLI（so-novel），不能用 CLI 的用上游自带 Web 服务（番茄）。
两者都是「引用上游能力」，没有复制其业务逻辑。

## 架构

```
浏览器
  │  HTTP / JSON（轮询 /api/state）
  ▼
FastAPI（app/main.py）
  │
  ├── store.py（SQLite：tasks + settings）
  └── scheduler.py（唯一工作线程）
         │
         ├── sonovel.py ──> java -Dmode=cli -jar app.jar --url ... --ext ...
         │                   （每任务独立 config.ini + 独立下载目录）
         └── tomato.py  ──> Tomato-Novel-Downloader --server
                             （HTTP：/api/search、/api/jobs、/api/config）
```

- **单线程**由 `Scheduler` 保证：只有一个 `novel-download-worker` 线程从 `tasks` 表取
  `queued` 中 `seq` 最小的一条执行。其它请求只写队列，不会并发下载。
- 任务的排队位置是实时算出来的：`status='queued' AND seq <= 自己` 的条数。
- 来源是**全局单值**（`settings.active_source`），持久化在 SQLite，重启后保留。

## 来源切换状态机

设当前来源 `A`，请求切到 `B`：

| 场景 | `after_current`（默认） | `cancel_now` |
| --- | --- | --- |
| 空闲（无 running） | 立即切换；取消队列中所有非 B 任务 | 同左 |
| 有 running 任务 | 记录 `pending_switch(B)`；**立即取消**队列中所有非 B 任务；等 running 结束后自动切换 | 取消 running（终止子进程 / 调用上游 cancel）+ 取消队列中非 B 任务，立即切换 |
| 切换请求后 | `active_source` 仍是 A，但**拒绝**向 A 提交新任务，提示「等待切换完成」 | 已切到 B，可直接提交 |

关键取舍：

- `pending_switch` 期间为什么连旧来源的**排队**任务也取消？
  因为需求是「一旦切换，其他正在使用的源必须切换」。若让旧来源队列继续跑，
  切换完成后这些任务就没有合法归属了；提前取消并明确提示，比事后静默丢弃更可预期。
- 正在下载的那一本为什么允许跑完（默认模式）？
  这正是需求里「或者说下载结束之后切换」的场景；中断一次已经下了一半的书代价更大，
  所以默认等它收尾。想立刻腾出来就用「立即取消并切换」。

## 进度与产物

### so-novel（CLI）

- 每任务在工作目录下生成独立 `config.ini`，覆盖：
  `download-path=<任务目录>`、`extname=<格式>`、`enable-progressbar=0`、
  `preserve-chapter-cache=0`、`[web] enabled=0`、`auto-update=0`、`concurrency=N`。
  - `[web] enabled` 必须为 0，否则上游会走 Web 分支而忽略 CLI 参数；
  - `enable-progressbar=0` 让逐章日志走控制台（否则只写文件），便于解析；
  - 独立下载目录避免两个任务同名互相覆盖，也省去猜文件名。
- 进度：从 `[INFO] 开始下载:《书名》(作者) 共计 N 章` 取总数；每章落一个临时文件，
  用「临时目录里的章节文件数」得到已完成数。若该行被上游日志级别吞掉，
  回落到读取 `<cwd>/logs/书名 (作者) 章节下载 yyyy-MM-dd.log`。
- 完成判定：**退出码不可信**（上游 CLI 收尾一律 `System.exit(0)`），因此以
  「任务下载目录里存在对应后缀的产物文件」为准；找不到时把日志尾部作为失败原因返回。
- 产物命名沿用上游：`书名(作者).txt|epub|pdf`，html 为 `书名 (作者) HTML.zip`。
  完成后移动到 `<data>/library/<taskId>/files/`。

### 番茄（`--server`）

- 启动前写 `<data>/plugins/tomato/config.yml`：`save_path` 指向本站目录、格式默认 txt、
  `ask_format_after_download=false`、`enable_audiobook=false`、`preferred_book_name_field=book_name`。
  - `save_path` 必须在**启动前**写好，因为上游的 `library_root` 在启动时固定；
  - 关掉「下载后询问格式/书名」可避免上游任务线程阻塞等待客户端回帖。
- 认证用请求头 `x-tomato-password`（上游支持，免登录 cookie）。
- 每个任务：先 `POST /api/config` 设定格式（避免阻塞式询问），再 `POST /api/jobs`，
  然后 `GET /api/jobs?id=` 轮询；上游若仍返回 `format_options`/`book_name_options`，
  插件会立即回帖默认值兜底。
- 上游自身限制「同时只允许 1 个活跃任务」（多提交返回 429），与本站串行策略天然一致。
- 进度取 `progress.saved_chapters / chapter_total`（上游不提供百分比）。
- 完成后按 `<save_path>/<书名>.<ext>` 定位文件并移动到本站库目录。

## 失败与取消

- 取消排队任务：直接置为 `canceled`。
- 取消下载中任务：置 `cancel_event` → 插件终止进程树（Windows `taskkill /T`，
  POSIX 杀进程组）或调用上游 `POST /api/jobs/:id/cancel`（协作式，按章节边界生效）。
- 服务重启：启动时把遗留的 `running` 标记为 `failed`（「服务重启导致任务中断」），
  队列里的任务保留继续排队。

## 已知限制

- 番茄同一时间只跑一本是上游硬编码（429），本站队列恰好匹配；但若宿主机同时有别的进程
  在用同一个番茄实例，会被上游拒绝。
- so-novel 单本内部仍按上游默认并发抓章节（可用 `SONOVEL_CONCURRENCY` 调小），
  「单线程」约束针对的是**任务级**，不是上游内部的章节并发。
- 两个来源都不支持「指定起止章节」：so-novel CLI 无此参数，番茄 API 虽有 `range_start/end`
  但本界面未暴露（避免误用导致静默全本下载）。
