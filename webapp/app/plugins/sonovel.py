"""来源插件 A：freeok/so-novel（Java 版）。

接入方式是**直接调用上游自带的 CLI**，不复制其下载逻辑：
    java -Dmode=cli -Dconfig.file=<每任务 config.ini> -jar app.jar --url <详情页> --ext <fmt>

几个来自源码的关键事实（决定插件实现）：
- `SourceUtils` 在生产环境（无 .env 或 ENV!=dev）从 **工作目录** 下的 `rules/` 读取书源规则，
  因此子进程必须 `cwd=<含 rules 的目录>`。
- `[download] download-path` 决定产物目录；本插件为每个任务生成独立下载目录，
  避免并发/多用户时互相覆盖，也无需猜测文件名。
- 产物（`CrawlerPostHandler` → `*MergeHandler`）：
    txt:  <download-path>/书名(作者).txt
    epub: <download-path>/书名(作者).epub
    pdf:  <download-path>/书名(作者).pdf
    html: <download-path>/书名 (作者) HTML.zip
- 退出码不可靠（`Main` 里 CLI 结束一律 `System.exit(0)`），成功与否以**产物文件是否存在**判定。
- 进度：`LogUtils` 会写 `<cwd>/logs/书名 (作者) 章节下载 yyyy-MM-dd.log`，
  其中 `开始下载:《书名》(作者) 共计 N 章` 给出了总章节数；每章一个临时文件，
  可通过统计临时目录中的章节文件数得到已完成章节。
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from . import _ini
from ._proc import LineReader, spawn, strip_ansi, terminate_tree
from .base import CanceledError, Capabilities, DownloadResult, PluginStatus, SearchItem

TOTAL_RE = re.compile(r"共计\s*(\d+)\s*章")
TITLE_RE = re.compile(r"开始下载[:：]\s*[《<]\s*(.+?)\s*[》>]\s*[(（]\s*(.*?)\s*[)）]")
CHAPTER_FILE_RE = re.compile(r"^\d+_.*(txt|html)$")


class SoNovelPlugin:
    id = "sonovel"
    name = "so-novel"
    description = "免费开源的多书源小说下载器（Java）。搜索用其 Web 接口，下载用其 CLI。"
    upstream = "https://github.com/freeok/so-novel"
    capabilities = Capabilities(
        search=True,
        input_hint="可输入书名搜索（聚合它自带的 13 个书源），也可以直接粘贴书籍详情页链接。",
        formats=["epub", "txt", "html", "pdf"],
        notes="搜索：临时启动上游 -Dmode=web 的 /search/aggregated；下载：-Dmode=cli。",
    )

    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._search_proc: subprocess.Popen | None = None
        self._search_port: int | None = None
        self._search_lock = threading.Lock()

    # ---------------- 状态 ----------------
    def _work_dir(self) -> Path:
        return Path(settings.sonovel_work_dir)

    def _jar_path(self) -> Path | None:
        raw = settings.sonovel_jar.strip()
        candidates: list[Path] = []
        if raw:
            candidates.append(Path(raw))
        candidates += [
            self._work_dir() / "app.jar",
            self._work_dir() / "sonovel.jar",
        ]
        for path in candidates:
            if path.is_file():
                return path
        return None

    def _rules_dir(self) -> Path:
        return self._work_dir() / "rules"

    def _java_path(self) -> str | None:
        """java 可执行文件：显式配置 > PATH > 本目录内置便携 JRE。"""
        import sys

        explicit = settings.sonovel_java.strip()
        if explicit and explicit not in {"java", "java.exe"} and Path(explicit).is_file():
            return explicit
        found = shutil.which(explicit or "java")
        if found:
            return found
        bundled = list((Path(settings.data_dir) / "plugins" / "java").glob("*/bin/java*"))
        for candidate in bundled:
            if candidate.is_file() and candidate.name in {"java", "java.exe"}:
                return str(candidate)
        return None

    def status(self) -> PluginStatus:
        jar = self._jar_path()
        if jar is None:
            return PluginStatus(
                False,
                f"未找到 so-novel 的 app.jar（请放到 {self._work_dir() / 'app.jar'}，"
                f"或设置 SONOVEL_JAR）",
            )
        if not self._rules_dir().is_dir():
            return PluginStatus(
                False,
                f"未找到书源规则目录 {self._rules_dir()}（发布包里的 rules/ 需要一并放入）",
            )
        # 上游会从 cwd 读 .env；一旦存在就切到 dev 行为（config-dev.ini + bundle/rules）
        if (self._work_dir() / ".env").exists():
            return PluginStatus(
                False,
                f"工作目录存在 .env 文件，会让上游切换到开发模式；请删除 {self._work_dir() / '.env'}",
            )
        java = self._java_path()
        if not java:
            return PluginStatus(
                False,
                "未找到 Java 21（请安装 JRE 21，或用 fetch_plugins.py --with-java 下载便携 JRE）",
            )
        return PluginStatus(True, f"CLI 就绪：{jar.name}")

    # ---------------- 搜索（借用上游 Web 模式的聚合搜索） ----------------
    def search(self, query: str) -> list[SearchItem]:
        """调用上游 `-Dmode=web` 的 /search/aggregated，返回带详情页链接的结果。"""
        status = self.status()
        if not status.ready:
            raise RuntimeError(status.detail)
        query = query.strip()
        if not query:
            return []
        base = self._ensure_search_server()
        try:
            resp = httpx.get(
                f"{base}/search/aggregated",
                params={"kw": query, "searchLimit": 30},
                timeout=90.0,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"搜索请求失败：{exc}")
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"搜索结果不是合法 JSON（HTTP {resp.status_code}）")
        code = data.get("code")
        if code != 200:
            raise RuntimeError(str(data.get("message") or f"搜索失败（code={code}）"))
        items: list[SearchItem] = []
        for row in data.get("data") or []:
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            items.append(
                SearchItem(
                    title=str(row.get("bookName") or "").strip(),
                    author=str(row.get("author") or "").strip(),
                    book_ref=url,
                    extra={
                        "source": row.get("sourceName"),
                        "latest_chapter": row.get("latestChapter"),
                        "updated": row.get("lastUpdateTime"),
                    },
                )
            )
        return items

    def _ensure_search_server(self) -> str:
        """按需启动一个 web 模式 JVM 专门做搜索（与下载用的 CLI 进程互不影响）。"""
        with self._search_lock:
            if self._search_proc is not None and self._search_proc.poll() is None:
                if self._search_port and self._port_alive(self._search_port):
                    return f"http://127.0.0.1:{self._search_port}"

            work = self._work_dir()
            port = self._free_port()
            config_path = work / "search.ini"
            _write_search_config(config_path, port, work)
            argv = [
                self._java_path() or settings.sonovel_java,
                # 并发下载时每个 JVM 都占内存，这里给个上限避免把机器压垮
                f"-Xmx{os.environ.get('SONOVEL_XMX', '512m')}",
                "-Dmode=web",
                f"-Dconfig.file={config_path}",
                "-Dfile.encoding=UTF-8",
                "-jar",
                str(self._jar_path()),
            ]
            proc = spawn(argv, cwd=str(work), env=dict(os.environ))
            self._search_proc = proc
            self._search_port = port

            deadline = time.time() + 90
            while time.time() < deadline:
                if proc.poll() is not None:
                    self._search_proc = None
                    raise RuntimeError("so-novel 搜索服务启动失败，请检查日志")
                if self._port_alive(port):
                    return f"http://127.0.0.1:{port}"
                time.sleep(0.5)
            terminate_tree(proc)
            self._search_proc = None
            raise RuntimeError("so-novel 搜索服务在 90 秒内未就绪")

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    @staticmethod
    def _port_alive(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            return False

    def _stop_search_server(self) -> None:
        proc = self._search_proc
        self._search_proc = None
        self._search_port = None
        if proc is not None:
            terminate_tree(proc)
            (self._work_dir() / "search.ini").unlink(missing_ok=True)

    # ---------------- 下载 ----------------
    def download(
        self,
        *,
        task: dict[str, Any],
        progress,
        cancel_event: threading.Event,
        library_dir: str,
    ) -> DownloadResult:
        status = self.status()
        if not status.ready:
            raise RuntimeError(status.detail)

        jar = self._jar_path()
        work = self._work_dir()
        task_dir = Path(library_dir) / task["id"]
        download_dir = task_dir / "download"
        download_dir.mkdir(parents=True, exist_ok=True)

        # 每个任务一份 config.ini：独立下载目录 + 关闭进度条（用文件计数代替 ANSI 解析）
        config_path = task_dir / "config.ini"
        base_config = settings.sonovel_config or str(work / "config.ini")
        _ini.write_overrides(
            base_config if Path(base_config).is_file() else None,
            str(config_path),
            {
                "global": {"auto-update": "0"},
                "download": {
                    "download-path": str(download_dir),
                    "extname": task["fmt"],
                    "enable-progressbar": "0",
                    "preserve-chapter-cache": "0",
                },
                "web": {"enabled": "0"},
                "crawl": {"concurrency": os.environ.get("SONOVEL_CONCURRENCY", "8")},
            },
        )

        argv = [
            self._java_path() or settings.sonovel_java,
            # 每个任务一个 JVM，限制堆大小以便多任务并发
            f"-Xmx{os.environ.get('SONOVEL_XMX', '512m')}",
            "-Dmode=cli",
            f"-Dconfig.file={config_path}",
            "-Dfile.encoding=UTF-8",
            "-jar",
            str(jar),
            "--url",
            task["book_ref"],
            "--ext",
            task["fmt"],
        ]

        env = dict(os.environ)
        env["JAVA_TOOL_OPTIONS"] = ""

        # 上游把日志写在共享的 cwd/logs 下，必须只认「本任务开始之后」写出的日志，
        # 否则会读到上一个任务的日志，导致书名/总章数串台。
        started_at = time.time() - 2
        proc = spawn(argv, cwd=str(work), env=env)
        with self._lock:
            self._procs[task["id"]] = proc

        state: dict[str, Any] = {"total": 0, "title": "", "author": "", "error": "", "tail": []}

        def on_line(line: str) -> None:
            line = strip_ansi(line)
            if not line:
                return
            state["tail"].append(line)
            if len(state["tail"]) > 30:
                del state["tail"][:-30]
            match = TOTAL_RE.search(line)
            if match:
                state["total"] = int(match.group(1))
            match_title = TITLE_RE.search(line)
            if match_title and not state["title"]:
                # 仅用于日志/提示，绝不覆盖用户提交的书名
                state["title"] = match_title.group(1)
                state["author"] = match_title.group(2)
                progress(message=f"正在下载《{task['title']}》")
            if "[ERROR]" in line or "[WARN]" in line:
                state["error"] = line[:300]

        reader = LineReader(proc.stdout, on_line)
        reader.start()

        started = time.time()
        last_pct = -1.0
        last_log_check = 0.0
        try:
            while True:
                if cancel_event.is_set():
                    terminate_tree(proc)
                    raise CanceledError()
                code = proc.poll()
                if code is not None:
                    break
                total = state["total"]
                # 进度条关闭时逐章日志会走控制台；若上游把该行吞掉，则回落到读日志文件
                if total <= 0 and time.time() - last_log_check > 2.0:
                    last_log_check = time.time()
                    title, author, log_total = _read_log_info(work, since=started_at)
                    if log_total > 0:
                        state["total"] = log_total
                    if title and not state["title"]:
                        state["title"] = title
                        state["author"] = author
                        progress(message=f"正在下载《{task['title']}》")
                    total = state["total"]
                done = _count_chapters(download_dir)
                if total > 0:
                    pct = min(99.0, done / total * 100.0)
                    if pct - last_pct >= 1.0:
                        last_pct = pct
                        progress(
                            done=done,
                            total=total,
                            percent=pct,
                            message=f"已下载 {done}/{total} 章",
                        )
                elif done > 0:
                    progress(done=done, total=0, message=f"已下载 {done} 章")
                if settings.task_timeout_sec and time.time() - started > settings.task_timeout_sec:
                    terminate_tree(proc)
                    raise RuntimeError("任务超时，已被终止")
                time.sleep(0.8)
        finally:
            reader.stop()
            with self._lock:
                self._procs.pop(task["id"], None)
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass

        # 收尾：产物判定（退出码不可信）
        artifact = _find_artifact(download_dir, task["fmt"])
        if artifact is None:
            tail = _tail_log(work, state["title"], state["author"], since=started_at)
            shutil.rmtree(download_dir, ignore_errors=True)
            message = "未生成下载文件"
            if state["error"]:
                message += f"：{state['error']}"
            stdout_tail = " | ".join(state["tail"][-6:]) if state["tail"] else ""
            if stdout_tail:
                message += f"\n上游输出：{stdout_tail}"
            if tail:
                message += f"\n最后日志：{tail}"
            raise RuntimeError(message)

        final_dir = task_dir / "files"
        final_dir.mkdir(parents=True, exist_ok=True)
        target = final_dir / artifact.name
        shutil.move(str(artifact), str(target))
        # 清理临时章节目录与下载目录
        shutil.rmtree(download_dir, ignore_errors=True)

        progress(done=state["total"] or 0, total=state["total"] or 0, percent=100.0, message="下载完成")
        return DownloadResult(
            file_path=str(target),
            title=state["title"] or None,
            extra={"author": state["author"], "format": task["fmt"]},
        )

    def cancel(self, task_id: str) -> None:
        with self._lock:
            proc = self._procs.get(task_id)
        if proc is not None:
            terminate_tree(proc)

    def shutdown(self) -> None:
        self._stop_search_server()
        with self._lock:
            procs = list(self._procs.values())
            self._procs.clear()
        for proc in procs:
            terminate_tree(proc)


def _write_search_config(path: Path, port: int, work: Path) -> None:
    """生成仅用于搜索的配置：打开 web 模式、指定端口。"""
    text = "\n".join(
        [
            "[global]",
            "auto-update = 0",
            "",
            "[download]",
            f"download-path = {work / 'runtime-search-tmp'}",
            "extname = epub",
            "",
            "[source]",
            # 搜索可以单独指定规则文件（剔除慢源可以显著降低搜索耗时）
            f"active-rules = {os.environ.get('SONOVEL_SEARCH_RULES', 'main.json')}",
            "search-limit = 30",
            "search-filter = 1",
            "",
            "[crawl]",
            # 聚合搜索会逐个书源抓取+解析，并发越高越快（13 个书源按并发数并行）
            f"concurrency = {os.environ.get('SONOVEL_SEARCH_CONCURRENCY', '8')}",
            "",
            "[web]",
            "enabled = 1",
            f"port = {port}",
            "",
            "[cookie]",
            "qidian =",
            "",
            "[proxy]",
            "enabled = 0",
            "host = 127.0.0.1",
            "port = 7890",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


# ---------------- 辅助函数 ----------------


def _count_chapters(download_dir: Path) -> int:
    """统计当前任务临时目录下的章节文件数量（每章一个文件）。"""
    count = 0
    try:
        for child in download_dir.iterdir():
            if not child.is_dir():
                continue
            for sub in child.iterdir():
                if sub.is_file() and CHAPTER_FILE_RE.match(sub.name):
                    count += 1
    except OSError:
        return count
    return count


def _find_artifact(download_dir: Path, fmt: str) -> Path | None:
    """在任务下载目录里找工作完成后生成的文件。"""
    if not download_dir.is_dir():
        return None
    direct = [p for p in download_dir.iterdir() if p.is_file()]
    desired = {
        "txt": ".txt",
        "epub": ".epub",
        "pdf": ".pdf",
        "html": ".zip",
    }.get(fmt, f".{fmt}")
    matches = [p for p in direct if p.suffix.lower() == desired and p.stat().st_size > 0]
    if matches:
        return max(matches, key=lambda p: p.stat().st_size)
    return None


def _read_log_info(work: Path, since: float = 0.0) -> tuple[str, str, int]:
    """从上游的章节日志里读取书名/作者/总章节数（控制台被吞时的兜底）。

    `since` 用于只接受本任务开始之后写出的日志，避免读到上一个任务的日志。
    """
    logs = work / "logs"
    if not logs.is_dir():
        return "", "", 0
    candidates = [
        p
        for p in logs.glob("*章节下载*.log")
        if p.stat().st_mtime >= since
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return "", "", 0
    try:
        with open(candidates[0], "r", encoding="utf-8", errors="replace") as fp:
            lines = fp.readlines()[-200:]
    except OSError:
        return "", "", 0
    total = 0
    title = ""
    author = ""
    for line in lines:
        match = TOTAL_RE.search(line)
        if match:
            total = int(match.group(1))
        if not title:
            match_title = TITLE_RE.search(line)
            if match_title:
                title, author = match_title.group(1), match_title.group(2)
    return title, author, total


def _clean_line(line: str) -> str:
    """过滤掉控制字符、JAVA_TOOL_OPTIONS 噪声与明显的乱码行。"""
    text = "".join(ch for ch in line if ch.isprintable() or ch in " \t")
    text = text.strip()
    if not text:
        return ""
    if "JAVA_TOOL_OPTIONS" in text or "Picked up" in text:
        return ""
    # GBK/UTF-8 混用产生的替换字符行直接丢弃
    bad = sum(1 for ch in text if ch == "\ufffd")
    if bad > len(text) / 4:
        return ""
    return text


def _tail_log(work: Path, title: str, author: str, since: float = 0.0, lines: int = 3) -> str:
    """读取上游在 cwd/logs 下写的章节日志尾部，用于失败时给出可读原因。"""
    logs = work / "logs"
    if not logs.is_dir():
        return ""
    candidates = [
        p for p in logs.glob("*章节下载*.log") if p.stat().st_mtime >= since
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return ""
    try:
        content = candidates[0].read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    errors = [ln for ln in content if "[ERROR]" in ln or "[WARN]" in ln]
    picked = errors[-lines:] if errors else content[-lines:]
    cleaned = [c for c in (_clean_line(ln) for ln in picked) if c]
    return " | ".join(cleaned)[:180]
