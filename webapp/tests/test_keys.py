"""单元测试：一钥一账号的密钥（自动/指定账号、单次使用、有效期、撤销、使用后可查账号）。

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

    print("[1] 管理员生成密钥：账号密码自动生成")
    keys = auth.generate_invite_keys(days=372, count=3, created_by="test")
    check(len(keys) == 3, "一次生成 3 把")
    check(len({k["key"] for k in keys}) == 3, "密钥互不相同")
    check(all(len(k["key"]) == 21 for k in keys), "每把 21 字符")
    check(all(k["username"] and k["password_plain"] for k in keys), "每把都有自动生成的账号密码")
    check(len({k["username"] for k in keys}) == 3, "账号互不相同")
    check(all(k["mode"] == "bound" for k in keys), "统一为绑定账号型")
    check(all(k["status"] == "unused" for k in keys), "初始未使用")

    print("[2] 查询密钥：可直接看到账号密码")
    info = auth.key_public_info(keys[0]["key"], ip="1.1.1.1")
    check(info["valid"] is True, "未使用密钥有效")
    check(info["username"] == keys[0]["username"], "返回账号")
    check(info["password"] == keys[0]["password_plain"], "返回密码")

    print("[3] 激活：账号来自密钥，有效期 = 密钥天数")
    user = auth.redeem_key(keys[0]["key"], ip="1.1.1.1")
    check(user["username"] == keys[0]["username"], "创建的账号等于密钥绑定账号")
    check(validity.remaining_days(user) == 372, "有效期 372 天")
    check(auth.authenticate(keys[0]["username"], keys[0]["password_plain"], ip="1.1.1.1")["username"] == user["username"],
          "用密钥里的账号密码可登录")
    check(store.get_invite_key(keys[0]["id"])["status"] == "used", "密钥标记已使用")
    check(store.get_invite_key(keys[0]["id"])["used_by_name"] == user["username"], "记录了使用者")

    print("[4] 同一把密钥不能二次使用")
    expect_http(lambda: auth.redeem_key(keys[0]["key"], ip="1.1.1.1"), 403, "重复激活被拒绝")

    print("[5] 已使用的密钥仍显示其账号密码（后台/前台都能看到）")
    used_info = auth.key_public_info(keys[0]["key"], ip="1.1.1.1")
    check(used_info["valid"] is False, "已使用密钥不能再用")
    check(used_info["username"] == keys[0]["username"], "仍返回账号")
    check(used_info["password"] == keys[0]["password_plain"], "仍返回密码")
    check(used_info["used_by_name"] == user["username"], "返回使用者")

    print("[6] 管理员指定账号密码：只生成 1 把")
    named = auth.generate_invite_keys(days=31, count=5, username="boss", password="boss-pass-1")
    check(len(named) == 1, "指定用户名时只生成 1 把")
    check(named[0]["username"] == "boss" and named[0]["password_plain"] == "boss-pass-1", "账号密码为管理员指定")
    u2 = auth.redeem_key(named[0]["key"], ip="2.2.2.2")
    check(u2["username"] == "boss", "激活后账号为 boss")
    check(validity.remaining_days(u2) == 31, "有效期 31 天")

    print("[7] 用户名冲突与非法输入")
    expect_http(
        lambda: auth.generate_invite_keys(days=1, username="boss", password="x12345678"),
        409,
        "用户名已存在时拒绝",
    )
    expect_http(lambda: auth.generate_invite_keys(days=1, username="ab"), 400, "用户名过短被拒绝")
    expect_http(lambda: auth.generate_invite_keys(days=7, count=1), 400, "非预设档位被拒绝")

    print("[8] 999999 → 永久")
    perm = auth.generate_invite_keys(days=999999, count=1)[0]
    check(perm["permanent"] == 1, "密钥标记永久")
    u3 = auth.redeem_key(perm["key"], ip="3.3.3.3")
    check(u3["permanent"] == 1, "账号永久")
    check(validity.remaining_days(u3) is None, "永久不显示天数")

    print("[9] 撤销与删除")
    k = auth.generate_invite_keys(days=31, count=1)[0]
    check(store.revoke_invite_key(k["id"]) is True, "撤销成功")
    expect_http(lambda: auth.redeem_key(k["key"], ip="4.4.4.4"), 403, "已撤销密钥被拒绝")
    check(auth.key_public_info(k["key"], ip="4.4.4.4")["valid"] is False, "前台查询不可用")
    check(store.delete_invite_key(k["id"]) is True, "删除记录成功")
    check(store.get_invite_key(k["id"]) is None, "记录已不存在")

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
