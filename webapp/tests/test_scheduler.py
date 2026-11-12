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


class EvilTitlePlugin(FakePlugin):
    """模拟上游把书名报错（例如读了上一个任务的日志），用于验证标题不被覆盖。"""

    def __init__(self, pid: str, name: str, wrong_title: str = "活着", seconds: float = 1.0):
        super().__init__(pid, name, seconds)
        self.wrong_title = wrong_title

    def download(self, *, task, progress, cancel_event, library_dir):
        result = super().download(
            task=task, progress=progress, cancel_event=cancel_event, library_dir=library_dir
        )
        result.title = self.wrong_title
        return result


class StallPlugin(FakePlugin):
    """模拟上游卡住：完全不发进度，直到被取消。"""

    def __init__(self, pid: str, name: str, stay: float = 30.0):
        super().__init__(pid, name, seconds=stay)
        self.stay = stay

    def download(self, *, task, progress, cancel_event, library_dir):
        deadline = time.time() + self.stay
        while time.time() < deadline:
            if cancel_event.is_set():
                raise CanceledError()
            time.sleep(0.2)
        if cancel_event.is_set():
            raise CanceledError()
        raise RuntimeError("stalled")


class SlowProgressPlugin(FakePlugin):
    """很慢但持续有进度：用于验证进度更新会重置超时计时。"""

    def __init__(self, pid: str, name: str, steps: int = 12, interval: float = 0.4):
        super().__init__(pid, name, seconds=steps * interval)
        self.steps = steps
        self.interval = interval

    def download(self, *, task, progress, cancel_event, library_dir):
        for i in range(self.steps):
            if cancel_event.is_set():
                raise CanceledError()
            time.sleep(self.interval)  # 总时长远大于 stall 限制
            progress(done=i + 1, total=self.steps,
                     percent=(i + 1) / self.steps * 100,
                     message=f"已下载 {i + 1}/{self.steps} 章")
        path = Path(library_dir) / task["id"] / "files" / "book.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * 1000, encoding="utf-8")
        return DownloadResult(file_path=str(path), title=task["title"])


class FileGrowthPlugin(FakePlugin):
    """只往临时目录写文件、不上报进度：文件在变大也应算「有进度」。"""

    def __init__(self, pid: str, name: str, chunks: int = 8, interval: float = 0.5):
        super().__init__(pid, name, seconds=chunks * interval)
        self.chunks = chunks
        self.interval = interval

    def download(self, *, task, progress, cancel_event, library_dir):
        out = Path(library_dir) / task["id"] / "download" / "book.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fp:
            for i in range(self.chunks):
                if cancel_event.is_set():
                    raise CanceledError()
                time.sleep(self.interval)  # 总时长 > stall 限制
                fp.write("x" * 500)
                fp.flush()
        return DownloadResult(file_path=str(out), title=task["title"])


class IdleProgressPlugin(FakePlugin):
    """不停调用 progress 但数值一直不变：没有真实进度，仍应判超时。"""

    def __init__(self, pid: str, name: str, stay: float = 30.0):
        super().__init__(pid, name, seconds=stay)
        self.stay = stay

    def download(self, *, task, progress, cancel_event, library_dir):
        deadline = time.time() + self.stay
        while time.time() < deadline:
            if cancel_event.is_set():
                raise CanceledError()
            progress(done=0, total=10, percent=0.0, message="已下载 0/10 章")
            time.sleep(0.3)
        if cancel_event.is_set():
            raise CanceledError()
        raise RuntimeError("stalled")


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
    scheduler = Scheduler({"alpha": plugin_a, "beta": plugin_b}, "alpha", workers=1)
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
    check(snap["counts"].get("running") == 1, "甲自己的统计里有 1 个 running")
    check(snap["counts"].get("queued", 0) == 0, "甲的统计里没有别人的排队任务")
    check(snap["queue_length"] == 1, f"全局队列长度仍可见（数字）：{snap['queue_length']}")
    running_id = store.running_task()["id"]

    print("[2] 任务隔离：普通用户只看自己的，管理员看全部")
    snap_a = scheduler.snapshot(USER_A)
    mine = task_in(snap_a, t1["task"]["id"])
    other = task_in(snap_a, t2["task"]["id"])
    check(mine["mine"] is True and mine["can_cancel"] is True, "自己的任务可取消")
    check(other is None, "看不到别人的任务（列表里不存在）")
    check(len(snap_a["tasks"]) == 1, f"甲只看到 1 条（实际 {len(snap_a['tasks'])}）")
    check(snap_a["running"] is not None and snap_a["running"]["id"] == t1["task"]["id"],
          "甲能看到自己正在下载的书名")
    check(snap_a["running_by_other"] is False, "甲的任务在运行时不算「别人在下载」")

    snap_admin = scheduler.snapshot(ADMIN)
    check(len(snap_admin["tasks"]) == 2, f"管理员能看到全部 2 条（实际 {len(snap_admin['tasks'])}）")
    check(task_in(snap_admin, t2["task"]["id"])["can_cancel"] is True, "管理员可取消任何任务")
    check(snap_admin["counts"].get("running", 0) + snap_admin["counts"].get("queued", 0) >= 1,
          "管理员统计是全局的")

    snap_b = scheduler.snapshot(USER_B)
    check(len(snap_b["tasks"]) == 1, f"乙只看到自己的 1 条（实际 {len(snap_b['tasks'])}）")
    check(task_in(snap_b, t2["task"]["id"])["mine"] is True, "乙看到的是自己的任务")
    check(snap_b["running"] is None, "别人在下载时不暴露对方书名")
    check(snap_b["running_by_other"] is True, "提示「当前有他人在下载」")
    queued_b = task_in(snap_b, t2["task"]["id"])
    check(queued_b.get("queue_ahead") == 0, f"排队提示：前面还有 {queued_b.get('queue_ahead')} 个")

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

    print("[8] 暂停：丢弃进度、不可续传，只能重新下载（重新排队）")
    t4 = scheduler.enqueue(
        source="beta", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书6", book_ref="b6", fmt="txt",
    )
    paused_id = t4["task"]["id"]
    check(wait_until(lambda: store.get_task(paused_id)["status"] == "running", 10), "任务开始运行")
    result = scheduler.pause(paused_id)
    check(result["paused"] is True and result["was_running"] is True, "暂停接口返回运行中")
    check(wait_until(lambda: store.get_task(paused_id)["status"] == "paused", 20), "任务变为已暂停")
    row = task_in(scheduler.snapshot(USER_A), paused_id)
    check(row["can_pause"] is False and row["can_cancel"] is False, "暂停后不能再次暂停/取消")
    check(row["can_retry"] is True, "暂停后只能重新下载")
    check(scheduler.deliverable_path(paused_id) is None, "暂停后临时文件已丢弃")

    retried = scheduler.enqueue(
        source="beta", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书6", book_ref="b6", fmt="txt",
    )
    check(retried["task"]["id"] != paused_id, "重新下载是一个新任务")
    check(retried["queue_position"] >= 1, "重新下载需要重新排队")
    check(store.get_task(paused_id)["status"] == "paused", "原任务保持已暂停，不会自动续传")
    scheduler.cancel(retried["task"]["id"])
    check(
        wait_until(lambda: store.get_task(retried["task"]["id"])["status"] == "canceled", 25),
        "清理重试任务",
    )

    print("[9] 终态统计（含暂停）")
    counts = store.task_counts()
    check(counts.get("paused", 0) >= 1, "存在已暂停任务")
    check(wait_until(lambda: store.task_counts().get("running", 0) == 0, 25), "没有遗留 running")
    print(f"  统计: {store.task_counts()}")

    print("[10] 待接收超时（TTL）自动删除并标记过期")
    t5 = scheduler.enqueue(
        source="beta", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书7", book_ref="b7", fmt="txt",
    )
    ttl_id = t5["task"]["id"]
    check(wait_until(lambda: store.get_task(ttl_id)["status"] == "ready", 25), "任务进入待接收")
    path = scheduler.deliverable_path(ttl_id)
    check(path is not None, "临时文件存在")
    if path is not None:
        from app.config import settings

        task_dir = settings.temp_root / ttl_id
        old = time.time() - 3 * 3600
        os.utime(task_dir, (old, old))
    scheduler._sweep_once()
    check(store.get_task(ttl_id)["status"] == "expired", "超时后标记为已过期")
    check(scheduler.deliverable_path(ttl_id) is None, "超时后临时文件已删除")

    print("[11] 上游报的书名不能覆盖用户填写的书名")
    evil = EvilTitlePlugin("evil", "来源C")
    scheduler._plugins["evil"] = evil
    scheduler.request_switch("evil", "cancel_now")
    t6 = scheduler.enqueue(
        source="evil", user_id=USER_A["id"], user_name=USER_A["username"],
        title="战神", book_ref="https://example.com/zhanshen", fmt="txt",
    )
    tid6 = t6["task"]["id"]
    check(wait_until(lambda: store.get_task(tid6)["status"] in {"ready", "failed"}, 30), "任务结束")
    row6 = store.get_task(tid6)
    check(row6["title"] == "战神", f"书名仍是用户填写的「战神」（实际：{row6['title']}）")
    check("活着" not in (row6["title"] or ""), "没有被上游的「活着」串台")

    print("[12] 单条删除 / 批量删除 / 越权")
    t7 = scheduler.enqueue(
        source="evil", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书A", book_ref="a", fmt="txt",
    )
    tid7 = t7["task"]["id"]
    check(wait_until(lambda: store.get_task(tid7)["status"] == "ready", 30), "任务A待接收")
    result = scheduler.remove_task(tid7)
    check(result["removed"] is True, "单条删除成功")
    check(store.get_task(tid7) is None, "记录已不存在")
    check(scheduler.deliverable_path(tid7) is None, "临时文件已删除")

    ids = []
    for i in range(2):
        row = scheduler.enqueue(
            source="evil", user_id=USER_B["id"], user_name=USER_B["username"],
            title=f"书B{i}", book_ref=f"b{i}", fmt="txt",
        )
        ids.append(row["task"]["id"])
    check(wait_until(lambda: all(store.get_task(i)["status"] == "ready" for i in ids), 40), "两个任务待接收")
    denied = scheduler.remove_tasks(ids, user_id=USER_A["id"])
    check(denied["removed"] == 0 and len(denied["skipped"]) == 2, "别人的任务不能删")
    bulk = scheduler.remove_tasks(ids, user_id=USER_B["id"])
    check(bulk["removed"] == 2, "批量删除自己的两条记录")
    check(all(store.get_task(i) is None for i in ids), "批量删除后记录都不存在")

    print("[13] 运行中的任务：删除需先取消")
    # 先用一个占位任务占住全局工作线程，保证第二个任务确实处于「排队中」
    blocker = scheduler.enqueue(
        source="evil", user_id=USER_B["id"], user_name=USER_B["username"],
        title="占位", book_ref="blk", fmt="txt",
    )
    tq = scheduler.enqueue(
        source="evil", user_id=USER_B["id"], user_name=USER_B["username"],
        title="排队待删", book_ref="q", fmt="txt",
    )
    tidq = tq["task"]["id"]
    check(wait_until(lambda: store.get_task(tidq)["status"] == "queued", 10), "第二个任务处于排队中")
    check(wait_until(lambda: store.get_task(blocker["task"]["id"])["status"] == "running", 15), "占位任务在运行")
    resq = scheduler.remove_task(tidq)
    check(resq["removed"] is True, "排队中的任务直接删除记录")
    check(store.get_task(tidq) is None, "排队记录已不存在")
    blocker_id = blocker["task"]["id"]
    check(wait_until(lambda: store.get_task(blocker_id)["status"] != "running", 25), "占位任务已停止")
    scheduler.remove_task(blocker_id)
    check(store.get_task(blocker_id) is None, "清理占位任务")

    t8 = scheduler.enqueue(
        source="evil", user_id=USER_A["id"], user_name=USER_A["username"],
        title="书C", book_ref="c", fmt="txt",
    )
    tid8 = t8["task"]["id"]
    check(wait_until(lambda: store.get_task(tid8)["status"] == "running", 15), "任务C开始运行")
    first = scheduler.remove_task(tid8)
    check(first.get("pending") is True, "运行中提示「正在取消」")
    check(
        wait_until(lambda: store.get_task(tid8)["status"] != "running", 25),
        "取消生效",
    )
    second = scheduler.remove_task(tid8)
    check(second["removed"] is True, "取消后再删除即可移除记录")
    check(store.get_task(tid8) is None, "记录已移除")

    print("[14] 多人下载同一本书：记录与临时目录互相独立")
    ta = scheduler.enqueue(
        source="evil", user_id=USER_A["id"], user_name=USER_A["username"],
        title="同一本书", book_ref="same", fmt="txt",
    )
    tb = scheduler.enqueue(
        source="evil", user_id=USER_B["id"], user_name=USER_B["username"],
        title="同一本书", book_ref="same", fmt="txt",
    )
    check(ta["task"]["id"] != tb["task"]["id"], "两个用户各自生成独立任务")
    check(wait_until(lambda: store.get_task(ta["task"]["id"])["status"] in {"ready", "failed"}, 40)
          and wait_until(lambda: store.get_task(tb["task"]["id"])["status"] in {"ready", "failed"}, 40),
          "两个任务都完成")
    from app.config import settings as app_settings
    dir_a = app_settings.temp_root / ta["task"]["id"]
    dir_b = app_settings.temp_root / tb["task"]["id"]
    check(dir_a.is_dir() and dir_b.is_dir(), "各自的临时目录独立存在")
    check(str(dir_a) != str(dir_b), "临时目录不是同一个（不会互相覆盖）")

    print("[15] 进度超时：连续 N 秒没更新就判定失败（测试里设成 3 秒）")
    from app.config import settings as app_settings

    old_stall = app_settings.stall_timeout_sec
    app_settings.stall_timeout_sec = 3

    stalled = StallPlugin("stall", "卡住源", stay=30)
    slow = SlowProgressPlugin("slow", "慢速源", steps=12, interval=0.4)  # 约 4.8s > 3s
    scheduler._plugins["stall"] = stalled
    scheduler._plugins["slow"] = slow

    scheduler.request_switch("stall", "cancel_now")
    t_stall = scheduler.enqueue(
        source="stall", user_id=USER_A["id"], user_name=USER_A["username"],
        title="卡住的书", book_ref="s", fmt="txt",
    )
    tid_stall = t_stall["task"]["id"]
    check(wait_until(lambda: store.get_task(tid_stall)["status"] == "running", 15), "卡住任务开跑")
    check(
        wait_until(lambda: store.get_task(tid_stall)["status"] in {"failed", "canceled"}, 20),
        "无进度后被判定结束",
    )
    row = store.get_task(tid_stall)
    check(row["status"] == "failed", f"状态是失败而不是暂停/取消（实际 {row['status']}）")
    check("超时" in (row["error"] or ""), f"错误里标明超时：{row['error']}")
    check(scheduler.deliverable_path(tid_stall) is None, "超时后临时文件已清理")

    scheduler.request_switch("slow", "cancel_now")
    t_slow = scheduler.enqueue(
        source="slow", user_id=USER_A["id"], user_name=USER_A["username"],
        title="慢速的书", book_ref="w", fmt="txt",
    )
    tid_slow = t_slow["task"]["id"]
    check(
        wait_until(lambda: store.get_task(tid_slow)["status"] in {"ready", "failed"}, 30),
        "慢速任务结束",
    )
    row_slow = store.get_task(tid_slow)
    check(row_slow["status"] == "ready", f"持续有进度的任务正常完成（实际 {row_slow['status']}）")

    app_settings.stall_timeout_sec = old_stall
    scheduler.remove_task(tid_slow)

    print("[16] 只有真实进度才算：文件增长算进度，空转回调不算")
    app_settings.stall_timeout_sec = 3

    grow = FileGrowthPlugin("grow", "写文件源", chunks=10, interval=0.5)  # 5s > 3s，但每 0.5s 有写入
    idle = IdleProgressPlugin("idle", "空转源", stay=30)
    scheduler._plugins["grow"] = grow
    scheduler._plugins["idle"] = idle

    scheduler.request_switch("grow", "cancel_now")
    t_grow = scheduler.enqueue(
        source="grow", user_id=USER_A["id"], user_name=USER_A["username"],
        title="边写边下的书", book_ref="g", fmt="txt",
    )
    tid_grow = t_grow["task"]["id"]
    check(
        wait_until(lambda: store.get_task(tid_grow)["status"] in {"ready", "failed"}, 40),
        "写文件任务结束",
    )
    row_grow = store.get_task(tid_grow)
    check(row_grow["status"] == "ready",
          f"文件持续变大 → 不超时，正常完成（实际 {row_grow['status']}）")

    scheduler.request_switch("idle", "cancel_now")
    t_idle = scheduler.enqueue(
        source="idle", user_id=USER_A["id"], user_name=USER_A["username"],
        title="空转的书", book_ref="i", fmt="txt",
    )
    tid_idle = t_idle["task"]["id"]
    check(
        wait_until(lambda: store.get_task(tid_idle)["status"] in {"failed", "canceled"}, 25),
        "空转任务被判结束",
    )
    row_idle = store.get_task(tid_idle)
    check(row_idle["status"] == "failed",
          f"反复报同样的进度也判超时（实际 {row_idle['status']}）")
    check("超时" in (row_idle["error"] or ""), f"错误标明超时：{row_idle['error']}")

    app_settings.stall_timeout_sec = old_stall

    print("[17] 并发下载：换一个 2 线程的调度器，同时跑 2 个任务")
    scheduler.shutdown()

    multi_a = FakePlugin("multi", "并发源", seconds=2.0)
    multi_b = FakePlugin("multi2", "并发源2", seconds=2.0)
    scheduler2 = Scheduler({"multi": multi_a, "multi2": multi_b}, "multi", workers=2)
    scheduler2.SOURCE_PARALLEL_LIMIT["multi"] = 2
    scheduler2.start()

    ids = []
    for i in range(3):
        row = scheduler2.enqueue(
            source="multi", user_id=USER_A["id"], user_name=USER_A["username"],
            title=f"并发{i}", book_ref=f"m{i}", fmt="txt",
        )
        ids.append(row["task"]["id"])

    def running_count() -> int:
        return len(store.running_tasks())

    check(wait_until(lambda: running_count() >= 2, 20), f"同时有 2 个任务在跑（实际 {running_count()}）")
    check(len(store.queued_tasks()) >= 1, f"第三个任务在排队（{len(store.queued_tasks())}）")
    snap_multi = scheduler2.snapshot(USER_A)
    check(snap_multi.get("task_concurrency") == 2, f"快照暴露并发度 {snap_multi.get('task_concurrency')}")
    check(
        wait_until(lambda: all(store.get_task(i)["status"] == "ready" for i in ids), 60),
        "三个任务全部完成",
    )

    print("[18] 受限来源（番茄类）并发上限 1")
    scheduler2.SOURCE_PARALLEL_LIMIT["multi"] = 1
    pair = []
    for i in range(2):
        row = scheduler2.enqueue(
            source="multi", user_id=USER_A["id"], user_name=USER_A["username"],
            title=f"串行{i}", book_ref=f"s{i}", fmt="txt",
        )
        pair.append(row["task"]["id"])
    check(wait_until(lambda: running_count() <= 1, 30), f"受限来源同时只跑 1 个（实际 {running_count()}）")
    check(
        wait_until(lambda: all(store.get_task(i)["status"] == "ready" for i in pair), 60),
        "受限来源的任务依次完成",
    )

    scheduler2.shutdown()
    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
