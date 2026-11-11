"""单元测试：so-novel 日志按任务开始时间过滤（防止读到上一个任务的日志导致书名串台）。

运行：python tests/test_log_filter.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WEBAPP_DATA_DIR", tempfile.mkdtemp(prefix="novel-log-test-"))

from app.plugins.sonovel import _read_log_info, _tail_log  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def write_log(logs: Path, name: str, title: str, total: int, mtime: float) -> Path:
    path = logs / name
    path.write_text(
        f"[INFO] 开始下载：《{title}》(作者)\n[INFO] 共计 {total} 章\n",
        encoding="utf-8",
    )
    os.utime(path, (mtime, mtime))
    return path


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="novel-log-work-"))
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    now = time.time()
    old = write_log(logs, "活着 (余华) 章节下载 2026-01-01.log", "活着", 11, now - 3600)
    new = write_log(logs, "战神 (x) 章节下载 2026-01-02.log", "战神", 200, now - 5)

    print("[1] 不带 since 时取最新日志（旧行为）")
    title, author, total = _read_log_info(work)
    check(title == "战神" and total == 200, f"取到最新任务（{title}/{total}）")

    print("[2] 任务开始时间晚于旧日志：只能读到本任务日志")
    since = now - 60  # 新任务在 60 秒前开始
    title2, _, total2 = _read_log_info(work, since=since)
    check(title2 == "战神", "读到的是本任务的书名")
    check(total2 == 200, "总章数来自本任务")

    print("[3] 本任务还没写出日志时，不返回上一个任务的信息")
    since_later = now + 1
    title3, _, total3 = _read_log_info(work, since=since_later)
    check(title3 == "" and total3 == 0, "没有本任务日志时不串台（返回空）")

    print("[4] 失败原因只取本任务日志")
    tail = _tail_log(work, "战神", "x", since=since)
    check("战神" in tail and "活着" not in tail, f"日志尾部来自本任务：{tail[:40]}")
    tail_old = _tail_log(work, "活着", "余华", since=since_later)
    check(tail_old == "", "旧日志不会被当作本任务错误")

    print("[5] 日志目录不存在时安全返回")
    empty = Path(tempfile.mkdtemp(prefix="novel-log-empty-"))
    check(_read_log_info(empty) == ("", "", 0), "无 logs 目录返回空")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
