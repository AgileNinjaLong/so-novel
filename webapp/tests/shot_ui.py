"""用本机 Chrome 通过 Playwright 截图前端（桌面 + 移动端），并用 API 准备真实数据。

用法：
    WEBAPP_URL=http://127.0.0.1:8099 ADMIN_USERNAME=root ADMIN_PASSWORD=xxx \
    python tests/shot_ui.py <输出目录>
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

CHROME = os.environ.get(
    "CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin-pass-123")
BOOK_SMALL = "https://www.biquge365.net/book/17221/"


def session_cookies(client: httpx.Client) -> list[dict]:
    return [
        {"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": "/"}
        for c in client.cookies.jar
        if c.name == "novel_session"
    ]


def prepare() -> dict:
    """准备：一把开放型密钥、一个带有效期的用户、一个待接收任务。"""
    admin = httpx.Client(base_url=BASE, timeout=30)
    admin.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    key = admin.post("/api/admin/keys", json={"days": 372, "count": 1, "mode": "open"}).json()["keys"][0]
    bound = admin.post(
        "/api/admin/keys",
        json={"days": 31, "mode": "bound", "username": f"demo{uuid.uuid4().hex[:4]}",
              "password": "demo-pass-1", "note": "演示账号"},
    ).json()["keys"][0]

    user = httpx.Client(base_url=BASE, timeout=180)
    name = f"user{uuid.uuid4().hex[:4]}"
    user.post("/api/auth/register", json={"key": key["key"], "username": name, "password": "password123"})
    try:
        user.post("/api/source", json={"source": "sonovel", "mode": "cancel_now"})
        task = user.post("/api/tasks", json={
            "source": "sonovel", "title": "活着", "book_ref": BOOK_SMALL, "fmt": "txt"}).json()["task"]["id"]
    except Exception:
        task = ""
    return {
        "admin": admin,
        "admin_cookies": session_cookies(admin),
        "user": user,
        "user_cookies": session_cookies(user),
        "open_key": key["key"],
        "bound_key": bound["key"],
        "task": task,
        "username": name,
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    data = prepare()
    print("prepared user:", data["username"], "task:", data["task"])

    # 等任务进入待接收（最多 3 分钟）
    deadline = time.time() + 180
    while time.time() < deadline and data["task"]:
        snap = data["user"].get("/api/state").json()
        row = next((t for t in snap["tasks"] if t["id"] == data["task"]), None)
        if row and row["status"] in {"ready", "failed", "canceled", "delivered"}:
            print("task status:", row["status"])
            break
        time.sleep(3)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True)

        # 1) 注册页：查询密钥
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.fill("#key", data["open_key"])
        page.click("#checkBtn")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / "register.png"))
        print("saved register.png")

        # 2) 注册页：绑定型密钥（显示预置账号密码）
        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.fill("#key", data["bound_key"])
        page.click("#checkBtn")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / "register-bound.png"))
        print("saved register-bound.png")

        # 3) 登录页
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.screenshot(path=str(out / "login.png"))
        print("saved login.png")

        # 4) 用户主界面（含待接收任务）
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_cookies(data["user_cookies"])
        p_user = ctx.new_page()
        p_user.goto(f"{BASE}/", wait_until="networkidle")
        p_user.wait_for_timeout(2500)
        p_user.screenshot(path=str(out / "app.png"), full_page=True)
        print("saved app.png")

        # 5) 后台（含密钥列表）
        ctx_admin = browser.new_context(viewport={"width": 1280, "height": 1000})
        ctx_admin.add_cookies(data["admin_cookies"])
        p_admin = ctx_admin.new_page()
        p_admin.goto(f"{BASE}/admin", wait_until="networkidle")
        p_admin.wait_for_timeout(1800)
        p_admin.screenshot(path=str(out / "admin.png"), full_page=True)
        print("saved admin.png")

        # 6) 移动端
        ctx_m = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        ctx_m.add_cookies(data["user_cookies"])
        p_m = ctx_m.new_page()
        p_m.goto(f"{BASE}/", wait_until="networkidle")
        p_m.wait_for_timeout(2000)
        p_m.screenshot(path=str(out / "app-mobile.png"), full_page=True)
        print("saved app-mobile.png")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
