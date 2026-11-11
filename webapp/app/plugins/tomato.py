"""来源插件 B：zhongbai2333/Tomato-Novel-Downloader（Rust 版）。

上游 CLI **没有**「新建下载」的非交互入口（`--download` 已被禁用，只保留 `--update <book_id>`，
且只更新本地已存在的书）。因此本插件不改写其逻辑，而是**引用它自带的 Web 服务**：
    Tomato-Novel-Downloader --server --data-dir <dir> --password <pwd>
然后通过它的 HTTP API 完成「搜索 → 建任务 → 轮询进度 → 取文件」。

以下事实来自上游源码（决定实现方式）：
- 认证：带 `--password` 时，除 `/`、`/assets/*`、`/api/login` 外的所有路由都要求
  请求头 `x-tomato-password: <password>`（或 cookie `tomato_session`）。用请求头最简单。
- 搜索：`GET /api/search?q=`，返回 `{"items":[{book_id,title,author,raw}]}`（需 official-api 构建）。
- 建任务：`POST /api/jobs`，body `{"book_id": "..."}`；返回 `{"id": n, "book_id": "...", "state": "queued"}`。
- 上游自身限制：同时只允许一个活跃任务（`count_active() >= 1` 直接 429），与本站「全局单线程」一致。
- 任务状态枚举（snake_case）：queued / running / done / failed / canceled。
- 进度：`GET /api/jobs?id=<id>`，任务对象里 `progress` 为
  `{group_done, group_total, saved_chapters, chapter_total, save_phase, ...}`。
- 阻塞点：若配置 `ask_format_after_download=true`，任务线程会等待客户端
  `POST /api/jobs/:id/format`；本插件在启动后把该配置写为 false，并把
  每个任务的格式在**建任务前**通过 `POST /api/config` 设定，从而避免卡住。
  同时兜底：若任务对象里仍出现 `format_options`/`book_name_options`，插件会立即回帖放行。
- 输出：`<save_path>/<书名>.<txt|epub|pdf>`（`prepare_output_path`）；`save_path` 由本插件
  在启动时通过 `/api/config/full` 指到自己的目录，避免与其他用途混用。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from ._proc import spawn, terminate_tree
from .base import CanceledError, Capabilities, DownloadResult, PluginStatus, SearchItem

TERMINAL_STATES = {"done", "failed", "canceled"}
STATE_LABELS = {
    "queued": "排队中",
    "running": "下载中",
    "done": "已完成",
    "failed": "失败",
    "canceled": "已取消",
}
SAVE_PHASE_LABELS = {
    "TextSave": "正在写入文件",
    "Audiobook": "正在生成有声书",
}


class TomatoPlugin:
    id = "tomato"
    name = "番茄小说"
    description = "番茄小说下载器（Rust），支持书名搜索与断点续传；通过其自带 Web API 驱动。"
    upstream = "https://github.com/zhongbai2333/Tomato-Novel-Downloader"
    capabilities = Capabilities(
        search=True,
        input_hint="可按书名搜索，也可直接粘贴 book_id（一串数字）。",
        formats=["txt", "epub"],
        notes="上游 CLI 禁止新建下载，因此这里引用它的 --server Web API（单任务串行）。",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc = None
        self._client: httpx.Client | None = None
        self._jobs: dict[str, int] = {}
        self._started_at = 0.0
        self._config_ready = False

    # ---------------- 路径 ----------------
    def _data_dir(self) -> Path:
        return Path(settings.tomato_data_dir)

    def _bin(self) -> Path | None:
        raw = settings.tomato_bin.strip()
        candidates: list[Path] = []
        if raw:
            candidates.append(Path(raw))
        candidates += [
            self._data_dir() / "bin" / _bin_name(),
            self._data_dir() / _bin_name(),
        ]
        for path in candidates:
            if path.is_file():
                return path
        found = shutil.which("tomato-novel-downloader") or shutil.which(
            "Tomato-Novel-Downloader"
        )
        return Path(found) if found else None

    def _base_url(self) -> str:
        return f"http://127.0.0.1:{settings.tomato_port}"

    def _headers(self) -> dict[str, str]:
        return {"x-tomato-password": settings.tomato_password}

    # ---------------- 状态 ----------------
    def status(self) -> PluginStatus:
        binary = self._bin()
        if binary is None:
            return PluginStatus(
                False,
                "未找到 Tomato-Novel-Downloader 可执行文件（请设置 TOMATO_BIN，"
                f"或放到 {self._data_dir() / 'bin'}）",
            )
        if self._server_alive():
            return PluginStatus(True, f"Web API 已就绪（{self._base_url()}）")
        return PluginStatus(True, f"可启动：{binary.name}（首次使用时自动拉起 --server）")

    def _server_alive(self) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(f"{self._base_url()}/api/status", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

    # ---------------- 生命周期 ----------------
    def _ensure_server(self) -> None:
        with self._lock:
            if self._client is not None and self._server_alive():
                return
            if self._server_alive():
                # 已有实例在跑（可能是上次遗留），直接复用
                self._client = httpx.Client(
                    base_url=self._base_url(),
                    headers=self._headers(),
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                self._config_ready = True
                return

            binary = self._bin()
            if binary is None:
                raise RuntimeError("未找到 Tomato-Novel-Downloader 可执行文件")

            data_dir = self._data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            log_path = data_dir / "server.log"

            # 关键：上游的 library_root 在服务启动时固定，且 --data-dir 不决定下载目录，
            # 因此必须在启动前把 save_path 写进 config.yml。
            self._write_config()

            env = dict(os.environ)
            env["TOMATO_WEB_ADDR"] = f"127.0.0.1:{settings.tomato_port}"
            env["TOMATO_WEB_PASSWORD"] = settings.tomato_password
            env["TOMATO_WEB_COOKIE_SECURE"] = "0"

            proc = spawn(
                [str(binary), "--server", "--data-dir", str(data_dir)],
                cwd=str(data_dir),
                env=env,
            )
            self._proc = proc
            self._started_at = time.time()

            deadline = time.time() + settings.tomato_start_timeout_sec
            while time.time() < deadline:
                if proc.poll() is not None:
                    tail = _tail(log_path)
                    raise RuntimeError(
                        f"番茄服务启动后立即退出（code={proc.returncode}）。{tail}"
                    )
                if self._server_alive():
                    break
                time.sleep(0.5)
            else:
                terminate_tree(proc)
                raise RuntimeError(
                    f"番茄服务在 {settings.tomato_start_timeout_sec}s 内未就绪，"
                    f"请检查端口 {settings.tomato_port} 是否被占用。日志：{_tail(log_path)}"
                )

            self._client = httpx.Client(
                base_url=self._base_url(),
                headers=self._headers(),
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
            self._config_ready = True
            self._verify_config()

    def _write_config(self) -> None:
        """启动前写入 config.yml：固定保存目录并关掉阻塞式交互。"""
        data_dir = self._data_dir()
        save_dir = data_dir / "library"
        save_dir.mkdir(parents=True, exist_ok=True)
        config_path = data_dir / "config.yml"
        content = "\n".join(
            [
                f"save_path: {json.dumps(str(save_dir))}",
                "novel_format: txt",
                "bulk_files: false",
                "allow_overwrite_files: true",
                "enable_audiobook: false",
                "auto_open_downloaded_files: false",
                "ask_format_after_download: false",
                "preferred_book_name_field: book_name",
                "use_official_api: true",
                "max_workers: 2",
                "auto_clear_dump: false",
                "",
            ]
        )
        # 仅在内容不同的时候重写，避免每次启动都动用户文件
        try:
            if config_path.is_file() and config_path.read_text(encoding="utf-8") == content:
                return
        except OSError:
            pass
        config_path.write_text(content, encoding="utf-8")

    def _verify_config(self) -> None:
        """确认上游确实把保存目录设成了我们的目录。"""
        client = self._client
        if client is None:
            return
        try:
            resp = client.get("/api/status")
            if resp.status_code == 200:
                cfg = (resp.json() or {}).get("config") or {}
                save_path = str(cfg.get("save_path") or "")
                expected = str(self._data_dir() / "library")
                if save_path and Path(save_path).resolve() != Path(expected).resolve():
                    raise RuntimeError(
                        f"番茄保存目录未生效：期望 {expected}，实际 {save_path}"
                    )
        except RuntimeError:
            raise
        except Exception:
            # 状态接口异常不影响下载，忽略
            pass

    def shutdown(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            if self._proc is not None:
                terminate_tree(self._proc)
                self._proc = None

    # ---------------- 搜索 ----------------
    def search(self, query: str) -> list[SearchItem]:
        self._ensure_server()
        client = self._client
        assert client is not None
        resp = client.get("/api/search", params={"q": query})
        if resp.status_code >= 400:
            raise RuntimeError(_error_message(resp))
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"上游提示：{data['error']}")
        return [
            SearchItem(
                title=item.get("title") or "",
                author=item.get("author") or "",
                book_ref=str(item.get("book_id") or ""),
                extra={"book_id": item.get("book_id")},
            )
            for item in data.get("items", [])
            if item.get("book_id")
        ]

    # ---------------- 下载 ----------------
    def download(
        self,
        *,
        task: dict[str, Any],
        progress,
        cancel_event: threading.Event,
        library_dir: str,
    ) -> DownloadResult:
        self._ensure_server()
        client = self._client
        assert client is not None

        fmt = task["fmt"]
        # 1) 建任务前先设定输出格式，避免触发上游的阻塞式格式询问
        patch = client.post(
            "/api/config",
            json={"novel_format": fmt, "ask_format_after_download": False},
        )
        if patch.status_code >= 400:
            raise RuntimeError(_error_message(patch))

        save_dir = Path(settings.tomato_data_dir) / "library"
        before = _snapshot_files(save_dir)
        job_started = time.time() - 1.0

        # 2) 创建任务
        resp = client.post("/api/jobs", json={"book_id": task["book_ref"]})
        if resp.status_code == 429:
            raise RuntimeError("上游同一时间只允许一个任务，稍后重试")
        if resp.status_code >= 400:
            raise RuntimeError(_error_message(resp))
        job_id = int(resp.json()["id"])
        self._jobs[task["id"]] = job_id

        # 3) 轮询
        finished_state = ""
        job: dict[str, Any] = {}
        last_pct = -1.0
        while True:
            if cancel_event.is_set():
                self._cancel_job(job_id)
                raise CanceledError()
            job = self._get_job(job_id, client)
            if job is None:
                # 被取消后上游会删除任务记录
                raise CanceledError() if cancel_event.is_set() else RuntimeError(
                    "上游任务记录已消失（可能被取消或过期）"
                )
            self._answer_pending_choices(client, job_id, job, fmt)

            state = str(job.get("state") or "")
            if job.get("title") and not task.get("title"):
                try:
                    progress(title=str(job["title"]))
                except TypeError:
                    pass

            pct = _progress_percent(job)
            message = _progress_message(job)
            if pct - last_pct >= 0.5 or message:
                last_pct = pct
                snap = job.get("progress") or {}
                progress(
                    done=int(snap.get("saved_chapters") or 0),
                    total=int(snap.get("chapter_total") or 0),
                    percent=pct,
                    message=message,
                )

            if state in TERMINAL_STATES:
                finished_state = state
                break
            time.sleep(1.0)

        if finished_state != "done":
            reason = str(job.get("message") or STATE_LABELS.get(finished_state, finished_state))
            raise RuntimeError(f"番茄下载失败：{reason}")

        # 4) 定位产物（<书名>.txt / .epub），移动到本站库目录
        title = str(job.get("title") or task.get("title") or "").strip()
        artifact = _find_output(save_dir, before, fmt, title, job_started)
        if artifact is None:
            raise RuntimeError("下载已完成，但未在上游保存目录找到输出文件")

        target_dir = Path(library_dir) / task["id"] / "files"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / artifact.name
        shutil.move(str(artifact), str(target))
        self._jobs.pop(task["id"], None)

        progress(done=0, total=0, percent=100.0, message="下载完成")
        return DownloadResult(
            file_path=str(target),
            title=title or None,
            extra={"book_id": task["book_ref"], "format": fmt},
        )

    def _get_job(self, job_id: int, client: httpx.Client) -> dict[str, Any] | None:
        resp = client.get("/api/jobs", params={"id": job_id, "all": "true"})
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise RuntimeError(_error_message(resp))
        items = resp.json().get("items") or []
        for item in items:
            if int(item.get("id") or 0) == job_id:
                return item
        return None

    def _answer_pending_choices(
        self, client: httpx.Client, job_id: int, job: dict[str, Any], fmt: str
    ) -> None:
        """兜底：上游若仍等待选择，立即回帖放行，避免任务挂起。"""
        formats = job.get("format_options")
        if formats:
            value = next(
                (o.get("value") for o in formats if str(o.get("value")).lower() == fmt),
                None,
            ) or (formats[0].get("value") if formats else None)
            if value:
                client.post(f"/api/jobs/{job_id}/format", json={"value": value})

        names = job.get("book_name_options")
        if names:
            value = names[0].get("value") if names else None
            client.post(f"/api/jobs/{job_id}/book_name", json={"value": value})

    def _cancel_job(self, job_id: int) -> None:
        client = self._client
        if client is None:
            return
        try:
            client.post(f"/api/jobs/{job_id}/cancel")
        except Exception:
            pass

    def cancel(self, task_id: str) -> None:
        job_id = self._jobs.get(task_id)
        if job_id is not None:
            self._cancel_job(job_id)


# ---------------- 辅助函数 ----------------


def _bin_name() -> str:
    import sys

    return "Tomato-Novel-Downloader.exe" if sys.platform.startswith("win") else "Tomato-Novel-Downloader"


def _error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text[:200] or f"HTTP {resp.status_code}"


def _progress_percent(job: dict[str, Any]) -> float:
    snap = job.get("progress") or {}
    total = int(snap.get("chapter_total") or 0)
    done = int(snap.get("saved_chapters") or 0)
    if total > 0:
        return min(99.0, done / total * 100.0)
    group_total = int(snap.get("group_total") or 0)
    group_done = int(snap.get("group_done") or 0)
    if group_total > 0:
        return min(99.0, group_done / group_total * 100.0)
    return 0.0


def _progress_message(job: dict[str, Any]) -> str:
    state = str(job.get("state") or "")
    snap = job.get("progress") or {}
    if state == "queued":
        return "上游排队中"
    if state == "running":
        total = int(snap.get("chapter_total") or 0)
        done = int(snap.get("saved_chapters") or 0)
        phase = SAVE_PHASE_LABELS.get(str(snap.get("save_phase") or ""), "")
        if total:
            text = f"已保存 {done}/{total} 章"
        else:
            text = "正在获取目录…"
        return f"{text}（{phase}）" if phase else text
    if state in TERMINAL_STATES:
        return STATE_LABELS.get(state, state)
    return state


def _snapshot_files(directory: Path) -> set[str]:
    try:
        return {p.name for p in directory.iterdir() if p.is_file()}
    except OSError:
        return set()


def _find_output(
    directory: Path,
    before: set[str],
    fmt: str,
    title: str,
    since_ts: float,
) -> Path | None:
    if not directory.is_dir():
        return None
    suffix = ".epub" if fmt == "epub" else ".pdf" if fmt == "pdf" else ".txt"
    candidates = []
    for p in directory.iterdir():
        if not p.is_file() or p.suffix.lower() != suffix:
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        # 新文件，或本次任务开始后被覆盖写出的同名文件
        if p.name not in before or stat.st_mtime >= since_ts:
            candidates.append(p)
    if not candidates:
        return None
    if title:
        for p in candidates:
            if p.stem == title or p.stem.startswith(title[:12]):
                return p
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _tail(path: Path, lines: int = 6) -> str:
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return " | ".join(content[-lines:])[:400]
