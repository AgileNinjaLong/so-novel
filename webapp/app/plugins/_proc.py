"""子进程工具：启动、按行读取输出、终止进程树。"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
from typing import IO, Callable

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


class LineReader:
    """把子进程 stdout 拆成行，过滤 ANSI 转义，回调给上层。"""

    def __init__(self, stream: IO[str], on_line: Callable[[str], None]):
        self._stream = stream
        self._on_line = on_line
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        try:
            for raw in iter(self._stream.readline, ""):
                if self._stop:
                    return
                line = strip_ansi(raw.rstrip("\r\n"))
                if not line:
                    continue
                try:
                    self._on_line(line)
                except Exception:
                    pass
        except Exception:
            return


def spawn(
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    kwargs: dict = {
        "cwd": cwd,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)


def terminate_tree(proc: subprocess.Popen, *, timeout: float = 10.0) -> None:
    """尽力终止整个进程树（Java 会 fork 线程，Rust 服务可能有子进程）。"""
    if proc.poll() is not None:
        return
    try:
        if sys.platform.startswith("win"):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
            try:
                proc.wait(timeout=min(timeout, 5.0))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=timeout)
    except Exception:
        pass
