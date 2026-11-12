"""搜索服务：并发限流 + 结果短缓存。

上游（so-novel 的聚合搜索要 10~20 秒，番茄要查自己的服务）都不是无限并发的，
所以这里给一个进程内信号量控制同时进行的搜索数，并对相同「来源+关键词」做短缓存，
让多个用户可以同时搜、重复搜不重复打上游。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from .config import settings


class SearchService:
    def __init__(
        self,
        concurrency: int | None = None,
        cache_sec: int | None = None,
        cache_size: int = 200,
    ):
        self._sem = threading.BoundedSemaphore(
            max(1, int(concurrency if concurrency is not None else settings.search_concurrency))
        )
        self._cache_sec = max(
            0, int(cache_sec if cache_sec is not None else settings.search_cache_sec)
        )
        self._cache_size = max(16, cache_size)
        self._cache: OrderedDict[str, tuple[float, list[Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def _cached(self, key: str) -> list[Any] | None:
        if self._cache_sec <= 0:
            return None
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if now - entry[0] > self._cache_sec:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return entry[1]

    def _store(self, key: str, items: list[Any]) -> None:
        if self._cache_sec <= 0:
            return
        with self._lock:
            self._cache[key] = (time.time(), items)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def search(self, source: str, query: str, plugin: Any) -> tuple[list[Any], bool]:
        """返回 (结果, 是否命中缓存)。信号量保证同时搜索数不超过上限。"""
        key = f"{source}:{query.strip().lower()}"
        hit = self._cached(key)
        if hit is not None:
            return hit, True
        with self._sem:
            # 等锁期间可能已经有人搜完写入缓存，再查一次
            hit = self._cached(key)
            if hit is not None:
                return hit, True
            items = plugin.search(query)
            self._store(key, items)
            return items, False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_service: SearchService | None = None


def service() -> SearchService:
    global _service
    if _service is None:
        _service = SearchService()
    return _service
