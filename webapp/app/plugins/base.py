"""插件接口：每个来源一个适配器，只负责「调用上游项目」，不重新实现下载逻辑。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class CanceledError(Exception):
    """任务被取消。"""


@dataclass
class PluginStatus:
    ready: bool
    detail: str = ""


@dataclass
class Capabilities:
    # 是否支持按书名搜索；False 表示只能输入链接
    search: bool
    # 前端提示语
    input_hint: str
    # 支持的导出格式
    formats: list[str]
    # 其他说明（显示在 UI）
    notes: str = ""


@dataclass
class SearchItem:
    title: str
    author: str = ""
    book_ref: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadResult:
    file_path: str | None
    title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


ProgressFn = Callable[..., None]


class Plugin(Protocol):
    """所有来源适配器实现的协议。"""

    id: str
    name: str
    description: str
    capabilities: Capabilities
    upstream: str

    def status(self) -> PluginStatus:
        ...

    def search(self, query: str) -> list[SearchItem]:
        ...

    def download(
        self,
        *,
        task: dict[str, Any],
        progress: ProgressFn,
        cancel_event: Any,
        library_dir: str,
    ) -> DownloadResult:
        ...

    def cancel(self, task_id: str) -> None:
        ...

    def shutdown(self) -> None:
        ...
