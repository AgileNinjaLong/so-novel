"""测试支撑：在进程内启动一个真实的 uvicorn 服务（随机端口）。

注意：`app.config.settings` 是模块级单例，因此必须在 import 之前设置环境变量；
本模块的 `start_server()` 会把数据目录指到临时目录，并在服务停止时清理。
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class ServerHandle:
    base_url: str
    data_dir: str


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def start_server(extra_env: dict[str, str] | None = None) -> Iterator[ServerHandle]:
    data_dir = tempfile.mkdtemp(prefix="novel-auth-test-")
    env = {
        "WEBAPP_DATA_DIR": data_dir,
        "WEBAPP_HOST": "127.0.0.1",
        "ADMIN_USERNAME": "root",
        "ADMIN_PASSWORD": "admin-pass-123",
    }
    env.update(extra_env or {})
    for key, value in env.items():
        os.environ[key] = value

    port = _free_port()
    os.environ["WEBAPP_PORT"] = str(port)

    # 每个测试进程内只 import 一次；此时环境变量已经就位
    from app.main import app  # noqa: PLC0415

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline:
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("测试服务启动超时")

    # 等 /healthz 真正可访问
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)

    try:
        yield ServerHandle(base_url=base, data_dir=data_dir)
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=False)


def unique_name(prefix: str = "u") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"
