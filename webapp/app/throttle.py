"""暴力破解防护：按「账号 / IP / 动作」维度的持久化窗口计数 + 锁定 + 退避。

规则（窗口内的失败次数达到上限即锁定）：

| scope | 维度 | 上限 | 窗口 | 锁定时长 |
| --- | --- | --- | --- | --- |
| `login_user` | 用户名 | 5 | 15 分钟 | 15 分钟 |
| `login_ip` | 来源 IP | 20 | 15 分钟 | 15 分钟 |
| `register_ip` | 来源 IP | 10 | 60 分钟 | 60 分钟 |
| `keyinfo_ip` | 来源 IP | 30 | 60 分钟 | 60 分钟 |
| `redeem_ip` | 来源 IP | 10 | 60 分钟 | 60 分钟 |

计数存 SQLite（`throttle` 表），重启不会被绕过；失败时按次数线性增加响应延迟
（最多 2 秒），让脚本化撞库显著变慢。成功即清零。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException

from . import store


@dataclass(frozen=True)
class Policy:
    max_failures: int
    window_seconds: float
    lock_seconds: float


POLICIES: dict[str, Policy] = {
    "login_user": Policy(5, 15 * 60, 15 * 60),
    "login_ip": Policy(20, 15 * 60, 15 * 60),
    "register_ip": Policy(10, 60 * 60, 60 * 60),
    "keyinfo_ip": Policy(30, 60 * 60, 60 * 60),
    "redeem_ip": Policy(10, 60 * 60, 60 * 60),
}


def _scope_key(scope: str, subject: str) -> str:
    return f"{scope}:{subject.strip().lower()[:64]}"


def check(scope: str, subject: str) -> None:
    """若处于锁定期，直接 429（并给出剩余秒数）。"""
    policy = POLICIES[scope]
    state = store.throttle_state(_scope_key(scope, subject))
    locked_until = float(state.get("locked_until") or 0)
    now = time.time()
    if locked_until > now:
        retry_after = int(locked_until - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"尝试过于频繁，请 {retry_after} 秒后再试",
            headers={"Retry-After": str(retry_after)},
        )


def record_failure(scope: str, subject: str) -> None:
    """记录一次失败；达到阈值则锁定，并做退避延迟。"""
    policy = POLICIES[scope]
    key = _scope_key(scope, subject)
    now = time.time()
    state = store.throttle_state(key)
    window_start = float(state.get("window_start") or 0)
    count = int(state.get("fail_count") or 0)

    if now - window_start > policy.window_seconds:
        # 窗口已过，重新计数
        window_start = now
        count = 0
    count += 1
    locked_until = 0.0
    if count >= policy.max_failures:
        locked_until = now + policy.lock_seconds
        count = 0
        window_start = now

    store.throttle_upsert(
        key, fail_count=count, window_start=window_start, locked_until=locked_until
    )

    # 线性退避：第 1 次 0.2s，最多 2s（在调用方线程池里执行，不阻塞事件循环）
    delay = min(0.2 * max(1, count), 2.0)
    if locked_until:
        delay = 0.5
    time.sleep(delay)


def clear(scope: str, subject: str) -> None:
    store.throttle_clear(_scope_key(scope, subject))


def remaining(scope: str, subject: str) -> int:
    """剩余锁秒数（0 表示未锁定）。"""
    state = store.throttle_state(_scope_key(scope, subject))
    return max(0, int(float(state.get("locked_until") or 0) - time.time()))


def stats() -> dict[str, int]:
    """当前处于锁定状态的条目数量（给后台展示）。"""
    now = time.time()
    with store._lock:  # noqa: SLF001 - 同包内的只读查询
        rows = store._connection().execute(  # noqa: SLF001
            "SELECT COUNT(*) AS c FROM throttle WHERE locked_until > ?", (now,)
        ).fetchone()
    return {"locked": int(rows["c"])}
