"""运行配置：全部通过环境变量控制，便于 Docker / systemd 部署。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_data_dir() -> str:
    # 未显式配置时，数据放在 webapp/data（与代码同级的本地目录，方便本机试跑）
    return str(Path(__file__).resolve().parent.parent / "data")


@dataclass
class Settings:
    # ---- 通用 ----
    data_dir: Path = field(
        default_factory=lambda: Path(_env_str("WEBAPP_DATA_DIR", _default_data_dir())).resolve()
    )
    host: str = field(default_factory=lambda: _env_str("WEBAPP_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("WEBAPP_PORT", 8080))
    # 可选：整站访问密码（留空表示不校验，公网部署强烈建议设置）
    password: str = field(default_factory=lambda: _env_str("WEBAPP_PASSWORD", ""))
    # 队列轮询间隔（前端使用），仅用于展示
    poll_interval_ms: int = field(default_factory=lambda: _env_int("WEBAPP_POLL_MS", 1500))
    # 单任务超时（秒），0 表示不限制
    task_timeout_sec: int = field(default_factory=lambda: _env_int("WEBAPP_TASK_TIMEOUT", 0))

    # ---- so-novel（freeok/so-novel，Java CLI）----
    sonovel_java: str = field(default_factory=lambda: _env_str("SONOVEL_JAVA", "java"))
    sonovel_jar: str = field(default_factory=lambda: _env_str("SONOVEL_JAR", ""))
    # 工作目录：需要包含 rules/，CLI 以该目录为 cwd 运行；默认 <data>/plugins/sonovel
    sonovel_work_dir: str = field(
        default_factory=lambda: _env_str("SONOVEL_WORK_DIR", "")
    )
    # 基础 config.ini（可覆盖），留空则使用工作目录下的 config.ini
    sonovel_config: str = field(default_factory=lambda: _env_str("SONOVEL_CONFIG", ""))

    # ---- Tomato-Novel-Downloader（Rust，--server 模式）----
    tomato_bin: str = field(default_factory=lambda: _env_str("TOMATO_BIN", ""))
    tomato_data_dir: str = field(
        default_factory=lambda: _env_str("TOMATO_DATA_DIR", "")
    )
    tomato_port: int = field(default_factory=lambda: _env_int("TOMATO_PORT", 18423))
    tomato_password: str = field(
        default_factory=lambda: _env_str("TOMATO_PASSWORD", "webapp-internal")
    )
    tomato_start_timeout_sec: int = field(
        default_factory=lambda: _env_int("TOMATO_START_TIMEOUT", 120)
    )
    # 番茄服务启动后等待预热（IID）的最长时间
    tomato_warmup_sec: int = field(
        default_factory=lambda: _env_int("TOMATO_WARMUP", 30)
    )

    def resolve(self) -> "Settings":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.sonovel_work_dir:
            self.sonovel_work_dir = str(self.data_dir / "plugins" / "sonovel")
        if not self.tomato_data_dir:
            self.tomato_data_dir = str(self.data_dir / "plugins" / "tomato")
        return self

    # 便捷派生路径
    @property
    def db_path(self) -> Path:
        return self.data_dir / "webapp.sqlite3"

    @property
    def library_dir(self) -> Path:
        d = self.data_dir / "library"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def runtime_dir(self) -> Path:
        d = self.data_dir / "runtime"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings().resolve()
