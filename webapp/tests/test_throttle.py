"""单元测试：抗暴力破解（窗口计数、锁定、持久化、作用域隔离）。

运行：python tests/test_throttle.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["WEBAPP_DATA_DIR"] = tempfile.mkdtemp(prefix="novel-throttle-test-")

from fastapi import HTTPException  # noqa: E402

from app import store, throttle  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def expect_locked(fn, label: str) -> bool:
    try:
        fn()
    except HTTPException as exc:
        ok = exc.status_code == 429
        check(ok, f"{label}（HTTP {exc.status_code}）")
        return ok
    else:
        check(False, f"{label}（未拦截）")
        return False


def main() -> int:
    store.init_db()

    print("[1] 登录账号维度：5 次失败后锁定")
    for i in range(5):
        throttle.record_failure("login_user", "victim")
    expect_locked(lambda: throttle.check("login_user", "victim"), "第 5 次失败后已锁定")
    check(throttle.remaining("login_user", "victim") > 0, "剩余锁定时间 > 0")

    print("[2] 锁定写入数据库（重启不可绕过）")
    state = store.throttle_state("login_user:victim")
    check(float(state["locked_until"]) > time.time(), "数据库记录了锁定截止时间")

    print("[3] 作用域隔离：其他账号/其他动作不受影响")
    throttle.check("login_user", "someone-else")
    check(True, "其他账号未被锁定")
    throttle.check("keyinfo_ip", "1.2.3.4")
    check(True, "其他动作未被锁定")

    print("[4] 成功登录清空计数")
    throttle.clear("login_user", "victim")
    check(throttle.remaining("login_user", "victim") == 0, "清除后可继续尝试")
    throttle.check("login_user", "victim")
    check(True, "清除后 check 通过")

    print("[5] 窗口过期后重新计数")
    now = time.time()
    store.throttle_upsert(
        "login_user:reset-me",
        fail_count=4,
        window_start=now - 20 * 60,
        locked_until=0,
    )
    throttle.record_failure("login_user", "reset-me")
    state = store.throttle_state("login_user:reset-me")
    check(int(state["fail_count"]) == 1, "窗口过期后计数从 1 重新开始")
    check(float(state["window_start"]) > now - 60, "窗口起点已刷新")

    print("[6] IP 维度阈值更高（20 次）")
    for _ in range(19):
        throttle.record_failure("login_ip", "9.9.9.9")
    throttle.check("login_ip", "9.9.9.9")
    check(True, "19 次失败后仍未锁定")
    throttle.record_failure("login_ip", "9.9.9.9")
    expect_locked(lambda: throttle.check("login_ip", "9.9.9.9"), "第 20 次失败后锁定")

    print("[7] 注册/兑换维度阈值 10 次")
    for _ in range(10):
        throttle.record_failure("redeem_ip", "8.8.8.8")
    expect_locked(lambda: throttle.check("redeem_ip", "8.8.8.8"), "第 10 次后锁定")

    print("[8] 锁定统计与过期清理")
    stats = throttle.stats()
    check(stats["locked"] >= 2, "统计能反映锁定条目")
    cleared = store.throttle_purge_stale(older_than_seconds=0)
    check(cleared >= 0, "过期清理可执行")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
