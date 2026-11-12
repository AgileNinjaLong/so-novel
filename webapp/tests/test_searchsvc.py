"""单元测试：搜索服务的并发限流与缓存。

运行：python tests/test_searchsvc.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WEBAPP_DATA_DIR", tempfile.mkdtemp(prefix="novel-search-test-"))

from app.searchsvc import SearchService  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


class FakePlugin:
    def __init__(self, delay: float = 0.4, items: int = 3):
        self.delay = delay
        self.items = items
        self.calls = 0
        self.peak = 0
        self._active = 0
        self._lock = threading.Lock()

    def search(self, query: str):
        with self._lock:
            self._active += 1
            self.calls += 1
            self.peak = max(self.peak, self._active)
        time.sleep(self.delay)
        with self._lock:
            self._active -= 1
        return [{"title": f"{query}-{i}", "book_ref": f"r{i}", "author": "a", "extra": {}}
                for i in range(self.items)]


def main() -> int:
    print("[1] 相同关键词命中缓存（不重复打上游）")
    svc = SearchService(concurrency=2, cache_sec=60)
    plugin = FakePlugin(delay=0.3)
    t0 = time.time()
    items, cached = svc.search("sonovel", "战神", plugin)
    check(len(items) == 3, f"首次返回 {len(items)} 条")
    check(cached is False, "首次不是缓存")
    items2, cached2 = svc.search("sonovel", "战神", plugin)
    check(cached2 is True, "第二次命中缓存")
    check(plugin.calls == 1, f"上游只被调用 1 次（实际 {plugin.calls}）")
    print(f"  两次耗时 {time.time()-t0:.2f}s")

    print("[2] 不同关键词/不同来源不串缓存")
    svc.search("sonovel", "星辰变", plugin)
    svc.search("tomato", "战神", plugin)
    check(plugin.calls == 3, f"新增 2 次调用（实际 {plugin.calls}）")

    print("[3] 并发搜索不会超过上限，且都能拿到结果")
    svc2 = SearchService(concurrency=2, cache_sec=0)
    slow = FakePlugin(delay=1.0)
    results: list[list] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        items = svc2.search("sonovel", f"书{i}", slow)[0]
        with lock:
            results.append(items)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - t0
    check(len(results) == 6, f"6 个并发请求都有结果（{len(results)}）")
    check(slow.peak <= 2, f"同时调用上游不超过 2（峰值 {slow.peak}）")
    check(slow.calls == 6, f"不同关键词各调用一次（{slow.calls}）")
    print(f"  6 个并发（每次 1s、上限 2）总耗时 {elapsed:.2f}s")

    print("[4] 缓存过期后重新调用")
    svc3 = SearchService(concurrency=1, cache_sec=1)
    p3 = FakePlugin(delay=0.01)
    svc3.search("sonovel", "x", p3)
    time.sleep(1.2)
    _, cached3 = svc3.search("sonovel", "x", p3)
    check(cached3 is False, "过期后不命中缓存")
    check(p3.calls == 2, f"上游被调用 2 次（实际 {p3.calls}）")

    print("[5] clear() 清空缓存")
    svc4 = SearchService(concurrency=1, cache_sec=60)
    p4 = FakePlugin(delay=0.01)
    svc4.search("sonovel", "y", p4)
    svc4.clear()
    _, cached4 = svc4.search("sonovel", "y", p4)
    check(cached4 is False, "清空后不命中")
    check(p4.calls == 2, f"上游被调用 2 次（实际 {p4.calls}）")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
