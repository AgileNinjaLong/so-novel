"""用本机 Chrome 通过 Playwright 截图前端各页面（桌面与移动端）。

用法：
    CHROME_PATH=<chrome> WEBAPP_URL=http://127.0.0.1:8099 ADMIN_USERNAME=root \
    ADMIN_PASSWORD=xxx python tests/shot_ui.py <输出目录>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = os.environ.get(
    "CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin-pass-123")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True)

        # 1) 登录页
        page = browser.new_page(viewport={"width": 1280, "height": 820})
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.screenshot(path=str(out / "login.png"))
        print("saved login.png")

        # 2) 注册页
        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.screenshot(path=str(out / "register.png"))
        print("saved register.png")

        # 3) 登录后的主界面
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.fill("#username", ADMIN_USER)
        page.fill("#password", ADMIN_PASS)
        page.click("#loginBtn")
        page.wait_for_url(f"{BASE}/", timeout=15000)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / "app.png"), full_page=True)
        print("saved app.png")

        # 4) 后台
        page.goto(f"{BASE}/admin", wait_until="networkidle")
        page.wait_for_timeout(1800)
        page.screenshot(path=str(out / "admin.png"), full_page=True)
        print("saved admin.png")

        # 5) 移动端（iPhone 尺寸）
        mobile = browser.new_page(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        context = mobile.context
        context.add_cookies(
            [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": "127.0.0.1",
                    "path": "/",
                }
                for c in page.context.cookies()
                if c["name"] == "novel_session"
            ]
            or []
        )
        mobile.goto(f"{BASE}/", wait_until="networkidle")
        mobile.wait_for_timeout(2000)
        mobile.screenshot(path=str(out / "app-mobile.png"), full_page=True)
        print("saved app-mobile.png")
        print("mobile logged in:", mobile.locator("#userName").inner_text()[:40])

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
