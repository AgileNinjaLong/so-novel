"""黑盒（浏览器）测试：点击「接收文件」应真正把文件保存到本机，并在确认后删除服务器临时文件。

前置：服务在 WEBAPP_URL 运行，且有可用上游（so-novel）。
运行：python tests/test_receive_browser.py
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin-pass-123")
CHROME = os.environ.get(
    "CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
TMP_ROOT = os.environ.get(
    "WEBAPP_TMP_ROOT", r"D:\AAA_WT_Work\TEST\小说下载网页端\webapp-data\runtime\tmp"
)
BOOK = "https://www.biquge365.net/book/17221/"
FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def main() -> int:
    admin = httpx.Client(base_url=BASE, timeout=60)
    admin.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    key = admin.post("/api/admin/keys", json={"days": 5, "count": 1}).json()["keys"][0]
    user = httpx.Client(base_url=BASE, timeout=180)
    name = "u" + uuid.uuid4().hex[:6]
    user.post("/api/auth/register", json={"key": key["key"], "username": name, "password": "password123"})
    user.post("/api/source", json={"source": "sonovel", "mode": "cancel_now"})
    task = user.post("/api/tasks", json={"source": "sonovel", "title": "活着", "book_ref": BOOK, "fmt": "txt"}).json()["task"]["id"]

    row = None
    for _ in range(120):
        row = [x for x in user.get("/api/state").json()["tasks"] if x["id"] == task][0]
        if row["status"] in {"ready", "failed"}:
            break
        time.sleep(1)
    print(f"任务状态：{row['status']} 大小={row['size_bytes']}")
    check(row["status"] == "ready", "下载完成进入待接收")

    tmp_dir = os.path.join(TMP_ROOT, task)
    check(os.path.isdir(tmp_dir), "服务器存在临时文件")

    cookies = [
        {"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": "/"}
        for c in user.cookies.jar
    ]
    saved_files: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True)
        ctx = browser.new_context(accept_downloads=True)
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(1200)

        btn = page.locator('button:has-text("接收文件")').first
        check(btn.count() > 0, "界面上出现「接收文件」按钮")

        btn.click()
        page.wait_for_timeout(600)
        check(page.is_visible("#receiveModal"), "弹出接收确认框（说明未接收会删除）")
        tip = page.inner_text("#receiveText")
        check("自动删除" in tip or "重新下载" in tip, "确认框包含「未接收会删除」的提示")
        page.screenshot(path="D:/AAA_WT_Work/TEST/小说下载网页端/shots11/receive-dialog.png")
        with page.expect_download(timeout=30000) as dl:
            page.click("#receiveOk")
        download = dl.value
        path = download.path()
        saved_files.append(path)
        size = os.path.getsize(path) if path else 0
        print(f"浏览器保存的文件：{download.suggested_filename} ({size} 字节)")
        check(size == row["size_bytes"], "浏览器收到的字节数与服务器记录一致")
        check(bool(download.suggested_filename), f"文件名正常：{download.suggested_filename}")

        page.wait_for_timeout(2000)
        check(not os.path.isdir(tmp_dir), "确认接收后服务器临时文件被删除")
        snap = [x for x in user.get("/api/state").json()["tasks"] if x["id"] == task][0]
        check(snap["status"] == "delivered", "任务状态变为已接收")
        check(snap["can_receive"] is False, "已接收后不再显示接收入口")

        # 再点一次应该没有按钮（或接口 409）
        check(
            page.locator('button:has-text("接收文件")').count() == 0,
            "刷新后不再出现接收按钮",
        )
        browser.close()

    # 清理下载到临时目录的文件
    for path in saved_files:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
