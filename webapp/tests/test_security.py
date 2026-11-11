"""单元测试：密钥生成（ai/nanoid 移植）、口令哈希、令牌。

运行：python tests/test_security.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.security import (  # noqa: E402
    REGISTRATION_KEY_SIZE,
    SESSION_TOKEN_SIZE,
    hash_password,
    hash_token,
    nanoid,
    new_registration_key,
    new_session_token,
    unique_nanoid,
    verify_password,
    _URL_ALPHABET,
)

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def main() -> int:
    print("[1] nanoid 基本性质")
    key = new_registration_key()
    check(len(key) == REGISTRATION_KEY_SIZE, f"注册密钥长度 = {REGISTRATION_KEY_SIZE}")
    check(all(c in _URL_ALPHABET for c in key), "只使用 URL 安全字母表")
    token = new_session_token()
    check(len(token) == SESSION_TOKEN_SIZE, f"会话令牌长度 = {SESSION_TOKEN_SIZE}")

    print("[2] 大量生成不重复（2 万次）")
    samples = {nanoid(21) for _ in range(20000)}
    check(len(samples) == 20000, "2 万个密钥无重复")

    print("[3] 自定义长度")
    for size in (8, 12, 16, 32, 64):
        value = nanoid(size)
        check(len(value) == size, f"nanoid({size}) 长度正确")

    print("[4] unique_nanoid 碰撞重试")
    conflict = "AAAAAAAAAAAAAAAAAAAAA"
    calls = {"n": 0}

    def exists(candidate: str) -> bool:
        calls["n"] += 1
        return calls["n"] == 1  # 第一次故意判为已存在

    value = unique_nanoid(21, exists)
    check(len(value) == 21, "碰撞后重新生成成功")
    check(calls["n"] >= 2, "确实重试了")

    print("[5] 口令哈希（scrypt）")
    stored = hash_password("correct horse battery staple")
    check(stored.startswith("scrypt$"), "哈希带算法标识")
    check(verify_password("correct horse battery staple", stored), "正确口令通过")
    check(not verify_password("wrong password", stored), "错误口令拒绝")
    check(not verify_password("", stored), "空口令拒绝")
    check(hash_password("same") != hash_password("same"), "相同口令因随机盐得到不同哈希")
    check(not verify_password("x", "garbage"), "损坏的哈希不会抛异常而是拒绝")

    print("[6] 令牌哈希")
    digest1 = hash_token("abc")
    check(len(digest1) == 64, "sha256 十六进制长度 64")
    check(digest1 != hash_token("abd"), "不同令牌得到不同哈希")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
