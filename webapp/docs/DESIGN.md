# 设计说明

## 目标与约束

需求可以拆成四条硬约束：

1. 后端**引用**两个上游项目，不自己实现站点解析；
2. 前端能**下拉切换来源**，且两个来源实质是不同插件；
3. **一旦切换**，其他正在使用的来源必须停用（或者选择「下载结束之后再切」）；
4. 下载**单线程**；多用户同时使用时明确显示「排队中」。

第二轮需求追加：

5. 前端重构并兼容移动端；
6. 完全取消匿名：注册必须输入后台生成的密钥，没有密钥就无法注册、也无法进入界面；
7. 独立管理员账号 + 后台管理页（用户列表、有效期叠加、密钥管理、全部任务）；
8. 有效期档位 1/31/124/372/999999 天，**叠加**且封顶 uint16（65535 天），999999 记为永久；
9. 全部数据落库；密钥使用 GitHub 开源项目（ai/nanoid）的生成算法且不重复；

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

## 账号体系与后台管理

### 数据模型（SQLite）

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `users` | id, username(UNIQUE NOCASE), password_hash, role, status, permanent, expires_at | 账号与有效期 |
| `sessions` | token_hash(PK), user_id, expires_at, ip, ua | 只存令牌的 sha256 |
| `invite_keys` | id, key(UNIQUE), mode(open/bound), days, permanent, username, password_plain, status, used_by… | **一钥一用户**的注册密钥 |
| `tasks` | …, user_id, user_name, size_bytes, delivered_at | 下载记录；**不含文件内容/路径** |
| `settings` | key/value | 当前来源、待切换 |

`init_db()` 会对旧库做迁移：补 `tasks.user_id` / `user_name` / `size_bytes` / `delivered_at`；
把历史的 `status='success'` 归一为 `delivered`，并清空文件路径。启动时还会删除旧版本的
`data/library` 目录（新模型不再保留成品文件）。

### 注册与登录

- 注册：`invite_key` 必须与 `settings.registration_key` **常量时间比较**相等；密钥为空时直接 403。
- 新用户默认 0 天（`WEBAPP_DEFAULT_GRANT_DAYS` 可改），此时可登录、可看队列，但提交下载/搜索/切换会被 403 拦下并提示「未开通或已过期」。
- 登录成功签发 `nanoid(43)` 会话令牌，写 HttpOnly Cookie，库里只留 sha256；默认 30 天。
- 登录/注册按 IP 做内存限流（每分钟 8 次），超限 429。
- 管理员账号由 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 在启动时**创建或同步**（改环境变量即改口令，并清掉旧会话），且被强制设为 `permanent=1`。

### 注册密钥：一钥一账号（账号由用户自设）

- 管理员生成密钥时只选**有效期**（1/31/124/372 天或 999999=永久）与数量，**不生成账号**；
- 用户在 `/register` 查询密钥后，**自己设置用户名与密码**；注册成功时：
  - 创建账号（口令以 scrypt 哈希存 `users.password_hash`）；
  - 把该账号与口令明文写入密钥记录（`invite_keys.username` / `password_plain`），
    以便后台展示「密钥 ↔ 账号密码 ↔ 使用者」；
  - 密钥置 `used`；
- 每把密钥只能注册一次；未使用的可撤销，记录可删除（不影响已注册账号）；
- 若注册失败（用户名重复等），密钥**不会被消耗**，仍可重试。

> 明文口令是为满足后台展示需求而保存的，属于产品取舍；文档与后台均有安全提示。

### 抗暴力破解（持久化）

`app/throttle.py` 把失败计数写进 SQLite `throttle` 表，因此**重启不会被绕过**：

| scope | 维度 | 阈值 / 窗口 | 锁定 |
| --- | --- | --- | --- |
| `login_user` | 账号 | 5 / 15 分钟 | 15 分钟 |
| `login_ip` | IP | 20 / 15 分钟 | 15 分钟 |
| `register_ip` | IP | 10 / 60 分钟 | 60 分钟 |
| `keyinfo_ip` | IP | 30 / 60 分钟 | 60 分钟 |
| `redeem_ip` | IP | 10 / 60 分钟 | 60 分钟 |

锁定期内一律 429（带 `Retry-After`），即使密码正确也不例外；失败按次数线性延迟
（0.2s × 次数，最多 2s）；成功清零。口令校验用 scrypt + 常量时间比较，账号不存在时
也执行一次同样开销的校验，避免用户名枚举的时间侧信道。

### 交付：客户端确认后删除（ack）

```
scheduler 完成 → ready（file_path + size_bytes）
GET /download  → 流式返回，不删除
POST /ack      → 删除临时目录、状态 delivered
TTL sweep      → 超时未 ack → 删除、状态 expired
```

不用「响应结束即删除」，因为服务端无法区分「浏览器已保存成功」与「断开但内核缓冲已接收」；
改为前段 `fetch → blob → 保存 → ack`，保证**没有确认就不删**（最坏只是多留到 TTL）。


两个上游都没有可靠的「暂停后继续」：so-novel 无断点续传，番茄的续传依赖本地状态且
被我们的临时目录策略打断。因此：

- `pause()` 对 running 任务置取消标志并终止进程，最终状态记为 `paused`（不是 `canceled`）；
- 临时文件立即删除，进度不再保留；
- 暂停后只出现「重新下载」：`POST /api/tasks/{id}/retry` 会**新建任务并重新排队**
  （队列位置从队尾开始计算），旧任务保持 `paused` 供追溯。

### so-novel 搜索

so-novel 的 CLI 没有搜索，但它的 Web 模式有 `/search/aggregated`（聚合 13 个书源）。
插件在首次搜索时按需启动一个独立 JVM（`-Dmode=web -Dconfig.file=search.ini`，随机端口），
拿到 `data[].url`（详情页链接）后返回给前端；下载仍走 `-Dmode=cli`。搜索进程与下载进程互不影响，
插件 `shutdown()` 时会终止搜索进程并删除 `search.ini`。


### 密钥算法（ai/nanoid）

`app/security.py` 移植了 [ai/nanoid](https://github.com/ai/nanoid)（MIT）的生成逻辑：

```
mask = (2 << (len(alphabet) - 1).bit_length() - 1) - 1
step = int(1.6 * mask * size / len(alphabet))
逐字节取 alphabet[byte & mask]，凑够 size 个字符
```

- 注册密钥 21 字符（URL 安全字母表，≈126 bit 熵），每把独立生成；
- 会话令牌 43 字符（≈258 bit 熵）；
- 碰撞处理：数据库 UNIQUE 约束 + `unique_nanoid()` 重试；
  `nanoid` 移植时保留了上游「掩码越界字节跳过」的语义（否则小字母表会索引越界）；
- 口令：`hashlib.scrypt(n=16384, r=8, p=1, 随机盐)`，存 `scrypt$n$r$p$salt$hash`。

### 暂停 = 不可续传

两个上游都没有可靠的「暂停后继续」：so-novel 无断点续传，番茄的续传依赖本地状态且会被
临时目录策略打断。因此：

- `pause()` 对 running 任务置取消标志并终止进程，最终状态记为 `paused`（不是 `canceled`）；
- 临时文件立即删除，进度不再保留；
- 暂停后只出现「重新下载」：`POST /api/tasks/{id}/retry` 会**新建任务并重新排队**
  （队列位置从队尾开始计算），旧任务保持 `paused` 供追溯。

### 临时文件与 TTL

- 上游只能写磁盘，所以服务器只提供**临时中转**：`data/runtime/tmp/<task_id>/`；
- 待接收文件由清扫线程按 `WEBAPP_FILE_TTL_MIN`（默认 120 分钟）删除并标记 `expired`；
- 服务启动时清空整个 `runtime/tmp`，把遗留的 `ready` 标记为 `expired`（DB 里不留路径）；
- 数据库只保留「谁、什么时候、下了哪本书、多大、什么状态」，没有小说内容。

### 有效期数学

`app/validity.py`：

```
is_active(user) = status == active and (permanent or expires_at > now)
grant(user, days):
    days >= 999999 → {permanent: 1, expires_at: None}
    否则 → expires = min(max(now, old_expiry) + days*86400, now + 65535*86400)
```

这样「叠加」就是把新天数加在**现有到期时间**上（过期账号从当前时间重新累计），
剩余天数绝不会超过 uint16 上限；`999999` 不再参与天数计算。

### 权限矩阵

| | 未登录 | 未开通 | 有效 | 管理员 |
| --- | --- | --- | --- | --- |
| 页面 | 跳 `/login` | ✅ | ✅ | ✅ |
| 队列只读 | 401 | ✅ | ✅ | ✅ |
| 提交/搜索/切换 | 401 | 403 | ✅ | ✅ |
| 取消/下载（他人任务） | 401 | 403 | 403 | ✅ |
| 后台接口 | 401 | 403 | 403 | ✅ |

任务快照按**查看者**计算 `mine` / `can_cancel` / `can_download` / `has_file`，
别人的失败原因与文件状态不会下发；服务端对每个操作再校验一次归属，前端标记只是提示。

### 前端响应式

- 桌面：`grid-template-columns: minmax(300px,400px) 1fr` 双栏；
- ≤900px：单栏；
- ≤760px：队列表格 `thead` 隐藏，`tr/td` 变块级卡片，用 `td[data-label]::before` 显示字段名；
- ≤560px：顶栏改为上下两行，避免品牌与用户徽章挤压。

## 已知限制

- 番茄同一时间只跑一本是上游硬编码（429），本站队列恰好匹配；但若宿主机同时有别的进程
  在用同一个番茄实例，会被上游拒绝。
- so-novel 单本内部仍按上游默认并发抓章节（可用 `SONOVEL_CONCURRENCY` 调小），
  「单线程」约束针对的是**任务级**，不是上游内部的章节并发。
- 两个来源都不支持「指定起止章节」：so-novel CLI 无此参数，番茄 API 虽有 `range_start/end`
  但本界面未暴露（避免误用导致静默全本下载）。
- 注册密钥只有「生成 / 轮换 / 清空」，没有手填自定义短语（需求要求用开源算法生成，故不提供弱口令入口）。
- 管理员账号来自环境变量：修改 `ADMIN_PASSWORD` 后重启即生效，同时会清掉管理员旧会话。
- 用户有效期以「天」为粒度，不支持小时级；`permanent` 用户不再显示天数。
