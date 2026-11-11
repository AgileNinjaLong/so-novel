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
    admin = httpx.Client(base_url=BASE, timeout=30)
    admin.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})

    # 一把留给注册页演示（不绑定），一把用来创建真实用户
    demo_key = admin.post("/api/admin/keys", json={"days": 372, "count": 1}).json()["keys"][0]
    real_key = admin.post("/api/admin/keys", json={"days": 372, "count": 1}).json()["keys"][0]

    user = httpx.Client(base_url=BASE, timeout=180)
    username = f"reader{uuid.uuid4().hex[:4]}"
    user.post(
        "/api/auth/register",
        json={"key": real_key["key"], "username": username, "password": "reader-pass-1"},
    )
    try:
        user.post("/api/source", json={"source": "sonovel", "mode": "cancel_now"})
        # 用搜索得到的 3 本不同的书，截图里队列更像真实场景
        found = user.get("/api/search", params={"q": "活着"}).json()["items"]
        picks = [(i["title"], i["book_ref"]) for i in found[:3]] or [("活着", BOOK_SMALL)]
        task = user.post("/api/tasks", json={
            "source": "sonovel", "title": picks[0][0], "book_ref": picks[0][1], "fmt": "txt"}).json()["task"]["id"]
        for title, ref in picks[1:]:
            user.post("/api/tasks", json={
                "source": "sonovel", "title": title, "book_ref": ref, "fmt": "txt"})
        # 管理员也提交一条，后台可展示「按用户分组」
        admin.post("/api/source", json={"source": "sonovel", "mode": "cancel_now"})
        admin.post("/api/tasks", json={
            "source": "sonovel", "title": picks[-1][0], "book_ref": picks[-1][1], "fmt": "txt"})
    except Exception:
        task = ""
    return {
        "admin": admin,
        "admin_cookies": session_cookies(admin),
        "user": user,
        "user_cookies": session_cookies(user),
        "demo_key": demo_key["key"],
        "task": task,
        "username": username,
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    data = prepare()
    print("prepared user:", data["username"], "task:", data["task"])

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

        # 1) 注册页：查询密钥后显示有效期 + 自设账号密码
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.fill("#key", data["demo_key"])
        page.click("#checkBtn")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out / "register.png"))
        print("saved register.png")

        # 2) 登录页
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.screenshot(path=str(out / "login.png"))
        print("saved login.png")

        # 3) 用户主界面 + 搜索结果
        ctx = browser.new_context(viewport={"width": 1280, "height": 950})
        ctx.add_cookies(data["user_cookies"])
        p_user = ctx.new_page()
        p_user.goto(f"{BASE}/", wait_until="networkidle")
        p_user.wait_for_timeout(2000)
        p_user.screenshot(path=str(out / "app.png"), full_page=True)
        print("saved app.png")

        p_user.fill("#searchBox", "活着")
        p_user.click("#searchBtn")
        p_user.wait_for_timeout(1200)
        for _ in range(40):
            if p_user.locator(".result-item").count() > 0:
                break
            if p_user.locator("#searchMeta").inner_text().startswith("搜索失败"):
                break
            p_user.wait_for_timeout(1000)
        print("results:", p_user.locator(".result-item").count(), "|", p_user.inner_text("#searchMeta")[:60])
        p_user.screenshot(path=str(out / "search.png"), full_page=True)
        print("saved search.png")

        # 选中第一条，展示选择态
        first = p_user.locator(".result-item").first
        if first.count() > 0:
            first.locator(".pick-btn").click()
            p_user.wait_for_timeout(600)
            p_user.screenshot(path=str(out / "search-selected.png"), full_page=True)
            print("saved search-selected.png")

        # 4) 后台
        ctx_admin = browser.new_context(viewport={"width": 1280, "height": 1000})
        ctx_admin.add_cookies(data["admin_cookies"])
        p_admin = ctx_admin.new_page()
        p_admin.goto(f"{BASE}/admin", wait_until="networkidle")
        p_admin.wait_for_timeout(1500)
        p_admin.screenshot(path=str(out / "admin.png"), full_page=True)
        print("saved admin.png")

        # 5) 移动端
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
        p_m.wait_for_timeout(1200)
        p_m.fill("#searchBox", "活着")
        p_m.click("#searchBtn")
        for _ in range(40):
            if p_m.locator(".result-item").count() > 0:
                break
            p_m.wait_for_timeout(1000)
        p_m.wait_for_timeout(800)
        p_m.screenshot(path=str(out / "app-mobile.png"), full_page=True)
        print("saved app-mobile.png")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
