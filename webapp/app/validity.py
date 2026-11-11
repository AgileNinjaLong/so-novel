"""用户有效期计算：按天叠加、封顶 uint16、999999 视为永久。

规则（来自需求）：
- 后台可给用户增加 1 / 31 / 124 / 372 / 999999 天；
- 除 999999 外，天数**叠加**到用户现有有效期上；
- 叠加后的剩余天数上限为 uint16 的 65535 天；
- 999999 天表示「永久有效」，用独立标记位存储，不参与天数计算。
"""

from __future__ import annotations

import math
import time
from typing import Any, Mapping, MutableMapping

# uint16 上限
MAX_DAYS = 65535
# 该档位表示永久
PERMANENT_DAYS = 999999
# 允许叠加的档位（后台按钮）
GRANT_PRESETS = (1, 31, 124, 372, PERMANENT_DAYS)

SECONDS_PER_DAY = 86400


def now_ts() -> int:
    return int(time.time())


def parse_ts(value: Any) -> int | None:
    """接受 ISO 字符串或整数秒；无效返回 None。"""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    # 数据库里统一存 "YYYY-MM-DDTHH:MM:SSZ"（UTC）
    try:
        from datetime import datetime

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return int(datetime.fromisoformat(text).timestamp())
    except Exception:
        try:
            return int(float(text))
        except Exception:
            return None


def fmt_ts(ts: int | None) -> str | None:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


def is_permanent(user: Mapping[str, Any]) -> bool:
    return bool(user.get("permanent"))


def remaining_seconds(user: Mapping[str, Any], now: int | None = None) -> int:
    now = now_ts() if now is None else now
    if is_permanent(user):
        return MAX_DAYS * SECONDS_PER_DAY
    expires = parse_ts(user.get("expires_at"))
    if expires is None:
        return 0
    return max(0, expires - now)


def remaining_days(user: Mapping[str, Any], now: int | None = None) -> int | None:
    """返回剩余天数（向上取整）；永久返回 None。"""
    if is_permanent(user):
        return None
    seconds = remaining_seconds(user, now)
    return int(math.ceil(seconds / SECONDS_PER_DAY)) if seconds > 0 else 0


def is_active(user: Mapping[str, Any], now: int | None = None) -> bool:
    if str(user.get("status") or "active") != "active":
        return False
    if is_permanent(user):
        return True
    return remaining_seconds(user, now) > 0


def grant(user: Mapping[str, Any], days: int, now: int | None = None) -> dict[str, Any]:
    """计算叠加后的有效期字段；返回可直接写库的 dict。

    - days >= 999999 → 永久（permanent=1, expires_at=None）
    - 否则在 max(now, 现有到期) 之上加 days，并把**剩余天数**封顶到 MAX_DAYS
    """
    now = now_ts() if now is None else now
    if days < 0:
        raise ValueError("天数不能为负")

    if is_permanent(user) or days >= PERMANENT_DAYS:
        return {"permanent": 1, "expires_at": None}

    current = parse_ts(user.get("expires_at")) if not is_permanent(user) else None
    base = max(now, current or 0)
    candidate = base + int(days) * SECONDS_PER_DAY
    # 剩余天数封顶 uint16
    cap = now + MAX_DAYS * SECONDS_PER_DAY
    expires = min(candidate, cap)
    return {"permanent": 0, "expires_at": fmt_ts(expires)}


def status_fields(user: MutableMapping[str, Any], now: int | None = None) -> dict[str, Any]:
    """给前端展示用的派生字段。"""
    now = now_ts() if now is None else now
    days = remaining_days(user, now)
    return {
        "permanent": is_permanent(user),
        "remaining_days": days,
        "expires_at": user.get("expires_at"),
        "active": is_active(user, now),
    }
