"""真实上游回归：连续下载两本不同的书，验证书名/章数不串台。

背景：so-novel 的日志写在共享目录，新任务曾读到上一个任务的日志，导致
「下载《战神》却显示《活着》」并且章数取到上一本的总数。

运行：python tests/test_title_stability.py（需服务已启动、so-novel 可用）
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


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def main() -> int:
    admin = httpx.Client(base_url=BASE, timeout=120)
    admin.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    key = admin.post("/api/admin/keys", json={"days": 31, "count": 1}).json()["keys"][0]
    user = httpx.Client(base_url=BASE, timeout=300)
    name = "u" + uuid.uuid4().hex[:6]
    user.post("/api/auth/register", json={"key": key["key"], "username": name, "password": "password123"})
    user.post("/api/source", json={"source": "sonovel", "mode": "cancel_now"})

    items = user.get("/api/search", params={"q": "战神"}).json()["items"]
    zs = next((i for i in items if i["title"].strip() == "战神"), items[0] if items else None)
    if zs is None:
        print("搜索无结果，跳过")
        return 1

    t1 = user.post("/api/tasks", json={
        "source": "sonovel", "title": "活着",
        "book_ref": "https://www.biquge365.net/book/17221/", "fmt": "txt"}).json()["task"]["id"]
    t2 = user.post("/api/tasks", json={
        "source": "sonovel", "title": "战神", "book_ref": zs["book_ref"], "fmt": "txt"}).json()["task"]["id"]
    print(f"第一本=活着({t1})　第二本=战神({t2})　第二个链接={zs['book_ref']}")

    rows: dict[str, dict] = {}
    totals: list[tuple[int, int]] = []
    for _ in range(70):
        rows = {x["id"]: x for x in user.get("/api/state").json()["tasks"]}
        r2 = rows.get(t2, {})
        if r2.get("chapters_total"):
            totals.append((r2["chapters_done"], r2["chapters_total"]))
        if (rows.get(t1, {}).get("status") in {"ready", "failed"}
                and r2.get("status") in {"ready", "failed"}):
            break
        time.sleep(3)

    final1 = rows[t1]
    final2 = rows[t2]
    check(final1["title"] == "活着", f"第一本仍是「活着」（实际：{final1['title']}）")
    check(final2["title"] == "战神", f"第二本仍是「战神」（实际：{final2['title']}）")
    # 第二本的章数不应等于第一本的 11 章（除非确实只有 11 章）
    total2 = final2.get("chapters_total") or 0
    if total2:
        check(total2 != 11, f"第二本的总章数不是上一本的 11（实际：{total2}）")
    print(f"第二本进度快照：{totals[-3:]}")

    # 清理本次两条记录
    for tid in (t1, t2):
        try:
            user.post("/api/tasks/bulk-delete", json={"ids": [t1, t2]})
        except Exception:
            pass
        break

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
