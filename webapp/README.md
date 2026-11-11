# 小说下载 WebUI（多来源插件 + 账号体系）

可部署在自己服务器上的网页端小说下载器。它本身**不实现站点解析或下载逻辑**，而是把两个成熟开源项目当作「来源插件」引用：

| 来源 ID | 上游项目 | 接入方式 | 能力 |
| --- | --- | --- | --- |
| `sonovel` | [freeok/so-novel](https://github.com/freeok/so-novel)（Java） | 直接调它自带的 **CLI**：`java -Dmode=cli -jar app.jar --url <详情页> --ext <格式>` | 按详情页链接下载；txt / epub / html / pdf |
| `tomato` | [zhongbai2333/Tomato-Novel-Downloader](https://github.com/zhongbai2333/Tomato-Novel-Downloader)（Rust） | 启动它自带的 **`--server`**，通过其 HTTP API 建任务/查进度/取文件 | 按书名搜索；txt / epub |

> **为什么番茄不走 CLI**：上游已禁用 CLI 的新建下载（`--download` 只保留友好报错，`--update` 只能更新本地已有的书），所以引用它自带的 Web API。

## 功能

- **账号体系**：完全取消匿名。注册必须输入管理员生成的**注册密钥**；管理员未生成密钥时，任何人都无法注册、也无法进入界面。登录使用 Cookie 会话（HttpOnly + SameSite=Lax）。
- **后台管理** `/admin`（独立管理员账号，由环境变量初始化）：
  - 生成 / 轮换 / 清空注册密钥（ai/nanoid 算法，21 字符）；
  - 查看用户列表、注册时间、最后登录、任务数、有效期；
  - 按 **+1 / +31 / +124 / +372 / 永久** 给用户**叠加**有效期；
  - 禁用 / 启用 / 删除用户；查看并取消全部任务。
- **有效期规则**：按天**叠加**（不是覆盖），剩余天数封顶 **uint16 = 65535 天**；`999999` 档位表示**永久有效**，用独立标记位，不参与天数计算。
- **多用户**：全局单线程下载，多人提交按序排队并显示 `排队中 · 第 N 位`；所有人能看到共享队列，但只有本人（或管理员）能取消/下载自己的任务。
- **来源切换**：下拉框切换插件。切换时可选「等当前任务结束后切换」或「立即取消并切换」；切换期间拒绝向旧来源提交新任务。
- **响应式界面**：桌面为双栏，手机窄屏自动折叠为单栏卡片（表格行在手机上变成带标签的卡片）。

## 界面

| 登录 | 注册 |
| --- | --- |
| ![登录](docs/screenshots/login.png) | ![注册](docs/screenshots/register.png) |

| 下载主界面 | 后台管理 |
| --- | --- |
| ![主界面](docs/screenshots/app.png) | ![后台](docs/screenshots/admin.png) |

移动端（390×844）：![移动端](docs/screenshots/app-mobile.png)

## 快速开始

### Docker（部署到服务器）

```bash
cd webapp
cp .env.example .env
# 必改：ADMIN_USERNAME / ADMIN_PASSWORD
docker compose up -d --build
# 打开 http://<服务器IP>:8080/
```

容器内置：Python 应用、JRE 21、so-novel 发布包、番茄二进制。首次启动会把上游产物铺到数据卷 `/data`（宿主机 `webapp/data`）。

### 本机运行

```bash
cd webapp
pip install -r requirements.txt
export WEBAPP_DATA_DIR="$(pwd)/data"
export ADMIN_USERNAME=admin ADMIN_PASSWORD='至少8位的口令'
python scripts/fetch_plugins.py --with-java   # 下载上游 Release + 便携 JRE21
python serve.py
```

## 首次使用流程

1. 用环境变量里的管理员账号登录 `/login` → 自动进入 `/admin`。
2. 在后台点「生成新密钥」，得到 21 位注册密钥（发给要使用的人）。
3. 对方打开 `/register`，输入用户名、密码和该密钥 → 注册成功后默认**未开通**（0 天）。
4. 管理员在后台给该用户点「+1 天 / +31 天 / …/ 永久」。
5. 用户即可在首页提交下载、排队、取回文件。

> 清空密钥后注册入口立即关闭；已登录用户不受影响。轮换密钥后旧密钥立刻失效。

## 权限模型

| 能力 | 未登录 | 已登录但未开通/过期 | 已登录且有效 | 管理员 |
| --- | --- | --- | --- | --- |
| 访问页面 | 跳转 `/login` | ✅ | ✅ | ✅ |
| 查看队列 | ❌ 401 | ✅ | ✅ | ✅ |
| 提交下载 / 搜索 / 切换来源 | ❌ | ❌ 403 | ✅ | ✅ |
| 取消 / 下载别人的任务 | ❌ | ❌ | ❌ 403 | ✅ |
| 后台管理 | ❌ | ❌ | ❌ 403 | ✅ |

## 有效期与密钥实现

- 密钥生成移植自 GitHub 开源项目 **ai/nanoid**（MIT）：密码学安全随机字节 + 掩码取模，21 字符约 **126 bit 熵**；数据库对注册密钥/用户名/会话令牌加唯一约束，碰撞时重试。
  - 注册密钥 21 字符；会话令牌 43 字符（约 258 bit 熵）；内部实体 ID 16 字符。
- 口令使用标准库 `hashlib.scrypt`（n=16384, r=8, p=1，随机盐），存储为 `scrypt$n$r$p$salt$hash`。
- 会话令牌只把 **sha256** 落库，数据库泄露也无法直接复用 Cookie；会话默认 30 天，过期自动清理。
- 登录/注册有内存限流（同 IP 每分钟 8 次，超出 429）。
- 有效期计算在 `app/validity.py`：`new_expiry = max(now, old_expiry) + days`，并把**剩余天数**封顶到 65535；`999999` 直接写 `permanent=1`。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ADMIN_USERNAME` | 空 | 管理员用户名（不设置则后台不可用） |
| `ADMIN_PASSWORD` | 空 | 管理员密码（≥8 位）；每次启动会按此同步口令 |
| `WEBAPP_DEFAULT_GRANT_DAYS` | `0` | 新注册用户默认赠送天数，0 = 需管理员开通 |
| `WEBAPP_COOKIE_SECURE` | `0` | HTTPS 部署设为 1 |
| `WEBAPP_HOST` / `WEBAPP_PORT` | `0.0.0.0` / `8080` | 监听地址 |
| `WEBAPP_DATA_DIR` | `webapp/data` | 数据目录（SQLite、下载产物、上游运行目录） |
| `WEBAPP_DEFAULT_SOURCE` | `sonovel` | 首次启动的默认来源 |
| `WEBAPP_TASK_TIMEOUT` | `0` | 单任务超时秒数，0 = 不限 |
| `WEBAPP_POLL_MS` | `1500` | 前端轮询间隔 |
| `SONOVEL_JAVA` / `SONOVEL_JAR` / `SONOVEL_WORK_DIR` | 自动探测 | so-novel CLI 相关路径（工作目录需含 `rules/`） |
| `SONOVEL_CONCURRENCY` | `8` | 单本内部章节并发（不影响任务级串行） |
| `TOMATO_BIN` / `TOMATO_PORT` / `TOMATO_PASSWORD` / `TOMATO_DATA_DIR` | 自动探测 / `18423` / `webapp-internal` | 番茄服务相关 |

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | `{username, password, invite_key}`；无密钥或密钥错误 403 |
| POST | `/api/auth/login` | `{username, password}` |
| POST | `/api/auth/logout` | 删除会话 |
| GET | `/api/auth/me` | 当前用户与剩余有效期 |
| GET | `/api/meta` | 来源列表/就绪状态/注册是否开放/当前用户（公开） |
| GET | `/api/state` | 队列快照（含 `mine` / `can_cancel` / `can_download`） |
| POST | `/api/source` | 切换来源 `{source, mode}` |
| GET | `/api/search?q=` | 仅支持搜索的来源（番茄） |
| POST | `/api/tasks` | 入队 `{source, title, book_ref, fmt}` |
| DELETE | `/api/tasks/{id}` | 取消（本人或管理员） |
| GET | `/api/tasks/{id}/download` | 下载（本人或管理员） |
| POST | `/api/cleanup` | 清理失败/取消记录（管理员） |
| GET | `/api/admin/overview` | 用户/密钥/任务总览（管理员） |
| POST/DELETE | `/api/admin/key` | 生成 / 清空注册密钥（管理员） |
| POST | `/api/admin/users/{id}/grant` | `{days}` ∈ 1/31/124/372/999999（管理员） |
| POST | `/api/admin/users/{id}/status` | `{status}` = active/banned（管理员） |
| DELETE | `/api/admin/users/{id}` | 删除用户（管理员） |
| POST | `/api/admin/tasks/{id}/cancel` | 取消任意任务（管理员） |
| GET | `/healthz` | 健康检查（公开） |

## 测试

```bash
cd webapp
python tests/test_security.py        # 单元：nanoid/口令/令牌
python tests/test_validity.py        # 单元：叠加、65535 封顶、永久
python tests/test_scheduler.py       # 单元：单线程队列、切换语义、任务归属
python tests/test_auth_blackbox.py   # 黑盒：真实 HTTP 下的注册/登录/权限/后台（19 组）
python tests/e2e_live.py             # 真实环境：多用户 + 真实上游下载（需先启动服务与管理员环境变量）
CHROME_PATH=<chrome> python tests/shot_ui.py <输出目录>   # 可选：界面截图
```

本机已跑通的真实下载（Windows + 官方 Release）：番茄 69 章 494 KB / 10 秒、199 章、1184 章（断点续传）、2728 章进度；so-novel《活着》11/11 章 277 KB。

**未在本机验证**：Docker 镜像构建（本机没有 Docker）。如构建失败，先检查 `SONOVEL_VERSION`/`TOMATO_VERSION` 对应资产名是否变化。

## 与上游的关系

- 代码零侵入：不 fork、不打补丁、不复制解析/下载实现，只调用官方 Release 的 CLI / Web API。
- 升级上游：改 `Dockerfile` 的 `SONOVEL_VERSION`/`TOMATO_VERSION`，或重跑 `scripts/fetch_plugins.py`。
- 上游行为提醒：so-novel 每次启动会向作者固定域名上报一次主机信息（无开关）；番茄启动会做 GitHub 更新检查与 IID 预热。

## 免责声明

本项目只做「调用上游工具」的外壳与账号管理。下载内容的使用需遵守当地法律法规与目标站点条款，仅供个人阅读备份；上游项目各自的免责声明同样适用于其下载行为。
