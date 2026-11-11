"""调度器语义测试：全局单线程 + 来源切换 + 任务归属。

用假插件验证（不依赖上游真实进程）：
1. 同一时刻只有一个任务运行，其余排队并带排队位置；
2. after_current 切换：等待当前任务收尾，期间旧来源不能再提交，旧来源排队任务被取消；
3. cancel_now 切换：正在下载的任务被取消并立即切换；
4. 空闲时切换：立即生效；
5. 任务归属：别人能看到队列与进度，但不能取消/下载自己的任务。

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
from app.scheduler import EnqueueError, Scheduler  # noqa: E402

FAILED: list[str] = []

USER_A = {"id": "user-a", "role": "user", "username": "甲"}
USER_B = {"id": "user-b", "role": "user", "username": "乙"}
ADMIN = {"id": "user-root", "role": "admin", "username": "root"}


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
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


def task_in(snap: dict, task_id: str) -> dict | None:
    for item in snap["tasks"]:
        if item["id"] == task_id:
            return item
    return None


def main() -> int:
    store.init_db()
    plugin_a = FakePlugin("alpha", "来源A", seconds=1.5)
    plugin_b = FakePlugin("beta", "来源B", seconds=1.0)
    scheduler = Scheduler({"alpha": plugin_a, "beta": plugin_b}, "alpha")
    scheduler.start()

    print("[1] 全局单线程与排队位置")
    t1 = scheduler.enqueue(
        source="alpha", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书1", book_ref="r1", fmt="txt",
    )
    t2 = scheduler.enqueue(
        source="alpha", user_id=USER_B["id"], user_name=USER_B["username"],
        title="书2", book_ref="r2", fmt="txt",
    )
    check(t1["queue_position"] == 1, "第一个任务排队位置=1")
    check(t2["queue_position"] == 2, "第二个任务排队位置=2")
    check(wait_until(lambda: store.running_task() is not None, 10), "第一个任务开始运行")
    snap = scheduler.snapshot(USER_A)
    check(snap["counts"].get("running") == 1, "只有 1 个 running")
    check(snap["counts"].get("queued") == 1, "另一任务仍在排队")
    running_id = store.running_task()["id"]

    print("[2] 任务归属：别人的任务只能看，不能操作")
    snap_a = scheduler.snapshot(USER_A)
    mine = task_in(snap_a, t1["task"]["id"])
    other = task_in(snap_a, t2["task"]["id"])
    check(mine["mine"] is True and mine["can_cancel"] is True, "自己的任务可取消")
    check(other["mine"] is False and other["can_cancel"] is False, "别人的排队任务不可取消")
    check(other["has_file"] is False, "别人的任务不暴露文件")
    check(other.get("queue_position") == 1, "仍能看到别人的排队位置")
    snap_admin = scheduler.snapshot(ADMIN)
    admin_view = task_in(snap_admin, t2["task"]["id"])
    check(admin_view["can_cancel"] is True, "管理员可取消任何任务")
    snap_b = scheduler.snapshot(USER_B)
    check(task_in(snap_b, t2["task"]["id"])["mine"] is True, "乙看到的是自己的任务")

    print("[3] after_current 切换（等当前下载结束）")
    result = scheduler.request_switch("beta", "after_current")
    check(result["applied"] is False, "切换未立即生效")
    check(result["pending_switch"]["source"] == "beta", "记录了待切换来源")
    check(len(result["canceled"]) == 1, "旧来源排队任务被取消")
    try:
        scheduler.enqueue(
            source="alpha", user_id=USER_B["id"], user_name=USER_B["username"],
            title="书3", book_ref="r3", fmt="txt",
        )
        check(False, "切换期间不应允许向旧来源提交")
    except EnqueueError as exc:
        check("切换" in str(exc), "旧来源提交被拒绝")
    check(
        wait_until(lambda: store.get_task(running_id)["status"] == "ready", 20),
        "当前任务正常完成并进入待接收（未被中断）",
    )
    # 待接收的临时文件应存在，交付后删除
    task_row = store.get_task(running_id)
    check(bool(task_row["size_bytes"]), "记录了文件大小（数据库不存文件内容）")
    delivered_path = scheduler.deliverable_path(running_id)
    check(delivered_path is not None and delivered_path.is_file(), "临时文件存在，等待接收")
    scheduler.complete_delivery(running_id)
    check(store.get_task(running_id)["status"] == "delivered", "接收后状态变为已交付")
    check(scheduler.deliverable_path(running_id) is None, "交付后临时文件已删除")
    check(wait_until(lambda: store.active_source("alpha") == "beta", 15), "收尾后自动切换到来源B")
    check(store.pending_switch() is None, "待切换标记已清除")

    print("[4] 切换后只能使用新来源")
    t3 = scheduler.enqueue(
        source="beta", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书4", book_ref="b1", fmt="txt",
    )
    check(t3["queue_position"] == 1, "新来源任务可提交")
    try:
        scheduler.enqueue(
            source="alpha", user_id=USER_B["id"], user_name=USER_B["username"],
            title="书5", book_ref="r5", fmt="txt",
        )
        check(False, "此时不应允许来源A")
    except EnqueueError:
        check(True, "来源A 提交被拒绝")
    check(wait_until(lambda: store.running_task() is not None, 10), "来源B 开始下载")

    print("[5] cancel_now 切换（立即取消并切换）")
    result = scheduler.request_switch("alpha", "cancel_now")
    check(result["applied"] is True, "立即切换生效")
    check(store.active_source("beta") == "alpha", "当前来源变为 A")
    check(
        wait_until(
            lambda: all(
                t["status"] != "running" for t in store.list_tasks() if t["source"] == "beta"
            ),
            25,
        ),
        "原下载中的任务已停止",
    )
    statuses = [t["status"] for t in store.list_tasks() if t["source"] == "beta"]
    check("canceled" in statuses, "原任务被标记为已取消")

    print("[6] 空闲时切换")
    check(store.running_task() is None, "当前空闲")
    result = scheduler.request_switch("beta", "cancel_now")
    check(result["applied"] is True and result["active_source"] == "beta", "空闲切换立即生效")

    print("[7] 全局终态统计")
    counts = store.task_counts()
    check(counts.get("running", 0) == 0, "没有遗留 running")
    print(f"  统计: {counts}")

    scheduler.shutdown()
    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
