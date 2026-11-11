"""对**运行中的**服务做真实的多用户排队 / 密钥注册 / 交付删除 验证。

前置：服务已运行（默认 http://127.0.0.1:8099），两个上游都已安装，
启动时设置了 ADMIN_USERNAME / ADMIN_PASSWORD（默认 root / admin-pass-123）。

运行：python tests/e2e_live.py
"""

from __future__ import annotations

import os
import time
import uuid

import httpx

BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin-pass-123")
FAILED: list[str] = []

BOOK_SMALL = "https://www.biquge365.net/book/17221/"
BOOK_LONG = "https://www.biquge365.net/book/78201/"
TMP_ROOT = os.environ.get(
    "WEBAPP_TMP_ROOT", r"D:\AAA_WT_Work\TEST\小说下载网页端\webapp-data\runtime\tmp"
)


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def make_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=180.0, follow_redirects=False)


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


def wait_until(fn, timeout: float = 90.0, interval: float = 0.8) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def signup_key(client: httpx.Client, admin: httpx.Client, days: int) -> dict:
    """管理员生成一把开放型密钥，新用户用它注册（有效期随密钥）。"""
    key = api(admin, "POST", "/api/admin/keys", json={"days": days, "count": 1, "mode": "open"})["keys"][0]
    name = f"u{uuid.uuid4().hex[:8]}"
    user = api(
        client,
        "POST",
        "/api/auth/register",
        json={"key": key["key"], "username": name, "password": "password123"},
    )["user"]
    return user


def temp_dir(task_id: str) -> str:
    return os.path.join(TMP_ROOT, task_id)


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

    print("[2] 用两把密钥注册两个用户")
    alice = make_client()
    bob = make_client()
    user_a = signup_key(alice, admin, 372)
    user_b = signup_key(bob, admin, 31)
    check(user_a["username"].startswith("u"), "用户A 注册成功")
    check(user_a["remaining_days"] == 372, "用户A 有效期来自密钥（372 天）")
    check(user_b["remaining_days"] == 31, "用户B 有效期来自密钥（31 天）")
    keys = api(admin, "GET", "/api/admin/keys")["keys"]
    used = [k for k in keys if k["status"] == "used"]
    check(len(used) >= 2, "两把密钥都已标记使用")

    print("[3] 单线程队列与排队位置")
    if state(alice)["active_source"] != "sonovel":
        api(alice, "POST", "/api/source", json={"source": "sonovel", "mode": "cancel_now"})
    t1 = api(alice, "POST", "/api/tasks", json={
        "source": "sonovel", "title": "临渊行", "book_ref": BOOK_LONG, "fmt": "txt"})["task"]["id"]
    t2 = api(bob, "POST", "/api/tasks", json={
        "source": "sonovel", "title": "活着", "book_ref": BOOK_SMALL, "fmt": "txt"})["task"]["id"]
    check(wait_until(lambda: state(alice)["running"] is not None, 60), "第一个任务开始运行")
    snap = state(alice)
    second = task_by_id(snap, t2)
    check(second["status"] == "queued", "第二个任务排队中")
    check(second.get("queue_position") == 1, "第二个任务排队位置=1")
    check(second["mine"] is False, "A 看到 B 的任务不是自己的")

    print("[4] 越权操作被拒绝")
    try:
        api(alice, "DELETE", f"/api/tasks/{t2}")
        check(False, "A 不应能取消 B 的任务")
    except RuntimeError as exc:
        check("只能取消自己的任务" in str(exc), "A 取消 B 的任务被拒绝")
    try:
        api(bob, "GET", f"/api/tasks/{t1}/download")
        check(False, "B 不应能接收 A 的文件")
    except RuntimeError as exc:
        check("只能接收自己的文件" in str(exc) or "不在待接收状态" in str(exc), "B 接收 A 的文件被拒绝")
    check(bob.get("/api/admin/overview").status_code == 403, "普通用户访问后台 403")

    print("[5] 管理员取消运行中的任务，源切换按 after_current 挂起")
    result = api(bob, "POST", "/api/source", json={"source": "tomato", "mode": "after_current"})
    check(result["applied"] is False, "切换未立即生效")
    check(result["pending_switch"]["source"] == "tomato", "记录了待切换目标")
    check(len(result["canceled"]) == 1, "旧来源排队任务被取消")
    check(task_by_id(state(bob), t2)["status"] == "canceled", "B 的排队任务已取消")
    api(admin, "POST", f"/api/admin/tasks/{t1}/cancel")
    check(
        wait_until(lambda: task_by_id(state(alice), t1)["status"] == "canceled", 90),
        "管理员取消 A 的运行中任务",
    )
    check(wait_until(lambda: state(alice)["active_source"] == "tomato", 90), "收尾后自动切换到番茄")

    print("[6] 真实下载 → 待接收 → 流式接收 → 服务器立即删除")
    key3 = api(admin, "POST", "/api/admin/keys", json={"days": 124, "count": 1, "mode": "open"})["keys"][0]
    carol = make_client()
    carol_name = f"u{uuid.uuid4().hex[:8]}"
    api(carol, "POST", "/api/auth/register",
        json={"key": key3["key"], "username": carol_name, "password": "password123"})
    api(carol, "POST", "/api/source", json={"source": "sonovel", "mode": "cancel_now"})
    t3 = api(carol, "POST", "/api/tasks", json={
        "source": "sonovel", "title": "活着", "book_ref": BOOK_SMALL, "fmt": "txt"})["task"]["id"]
    check(wait_until(lambda: task_by_id(state(carol), t3)["status"] == "ready", 120), "下载完成进入待接收")
    ready_task = task_by_id(state(carol), t3)
    check(ready_task["size_bytes"] > 0, "记录了文件大小")
    check(ready_task["can_receive"] is True, "出现接收入口")
    check(os.path.isdir(temp_dir(t3)), "服务器上只有临时中转文件")
    resp = carol.get(f"/api/tasks/{t3}/download")
    check(resp.status_code == 200, "接收接口返回 200")
    check(resp.headers.get("content-type", "").startswith("text/plain"), "内容按附件流式返回")
    check(len(resp.content) == ready_task["size_bytes"], "收到的字节数与记录一致")
    check(
        wait_until(lambda: not os.path.isdir(temp_dir(t3)), 20),
        "接收完成后服务器临时文件已删除",
    )
    check(
        wait_until(lambda: task_by_id(state(carol), t3)["status"] == "delivered", 20),
        "任务状态变为已交付",
    )
    detail = api(carol, "GET", f"/api/tasks/{t3}")
    check(detail.get("file_path") is None, "数据库不保存文件路径")
    check(detail.get("size_bytes", 0) > 0, "数据库只保留记录与大小")

    print("[7] 后台能看到用户、密钥与任务")
    overview = api(admin, "GET", "/api/admin/overview")
    check(overview["user_count"] >= 3, "后台列出用户")
    check(len(overview["keys"]) >= 3, "后台列出密钥")
    check(overview["storage_mode"] == "stream-and-delete", "后台标明不在服务器留存")
    check(len(overview["tasks"]) >= 3, "后台能看到任务记录")

    print("[8] 禁用用户 B 后会话失效")
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
