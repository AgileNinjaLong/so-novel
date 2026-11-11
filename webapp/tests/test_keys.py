"""单元测试：密钥只带有效期；用户注册时自设账号密码，绑定后后台可见。

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

    print("[1] 生成密钥：只带有效期，不生成账号密码")
    keys = auth.generate_invite_keys(days=372, count=3, created_by="test")
    check(len(keys) == 3, "一次生成 3 把")
    check(len({k["key"] for k in keys}) == 3, "密钥互不相同")
    check(all(len(k["key"]) == 21 for k in keys), "每把 21 字符")
    check(all(k["username"] is None and k["password_plain"] is None for k in keys), "未生成账号密码")
    check(all(k["status"] == "unused" for k in keys), "初始未使用")

    print("[2] 未使用时查询：只有有效期，没有账号")
    info = auth.key_public_info(keys[0]["key"], ip="1.1.1.1")
    check(info["valid"] is True, "密钥有效")
    check(info["days_text"] == "372 天", "显示有效期")
    check(info["username"] == "" and info["password"] == "", "没有账号密码")
    check(info.get("needs_credentials") is True, "提示需要用户自己设置账密")

    print("[3] 注册时必须自己提供账号密码")
    expect_http(lambda: auth.redeem_key(keys[0]["key"], "", "", ip="1.1.1.1"), 400, "缺账号密码被拒绝")
    expect_http(lambda: auth.redeem_key(keys[0]["key"], "ab", "password123", ip="1.1.1.1"), 400, "用户名过短被拒绝")
    expect_http(lambda: auth.redeem_key(keys[0]["key"], "alice", "short", ip="1.1.1.1"), 400, "密码过短被拒绝")

    print("[4] 注册成功：账号按用户填的创建，有效期来自密钥")
    user = auth.redeem_key(keys[0]["key"], "alice", "alice-pass-1", ip="1.1.1.1")
    check(user["username"] == "alice", "账号为用户填写的用户名")
    check(validity.remaining_days(user) == 372, "有效期 372 天")
    check(auth.authenticate("alice", "alice-pass-1", ip="1.1.1.1")["username"] == "alice", "可用自设密码登录")

    print("[5] 注册后密钥与账号绑定，后台可见账号密码")
    row = store.get_invite_key(keys[0]["id"])
    check(row["status"] == "used", "密钥标记已使用")
    check(row["username"] == "alice", "绑定了账号")
    check(row["password_plain"] == "alice-pass-1", "绑定了密码（供后台展示）")
    check(row["used_by_name"] == "alice", "记录了使用者")
    used_info = auth.key_public_info(keys[0]["key"], ip="1.1.1.1")
    check(used_info["valid"] is False, "已用密钥不能再注册")
    check(used_info["username"] == "alice" and used_info["password"] == "alice-pass-1", "查询仍能显示绑定账密")

    print("[6] 一把密钥只能注册一次")
    expect_http(lambda: auth.redeem_key(keys[0]["key"], "alice2", "password123", ip="1.1.1.1"), 403, "重复注册被拒绝")

    print("[7] 用户名冲突")
    expect_http(lambda: auth.redeem_key(keys[1]["key"], "alice", "password123", ip="1.1.1.1"), 409, "重名被拒绝")

    print("[8] 999999 → 永久")
    perm = auth.generate_invite_keys(days=999999, count=1)[0]
    check(perm["permanent"] == 1, "密钥标记永久")
    u3 = auth.redeem_key(perm["key"], "dave", "dave-pass-1", ip="3.3.3.3")
    check(u3["permanent"] == 1, "账号永久")
    check(validity.remaining_days(u3) is None, "永久不显示天数")

    print("[9] 撤销 / 删除 / 有效期校验")
    k = auth.generate_invite_keys(days=31, count=1)[0]
    check(store.revoke_invite_key(k["id"]) is True, "撤销成功")
    expect_http(lambda: auth.redeem_key(k["key"], "eve", "password123", ip="4.4.4.4"), 403, "已撤销密钥被拒绝")
    check(store.delete_invite_key(k["id"]) is True, "删除记录成功")
    check(store.get_invite_key(k["id"]) is None, "记录已不存在")

    # 支持自定义时长：1..65535 任意天数
    custom = auth.generate_invite_keys(days=7, count=1)[0]
    check(custom["days"] == 7 and custom["permanent"] == 0, "可以生成 7 天的自定义密钥")
    custom_user = auth.redeem_key(custom["key"], "frank", "frank-pass-1", ip="5.5.5.5")
    check(validity.remaining_days(custom_user) == 7, "自定义 7 天的账号有效期正确")
    max_days_key = auth.generate_invite_keys(days=65535, count=1)[0]
    check(max_days_key["days"] == 65535, "可以生成 65535 天的密钥")
    expect_http(lambda: auth.generate_invite_keys(days=0, count=1), 400, "0 天被拒绝")
    expect_http(lambda: auth.generate_invite_keys(days=65536, count=1), 400, "超过 65535 天被拒绝")

    print("[10] 密钥唯一性")
    all_keys = store.list_invite_keys()
    check(len({x["key"] for x in all_keys}) == len(all_keys), "库内密钥无重复")
    check(store.invite_key_code_exists(keys[1]["key"]) is True, "已存在密钥可检测")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
