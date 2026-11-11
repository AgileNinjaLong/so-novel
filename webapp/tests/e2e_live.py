"""对**运行中的**服务做一次真实的多用户排队 / 来源切换 / 权限验证。

前置：服务已运行（默认 http://127.0.0.1:8099），两个上游都已安装，
且启动时设置了 ADMIN_USERNAME / ADMIN_PASSWORD（默认 root / admin-pass-123）。

运行：python tests/e2e_live.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin-pass-123")
FAILED: list[str] = []

# so-novel 的测试书目（笔趣阁365，《活着》11 章）
BOOK_SMALL = "https://www.biquge365.net/book/17221/"
BOOK_LONG = "https://www.biquge365.net/book/78201/"


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def make_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=30.0, follow_redirects=False)


def api(client: httpx.Client, method: str, path: str, **kwargs):
    resp = client.request(method, path, **kwargs)
    if resp.status_code >= 400:
        detail = resp.text[:200]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(f"{method} {path} -> {resp.status_code}: {detail}")
    return resp.json() if resp.content else None


def state(client: httpx.Client) -> dict:
    return api(client, "GET", "/api/state")


def task_by_id(snap: dict, task_id: str) -> dict | None:
    for task in snap["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def wait_until(fn, timeout: float = 40.0, interval: float = 0.6) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def signup(client: httpx.Client, admin: httpx.Client, name: str, days: int) -> dict:
    """用管理员密钥注册一个用户，并由管理员开通时长。"""
    overview = api(admin, "GET", "/api/admin/overview")
    key = overview["registration_key"]
    if not key:
        key = api(admin, "POST", "/api/admin/key")["registration_key"]
    user = api(
        client,
        "POST",
        "/api/auth/register",
        json={"username": name, "password": "password123", "invite_key": key},
    )["user"]
    api(admin, "POST", f"/api/admin/users/{user['id']}/grant", json={"days": days})
    return user


def main() -> int:
    print(f"目标服务：{BASE}")

    print("[0] 匿名访问被完全拦截")
    anon = make_client()
    check(anon.get("/").status_code in (303, 401), "匿名访问首页被跳转")
    check(anon.get("/api/state").status_code == 401, "匿名访问队列接口 401")

    print("[1] 管理员登录与插件就绪")
    admin = make_client()
    api(admin, "POST", "/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    meta = api(admin, "GET", "/api/meta")
    check(meta["user"]["role"] == "admin", "管理员身份正确")
    for plugin in meta["plugins"]:
        check(plugin["ready"], f"{plugin['name']} 就绪（{plugin['status_detail']}）")

    print("[2] 注册两个用户并开通时长")
    tag = uuid.uuid4().hex[:6]
    alice = make_client()
    bob = make_client()
    user_a = signup(alice, admin, f"alice{tag}", 372)
    user_b = signup(bob, admin, f"bob{tag}", 31)
    check(user_a["username"] == f"alice{tag}", "用户A 注册成功")
    check(user_b["username"] == f"bob{tag}", "用户B 注册成功")
    me_a = api(alice, "GET", "/api/auth/me")["user"]
    check(me_a["active"] is True and me_a["remaining_days"] > 0, "用户A 已开通")

    print("[3] 提交两个任务，验证单线程与排队位置")
    if state(alice)["active_source"] != "sonovel":
        api(alice, "POST", "/api/source", json={"source": "sonovel", "mode": "cancel_now"})
    t1 = api(alice, "POST", "/api/tasks", json={
        "source": "sonovel", "title": "临渊行", "book_ref": BOOK_LONG, "fmt": "txt"})["task"]["id"]
    t2 = api(bob, "POST", "/api/tasks", json={
        "source": "sonovel", "title": "活着", "book_ref": BOOK_SMALL, "fmt": "txt"})["task"]["id"]
    check(wait_until(lambda: state(alice)["running"] is not None, 40), "第一个任务开始运行")
    snap = state(alice)
    second = task_by_id(snap, t2)
    check(second["status"] == "queued", "第二个任务排队中")
    check(second.get("queue_position") == 1, "第二个任务排队位置=1")
    check(second["user"] == f"bob{tag}", "排队任务显示提交者")
    check(second["mine"] is False, "A 看到 B 的任务不是自己的")

    print("[4] 越权操作被拒绝")
    try:
        api(alice, "DELETE", f"/api/tasks/{t2}")
        check(False, "A 不应能取消 B 的任务")
    except RuntimeError as exc:
        check("只能取消自己的任务" in str(exc), "A 取消 B 的任务被拒绝")
    try:
        api(bob, "GET", f"/api/tasks/{t1}/download")
        check(False, "B 不应能下载 A 的文件")
    except RuntimeError as exc:
        check("只能下载自己的文件" in str(exc) or "尚未就绪" in str(exc), "B 下载 A 的文件被拒绝")
    check(bob.get("/api/admin/overview").status_code == 403, "普通用户访问后台 403")

    print("[5] 下载中切换来源：after_current 挂起并取消旧来源排队任务")
    result = api(bob, "POST", "/api/source", json={"source": "tomato", "mode": "after_current"})
    check(result["applied"] is False, "切换未立即生效")
    check(result["pending_switch"]["source"] == "tomato", "记录了待切换目标")
    check(len(result["canceled"]) == 1, "旧来源排队任务被取消")
    snap = state(alice)
    check(task_by_id(snap, t2)["status"] == "canceled", "B 的排队任务被取消")
    try:
        api(bob, "POST", "/api/tasks", json={
            "source": "sonovel", "title": "拒绝测试", "book_ref": BOOK_SMALL, "fmt": "txt"})
        check(False, "切换期间不应允许提交旧来源")
    except RuntimeError as exc:
        check("切换" in str(exc), "切换期间提交旧来源被拒绝")

    print("[6] 管理员可取消任何任务，取消后自动切换")
    api(admin, "POST", f"/api/admin/tasks/{t1}/cancel")
    check(
        wait_until(lambda: task_by_id(state(alice), t1)["status"] == "canceled", 60),
        "管理员取消 A 的运行中任务",
    )
    check(wait_until(lambda: state(alice)["active_source"] == "tomato", 60), "取消收尾后自动切换")

    print("[7] 后台能查看用户与任务")
    overview = api(admin, "GET", "/api/admin/overview")
    names = {u["username"] for u in overview["users"]}
    check(f"alice{tag}" in names and f"bob{tag}" in names, "后台列出两个新用户")
    perms = [u for u in overview["users"] if u["username"] == f"alice{tag}"][0]
    check(perms["active"] is True, "后台显示 A 的有效期状态")
    check(len(overview["tasks"]) >= 2, "后台能看到任务列表")

    print("[8] 禁用用户 B 后会话立即失效")
    api(admin, "POST", f"/api/admin/users/{user_b['id']}/status", json={"status": "banned"})
    check(bob.get("/api/state").status_code == 401, "B 的会话已失效")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
