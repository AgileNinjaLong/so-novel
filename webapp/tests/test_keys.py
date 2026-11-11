"""单元测试：一钥一用户的邀请密钥（生成、兑换、单次使用、绑定型、撤销）。

运行：python tests/test_keys.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["WEBAPP_DATA_DIR"] = tempfile.mkdtemp(prefix="novel-keys-test-")

from fastapi import HTTPException  # noqa: E402

from app import auth, store, validity  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def expect_http(fn, status: int, label: str) -> None:
    try:
        fn()
    except HTTPException as exc:
        check(exc.status_code == status, f"{label}（HTTP {exc.status_code}）")
    else:
        check(False, f"{label}（没有抛出异常）")


def main() -> int:
    store.init_db()

    print("[1] 批量生成开放型密钥")
    keys = auth.generate_invite_keys(days=372, count=3, mode="open", created_by="test")
    check(len(keys) == 3, "一次生成 3 把")
    check(len({k["key"] for k in keys}) == 3, "密钥互不相同")
    check(all(len(k["key"]) == 21 for k in keys), "每把 21 字符")
    check(all(k["status"] == "unused" for k in keys), "初始状态为未使用")
    check(all(k["mode"] == "open" for k in keys), "类型为开放型")

    print("[2] 兑换开放型密钥：用户自填账号密码，获得 372 天")
    user = auth.redeem_key(keys[0]["key"], "alice", "password123")
    check(user["username"] == "alice", "账号创建成功")
    check(validity.remaining_days(user) == 372, "有效期 = 密钥设定的 372 天")
    check(store.get_invite_key(keys[0]["id"])["status"] == "used", "密钥已标记使用")
    check(store.get_invite_key(keys[0]["id"])["used_by_name"] == "alice", "记录了使用者")

    print("[3] 同一把密钥不能再用")
    expect_http(lambda: auth.redeem_key(keys[0]["key"], "alice2", "password123"), 403, "重复兑换被拒绝")

    print("[4] 绑定型密钥：预置账号密码并可在后台查看")
    bound = auth.generate_invite_keys(
        days=31,
        mode="bound",
        username="bobby",
        password="bobby-pass-1",
        note="给老王",
        created_by="test",
    )[0]
    check(bound["mode"] == "bound", "类型为绑定型")
    check(bound["username"] == "bobby", "预置了用户名")
    check(bound["password_plain"] == "bobby-pass-1", "保存了可展示的密码")
    info = auth.key_public_info(bound["key"])
    check(info["valid"] is True, "前台可查询到该密钥")
    check(info["mode"] == "bound", "前台识别为绑定型")
    check(info["username"] == "bobby" and info["password"] == "bobby-pass-1", "前台能看到预置账号密码")

    print("[5] 兑换绑定型密钥（无需再填账号密码）")
    user2 = auth.redeem_key(bound["key"], "", "")
    check(user2["username"] == "bobby", "账号为预置用户名")
    check(validity.remaining_days(user2) == 31, "有效期 = 31 天")
    check(auth.authenticate("bobby", "bobby-pass-1")["username"] == "bobby", "预置密码可直接登录")

    print("[6] 绑定型密钥不能批量生成")
    bound_many = auth.generate_invite_keys(
        days=1, count=5, mode="bound", username="carol", password="carol-pass-1"
    )
    check(len(bound_many) == 1, "绑定型只会生成 1 把")

    print("[7] 999999 → 永久")
    perm_key = auth.generate_invite_keys(days=999999, count=1, mode="open")[0]
    check(perm_key["permanent"] == 1, "密钥标记为永久")
    user3 = auth.redeem_key(perm_key["key"], "dave", "password123")
    check(user3["permanent"] == 1, "账号永久有效")
    check(validity.remaining_days(user3) is None, "永久账号不显示天数")

    print("[8] 撤销后不可兑换")
    k = auth.generate_invite_keys(days=31, count=1, mode="open")[0]
    check(store.revoke_invite_key(k["id"]) is True, "撤销成功")
    expect_http(lambda: auth.redeem_key(k["key"], "eve", "password123"), 403, "已撤销密钥被拒绝")
    check(auth.key_public_info(k["key"])["valid"] is False, "前台查询显示不可用")

    print("[9] 错误的档位被拒绝")
    expect_http(lambda: auth.generate_invite_keys(days=7, count=1), 400, "非预设档位被拒绝")

    print("[10] 密钥碰撞检查：存在性函数生效")
    existing = store.list_invite_keys()
    check(len({x["key"] for x in existing}) == len(existing), "库内密钥无重复")
    check(store.invite_key_code_exists(keys[1]["key"]) is True, "已存在的密钥可被检测到")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
