"""调度器语义测试：全局单线程 + 来源切换。

用假插件验证（不依赖上游真实进程）：
1. 同一时刻只有一个任务运行，其余排队并带排队位置；
2. after_current 切换：等待当前任务收尾，期间旧来源不能再提交，旧来源排队任务被取消；
3. cancel_now 切换：正在下载的任务被取消并立即切换；
4. 空闲时切换：立即生效。

运行：python tests/test_scheduler.py
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

TMP = tempfile.mkdtemp(prefix="novel-test-")
os.environ["WEBAPP_DATA_DIR"] = TMP
os.environ["WEBAPP_POLL_MS"] = "200"

from app import store  # noqa: E402
from app.plugins.base import (  # noqa: E402
    CanceledError,
    Capabilities,
    DownloadResult,
    PluginStatus,
)
from app.scheduler import EnqueueError, Scheduler, SwitchError  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    if cond:
        print(f"  OK  {label}")
    else:
        print(f"  FAIL {label}")
        FAILED.append(label)


class FakePlugin:
    def __init__(self, pid: str, name: str, seconds: float = 1.2):
        self.id = pid
        self.name = name
        self.description = "fake"
        self.upstream = "local"
        self.seconds = seconds
        self.capabilities = Capabilities(True, "fake", ["txt"], "")
        self.canceled: list[str] = []

    def status(self) -> PluginStatus:
        return PluginStatus(True, "fake ready")

    def search(self, query: str):
        return []

    def download(self, *, task, progress, cancel_event, library_dir):
        total = 10
        for i in range(total):
            if cancel_event.is_set():
                raise CanceledError()
            time.sleep(self.seconds / total)
            progress(done=i + 1, total=total, percent=(i + 1) / total * 100)
        if cancel_event.is_set():
            raise CanceledError()
        path = Path(library_dir) / task["id"] / "files" / "book.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        return DownloadResult(file_path=str(path), title=task["title"])

    def cancel(self, task_id: str) -> None:
        self.canceled.append(task_id)

    def shutdown(self) -> None:
        return None


def wait_until(predicate, timeout: float = 20.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def main() -> int:
    store.init_db()
    plugin_a = FakePlugin("alpha", "来源A", seconds=1.5)
    plugin_b = FakePlugin("beta", "来源B", seconds=1.0)
    scheduler = Scheduler({"alpha": plugin_a, "beta": plugin_b}, "alpha")
    scheduler.start()

    print("[1] 全局单线程与排队位置")
    t1 = scheduler.enqueue(
        source="alpha", user_name="用户甲", title="书1", book_ref="r1", fmt="txt"
    )
    t2 = scheduler.enqueue(
        source="alpha", user_name="用户乙", title="书2", book_ref="r2", fmt="txt"
    )
    check(t1["queue_position"] == 1, "第一个任务排队位置=1")
    check(t2["queue_position"] == 2, "第二个任务排队位置=2")
    check(
        wait_until(lambda: store.running_task() is not None, 10),
        "第一个任务开始运行",
    )
    snap = scheduler.snapshot()
    check(snap["counts"].get("running") == 1, "只有 1 个 running")
    check(snap["counts"].get("queued") == 1, "另一任务仍在排队")
    running_id = store.running_task()["id"]

    print("[2] after_current 切换（等当前下载结束）")
    result = scheduler.request_switch("beta", "after_current")
    check(result["applied"] is False, "切换未立即生效")
    check(result["pending_switch"]["source"] == "beta", "记录了待切换来源")
    check(len(result["canceled"]) == 1, "旧来源排队任务被取消")
    try:
        scheduler.enqueue(
            source="alpha", user_name="用户丙", title="书3", book_ref="r3", fmt="txt"
        )
        check(False, "切换期间不应允许向旧来源提交")
    except EnqueueError as exc:
        check("请等待切换完成" in str(exc) or "切换" in str(exc), "旧来源提交被拒绝")
    check(
        wait_until(lambda: store.get_task(running_id)["status"] == "success", 20),
        "当前任务正常完成（未被中断）",
    )
    check(
        wait_until(lambda: store.active_source("alpha") == "beta", 15),
        "收尾后自动切换到来源B",
    )
    check(store.pending_switch() is None, "待切换标记已清除")

    print("[3] 切换后只能使用新来源")
    t3 = scheduler.enqueue(
        source="beta", user_name="用户甲", title="书4", book_ref="b1", fmt="txt"
    )
    check(t3["queue_position"] == 1, "新来源任务可提交")
    try:
        scheduler.enqueue(
            source="alpha", user_name="用户丁", title="书5", book_ref="r5", fmt="txt"
        )
        check(False, "此时不应允许来源A")
    except EnqueueError:
        check(True, "来源A 提交被拒绝")
    check(wait_until(lambda: store.running_task() is not None, 10), "来源B 开始下载")

    print("[4] cancel_now 切换（立即取消并切换）")
    result = scheduler.request_switch("alpha", "cancel_now")
    check(result["applied"] is True, "立即切换生效")
    check(store.active_source("beta") == "alpha", "当前来源变为 A")
    check(
        wait_until(
            lambda: all(
                t["status"] != "running"
                for t in store.list_tasks()
                if t["source"] == "beta"
            ),
            25,
        ),
        "原下载中的任务已停止",
    )
    statuses = [t["status"] for t in store.list_tasks() if t["source"] == "beta"]
    check("canceled" in statuses, "原任务被标记为已取消")

    print("[5] 空闲时切换")
    check(store.running_task() is None, "当前空闲")
    result = scheduler.request_switch("beta", "cancel_now")
    check(result["applied"] is True and result["active_source"] == "beta", "空闲切换立即生效")

    print("[6] 全局终态统计")
    counts = store.task_counts()
    check(counts.get("running", 0) == 0, "没有遗留 running")
    print(f"  统计: {counts}")

    scheduler.shutdown()
    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项: {FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
