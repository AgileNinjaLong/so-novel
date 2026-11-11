"""口令、令牌与「注册密钥」的生成。

密钥算法取自 GitHub 开源项目 **ai/nanoid**（MIT，https://github.com/ai/nanoid）：
它用密码学安全的随机字节 + 掩码取模生成 URL 安全短 ID，默认 21 个字符约 126 bit 熵，
碰撞概率极低；本项目在数据库上再加 UNIQUE 约束并在碰撞时重试，保证「不重复」。

口令用标准库 `hashlib.scrypt`（内存硬，抗 GPU 暴力破解），参数与盐随每次生成随机化，
存储格式：``scrypt$n$r$p$salt_b64$hash_b64``。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Callable
from urllib.parse import quote

# ai/nanoid 的 urlAlphabet（顺序与上游一致）
_URL_ALPHABET = (
    "_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)

# 注册密钥：21 字符 × 6 bit ≈ 126 bit 熵
REGISTRATION_KEY_SIZE = 21
# 会话令牌：43 字符 ≈ 258 bit 熵
SESSION_TOKEN_SIZE = 43
# 用户/任务等内部 ID
ENTITY_ID_SIZE = 16

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def nanoid(
    size: int = REGISTRATION_KEY_SIZE, alphabet: str = _URL_ALPHABET
) -> str:
    """ai/nanoid 的 Python 移植（掩码取模，避免取模偏差）。"""
    if size <= 0:
        raise ValueError("size 必须为正整数")
    if not alphabet or len(alphabet) > 255:
        raise ValueError("alphabet 长度必须在 1..255 之间")

    mask = (2 << (len(alphabet) - 1).bit_length() - 1) - 1
    step = max(1, int(1.6 * mask * size / len(alphabet)))

    out: list[str] = []
    while True:
        random_bytes = secrets.token_bytes(step)
        for index in range(step - 1, -1, -1):
            char = alphabet[random_bytes[index] & mask]
            if char:
                out.append(char)
                if len(out) == size:
                    return "".join(out)
        step = int(step * 1.1) + 1


def unique_nanoid(
    size: int = REGISTRATION_KEY_SIZE,
    exists: Callable[[str], bool] | None = None,
    attempts: int = 8,
) -> str:
    """生成一个数据库中不存在的 ID；碰撞时换一个（nanoid 本身已避免碰撞）。"""
    for _ in range(attempts):
        candidate = nanoid(size)
        if exists is None or not exists(candidate):
            return candidate
    raise RuntimeError("连续生成重复 ID，随机源可能异常")


def new_registration_key() -> str:
    return nanoid(REGISTRATION_KEY_SIZE)


def new_session_token() -> str:
    return nanoid(SESSION_TOKEN_SIZE)


def new_entity_id() -> str:
    return nanoid(ENTITY_ID_SIZE)


# ---------------- 口令 ----------------------------


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except Exception:
        return False
    return hmac.compare_digest(digest, expected)


def hash_token(token: str) -> str:
    """会话令牌只把 sha256 落到数据库，泄露数据库也无法直接复用 cookie。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def quote_cookie(value: str) -> str:
    return quote(value, safe="")
