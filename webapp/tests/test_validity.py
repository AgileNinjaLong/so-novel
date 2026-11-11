"""单元测试：有效期叠加、uint16 封顶、永久标记。

运行：python tests/test_validity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import validity  # noqa: E402

FAILED: list[str] = []
NOW = 1_800_000_000  # 固定时间，保证结果可断言


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def user(**kwargs):
    base = {"status": "active", "permanent": 0, "expires_at": None}
    base.update(kwargs)
    return base


def main() -> int:
    print("[1] 初始状态")
    u = user()
    check(not validity.is_active(u, NOW), "无有效期时不可用")
    check(validity.remaining_days(u, NOW) == 0, "剩余天数 0")

    print("[2] 叠加 1 天")
    granted = validity.grant(u, 1, NOW)
    u2 = user(**granted)
    check(validity.is_active(u2, NOW), "加 1 天后可用")
    check(validity.remaining_days(u2, NOW) == 1, "剩余 1 天")

    print("[3] 继续叠加（31 天，累加而不是覆盖）")
    granted = validity.grant(u2, 31, NOW)
    u3 = user(**granted)
    check(validity.remaining_days(u3, NOW) == 32, "1 + 31 = 32 天")

    print("[4] 继续叠加 124 / 372 天")
    granted = validity.grant(u3, 124, NOW)
    u4 = user(**granted)
    check(validity.remaining_days(u4, NOW) == 32 + 124, "32 + 124 = 156 天")
    granted = validity.grant(u4, 372, NOW)
    u5 = user(**granted)
    check(validity.remaining_days(u5, NOW) == 156 + 372, "156 + 372 = 528 天")

    print("[5] uint16 封顶（65535 天）")
    near_cap = user(expires_at=validity.fmt_ts(NOW + 65530 * 86400))
    granted = validity.grant(near_cap, 372, NOW)
    capped = user(**granted)
    check(
        validity.remaining_days(capped, NOW) == validity.MAX_DAYS,
        f"65530 + 372 天时封顶到 {validity.MAX_DAYS} 天",
    )
    # 恰好等于上限时不会被截断
    exact = user(expires_at=validity.fmt_ts(NOW + (validity.MAX_DAYS - 1) * 86400))
    granted = validity.grant(exact, 1, NOW)
    kept = user(**granted)
    check(
        validity.remaining_days(kept, NOW) == validity.MAX_DAYS,
        "恰好到 65535 天时保留完整天数",
    )

    print("[6] 999999 视为永久")
    granted = validity.grant(user(), 999999, NOW)
    perm = user(**granted)
    check(granted["permanent"] == 1 and granted["expires_at"] is None, "标记为永久且清空到期时间")
    check(validity.is_active(perm, NOW), "永久账号可用")
    check(validity.remaining_days(perm, NOW) is None, "永久账号不返回天数")
    # 永久账号再加天数不会退化
    again = validity.grant(perm, 1, NOW)
    check(again["permanent"] == 1, "永久账号叠加天数后仍永久")

    print("[7] 已过期账号")
    expired = user(expires_at=validity.fmt_ts(NOW - 86400))
    check(not validity.is_active(expired, NOW), "过期账号不可用")
    check(validity.remaining_days(expired, NOW) == 0, "过期后剩余天数归零")

    print("[8] 过期后叠加从「现在」重新开始")
    granted = validity.grant(expired, 31, NOW)
    revived = user(**granted)
    check(validity.remaining_days(revived, NOW) == 31, "过期后 +31 天 = 31 天")

    print("[9] 封禁状态")
    banned = user(status="banned", permanent=1)
    check(not validity.is_active(banned, NOW), "被禁用的永久账号也不可用")

    print("[10] 预设档位")
    check(
        validity.GRANT_PRESETS == (1, 31, 124, 372, 999999),
        "档位为 1/31/124/372/999999",
    )
    check(validity.MAX_DAYS == 65535, "uint16 上限为 65535")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
