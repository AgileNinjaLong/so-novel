"""对**运行中的**服务做一次真实的多用户排队 / 来源切换 / 取消验证。

前置：服务已在 WEBAPP_URL（默认 http://127.0.0.1:8099）运行，且两个上游都已安装。

运行：python tests/e2e_live.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def api(client: httpx.Client, method: str, path: str, **kwargs):
    resp = client.request(method, BASE + path, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else None


def state(client: httpx.Client) -> dict:
    return api(client, "GET", "/api/state")


def task_by_id(snap: dict, task_id: str) -> dict | None:
    for task in snap["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def wait_until(fn, timeout: float = 30.0, interval: float = 0.6) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def main() -> int:
    client = httpx.Client(timeout=30.0)
    print(f"目标服务：{BASE}")

    meta = api(client, "GET", "/api/meta")
    print("[0] 来源就绪状态")
    for plugin in meta["plugins"]:
        check(plugin["ready"], f"{plugin['name']} 就绪（{plugin['status_detail']}）")

    active = meta["app"]["active_source"]
    if active != "sonovel":
        result = api(client, "POST", "/api/source", json={"source": "sonovel", "mode": "cancel_now"})
        check(result["applied"], "切回 so-novel")

    print("[1] 昵称写进 Cookie（中文不应报错）")
    me = api(client, "POST", "/api/me", json={"name": "排队测试"})
    check(me["name"] == "排队测试", "中文昵称可保存")

    print("[2] 提交两个任务，验证全局单线程与排队位置")
    tasks = [
        {"source": "sonovel", "title": "临渊行", "book_ref": "https://www.biquge365.net/book/78201/", "fmt": "txt"},
        {"source": "sonovel", "title": "大梦主", "book_ref": "https://www.biquge365.net/book/39884/", "fmt": "txt"},
    ]
    created = []
    for payload in tasks:
        created.append(api(client, "POST", "/api/tasks", json=payload)["task"]["id"])
    check(len(created) == 2, "两个任务都已入队")
    check(
        wait_until(lambda: state(client)["running"] is not None, 30),
        "第一个任务开始运行",
    )
    snap = state(client)
    second = task_by_id(snap, created[1])
    check(second["status"] == "queued", "第二个任务排队中")
    check(second.get("queue_position") == 1, "第二个任务排队位置=1")
    check(snap["counts"].get("running") == 1, "同时只有一个任务在跑")
    check(second["user"] == "排队测试", "任务记录提交者昵称")

    print("[3] 下载中切换来源：after_current 应挂起并取消旧来源排队任务")
    result = api(client, "POST", "/api/source", json={"source": "tomato", "mode": "after_current"})
    check(result["applied"] is False, "切换未立即生效")
    check(result["pending_switch"]["source"] == "tomato", "记录了待切换目标")
    check(len(result["canceled"]) == 1, "旧来源排队任务被取消")
    snap = state(client)
    check(task_by_id(snap, created[1])["status"] == "canceled", "排队任务状态=已取消")
    check(snap["pending_switch"] is not None, "快照里有待切换标记")
    try:
        api(client, "POST", "/api/tasks", json={
            "source": "sonovel", "title": "测试拒绝", "book_ref": "https://www.biquge365.net/book/95601/", "fmt": "txt",
        })
        check(False, "切换期间不应允许向旧来源提交")
    except RuntimeError as exc:
        check("切换" in str(exc), "旧来源提交被拒绝")

    print("[4] 取消正在下载的任务 → 收尾后应自动完成切换")
    api(client, "DELETE", f"/api/tasks/{created[0]}")
    check(
        wait_until(lambda: task_by_id(state(client), created[0])["status"] == "canceled", 40),
        "运行中的任务被取消",
    )
    check(
        wait_until(lambda: state(client)["active_source"] == "tomato", 40),
        "取消收尾后自动切换到番茄",
    )
    check(state(client)["pending_switch"] is None, "待切换标记已清除")

    print("[5] 切换后旧来源任务已全部终止")
    snap = state(client)
    check(snap["counts"].get("running", 0) == 0, "没有遗留 running 任务")
    old = [t for t in snap["tasks"] if t["source"] == "sonovel" and t["status"] in {"running", "queued"}]
    check(not old, "没有遗留的 so-novel 活动任务")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
