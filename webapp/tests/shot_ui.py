"""用本机 Chrome 通过 Playwright 截图前端关键状态（仅用于本地验收，不随部署）。

用法：CHROME_PATH=<chrome 可执行文件> WEBAPP_URL=http://127.0.0.1:8099 python tests/shot_ui.py <输出目录>
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

CHROME = os.environ.get(
    "CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
BASE = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099").rstrip("/")


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(3500)
        page.screenshot(path=f"{out_dir}/shot-queue.png", full_page=True)
        print("saved shot-queue.png")
        print("source status:", page.inner_text("#sourceStatus").replace("\n", " / "))

        counts = page.inner_text("#countBadge")
        print("counts:", counts)

        # 触发切换弹窗（当前有 running 任务时选另一个来源）
        page.select_option("#sourceSelect", "sonovel")
        page.wait_for_timeout(800)
        modal_visible = page.is_visible("#modal")
        print("modal visible:", modal_visible)
        if modal_visible:
            page.screenshot(path=f"{out_dir}/shot-modal.png", full_page=False)
            print("saved shot-modal.png")
            print("modal text:", page.inner_text("#modalText")[:200].replace("\n", " | "))
            page.click("#modalCancel")
            page.wait_for_timeout(300)
            print("after cancel, select back to:", page.input_value("#sourceSelect"))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
