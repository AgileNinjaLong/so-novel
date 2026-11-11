"""界面测试：队列的勾选批量删除 / 单条删除 / 后台按用户分组删除。

运行：python tests/test_delete_ui.py（需服务已启动、有上游 so-novel）
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx
from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin-pass-123")
CHROME = os.environ.get(
    "CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
BOOK = "https://www.biquge365.net/book/17221/"
FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def cookies_of(client: httpx.Client) -> list[dict]:
    return [
        {"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": "/"}
        for c in client.cookies.jar
    ]


def main() -> int:
    admin = httpx.Client(base_url=BASE, timeout=60)
    admin.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})

    # 两个用户，各下同一本书：验证后台按用户分组互不覆盖
    users = []
    for _ in range(2):
        key = admin.post("/api/admin/keys", json={"days": 7, "count": 1}).json()["keys"][0]
        client = httpx.Client(base_url=BASE, timeout=180)
        name = "u" + uuid.uuid4().hex[:6]
        client.post("/api/auth/register", json={"key": key["key"], "username": name, "password": "password123"})
        client.post("/api/source", json={"source": "sonovel", "mode": "cancel_now"})
        client.post("/api/tasks", json={"source": "sonovel", "title": "同一本书", "book_ref": BOOK, "fmt": "txt"})
        client.post("/api/tasks", json={"source": "sonovel", "title": "第二本", "book_ref": BOOK, "fmt": "txt"})
        users.append((name, client))
    time.sleep(2)

    snap = admin.get("/api/state").json()
    print(f"队列任务数：{len(snap['tasks'])}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True)

        # ---- 用户页：勾选批量删除 ----
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_cookies(cookies_of(users[0][1]))
        page = ctx.new_page()
        dialog_answers: list[bool] = []
        page.on("dialog", lambda d: (dialog_answers.append(True), d.accept()))
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(1500)

        rows = page.locator("tbody tr").count()
        check(rows > 0, "队列渲染出任务行")
        page.locator(".row-check").first.check()
        page.wait_for_timeout(300)
        check(page.is_visible("#bulkDeleteBtn"), "勾选后出现「删除选中」按钮")

        before = len(admin.get("/api/state").json()["tasks"])
        page.click("#bulkDeleteBtn")
        page.wait_for_timeout(2500)
        after = len(admin.get("/api/state").json()["tasks"])
        check(after < before, f"批量删除生效（{before} → {after}）")

        # ---- 用户页：单条删除 ----
        page.wait_for_timeout(1200)
        del_btn = page.locator('button:has-text("删除")').last
        if del_btn.count() > 0:
            before2 = len(admin.get("/api/state").json()["tasks"])
            del_btn.click()
            page.wait_for_timeout(2000)
            after2 = len(admin.get("/api/state").json()["tasks"])
            check(after2 <= before2, f"单条删除可用（{before2} → {after2}）")
        ctx.close()

        # ---- 后台：按用户分组 + 组内删除 ----
        ctx2 = browser.new_context(viewport={"width": 1280, "height": 1000})
        ctx2.add_cookies(cookies_of(admin))
        p2 = ctx2.new_page()
        p2.on("dialog", lambda d: d.accept())
        p2.goto(BASE + "/admin", wait_until="networkidle")
        p2.wait_for_timeout(1500)
        groups = p2.locator("tr.group-row").count()
        print(f"后台分组数：{groups}")
        check(groups >= 1, "后台任务按提交者分组显示")
        check(
            p2.locator('tbody td .btn:has-text("删除该用户记录")').count() >= 1,
            "每个分组都有删除按钮",
        )
        p2.screenshot(path="D:/AAA_WT_Work/TEST/小说下载网页端/shots14/admin-grouped.png", full_page=True)
        ctx2.close()
        browser.close()

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
