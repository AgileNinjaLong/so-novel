"""来源插件注册表。"""

from __future__ import annotations

import os
from typing import Any

from .base import Plugin


def build_plugins() -> dict[str, Plugin]:
    # 延迟导入，保证装配失败不会导致整个应用起不来
    from .sonovel import SoNovelPlugin
    from .tomato import TomatoPlugin

    factories = (SoNovelPlugin, TomatoPlugin)
    plugins: dict[str, Plugin] = {}
    for factory in factories:
        try:
            plugin = factory()
        except Exception as exc:  # pragma: no cover - 兜底
            print(f"[plugins] 初始化 {factory.__name__} 失败: {exc}")
            continue
        plugins[plugin.id] = plugin
    return plugins


def default_source(plugins: dict[str, Plugin]) -> str:
    wanted = os.environ.get("WEBAPP_DEFAULT_SOURCE", "").strip()
    if wanted and wanted in plugins:
        return wanted
    if plugins:
        return next(iter(plugins))
    raise RuntimeError("没有任何可用来源插件")


def describe_plugin(plugin: Plugin) -> dict[str, Any]:
    status = plugin.status()
    caps = plugin.capabilities
    return {
        "id": plugin.id,
        "name": plugin.name,
        "description": plugin.description,
        "upstream": plugin.upstream,
        "ready": status.ready,
        "status_detail": status.detail,
        "capabilities": {
            "search": caps.search,
            "input_hint": caps.input_hint,
            "formats": caps.formats,
            "notes": caps.notes,
        },
    }
