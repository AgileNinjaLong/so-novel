"""认证与会话：注册密钥校验、登录、Cookie 会话、管理员引导、限流。"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

from fastapi import HTTPException, Request

from . import store, validity
from .config import settings
from .security import (
    constant_time_eq,
    hash_password,
    hash_token,
    new_entity_id,
    new_session_token,
    unique_nanoid,
    verify_password,
)

SESSION_COOKIE = "novel_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]{3,24}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128

# ---- 简易登录/注册限流（内存，单实例足够） ----
_RATE_LOCK = threading.Lock()
_ATTEMPTS: dict[str, list[float]] = {}
_RATE_WINDOW = 60.0
_RATE_LIMIT = 8


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def _check_rate(key: str) -> None:
    now = time.time()
    with _RATE_LOCK:
        attempts = [t for t in _ATTEMPTS.get(key, []) if now - t < _RATE_WINDOW]
        if len(attempts) >= _RATE_LIMIT:
            raise HTTPException(status_code=429, detail="尝试过于频繁，请稍后再试")
        attempts.append(now)
        _ATTEMPTS[key] = attempts


def _clear_rate(key: str) -> None:
    with _RATE_LOCK:
        _ATTEMPTS.pop(key, None)


# ---------------- 管理员引导 ----------------


def ensure_admin() -> str:
    """按环境变量创建/同步管理员账号，返回提示信息。"""
    username = (os.environ.get("ADMIN_USERNAME") or "").strip()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if not username or not password:
        return "未设置 ADMIN_USERNAME / ADMIN_PASSWORD，后台管理不可用"

    if not USERNAME_RE.match(username):
        return f"ADMIN_USERNAME 不合法（{USERNAME_RE.pattern}）"
    if len(password) < PASSWORD_MIN:
        return f"ADMIN_PASSWORD 至少 {PASSWORD_MIN} 位"

    existing = store.get_user_by_username(username)
    if existing is None:
        store.create_user(
            user_id=unique_nanoid(16, lambda _id: store.get_user(_id) is not None),
            username=username,
            password_hash=hash_password(password),
            role=store.ROLE_ADMIN,
            created_by="env",
            permanent=True,
        )
        return f"已创建管理员账号 {username}"

    fields: dict[str, Any] = {"role": store.ROLE_ADMIN, "status": store.USER_ACTIVE}
    if not verify_password(password, existing["password_hash"]):
        fields["password_hash"] = hash_password(password)
        store.delete_user_sessions(existing["id"])
    if not existing["permanent"]:
        fields["permanent"] = 1
        fields["expires_at"] = None
    store.update_user(existing["id"], **fields)
    return f"已同步管理员账号 {username}"


# ---------------- 注册 ----------------


def register_user(
    username: str, password: str, invite_key: str, *, ip: str = ""
) -> dict[str, Any]:
    expected = store.registration_key()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="管理员尚未生成注册密钥，当前无法注册",
        )
    _check_rate(f"register:{ip}")
    if not constant_time_eq(invite_key.strip(), expected):
        raise HTTPException(status_code=403, detail="注册密钥不正确")

    username = username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="用户名需 3-24 位，可用中英文、数字、下划线、短横线",
        )
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"密码长度需 {PASSWORD_MIN}-{PASSWORD_MAX} 位",
        )
    if store.username_exists(username):
        raise HTTPException(status_code=409, detail="用户名已被占用")

    # 默认开源时长（0 天 = 需管理员开通）
    default_days = int(os.environ.get("WEBAPP_DEFAULT_GRANT_DAYS", "0") or 0)
    expires_at = None
    permanent = False
    if default_days > 0:
        granted = validity.grant({}, default_days)
        permanent = bool(granted["permanent"])
        expires_at = granted["expires_at"]

    user = store.create_user(
        user_id=unique_nanoid(16, lambda _id: store.get_user(_id) is not None),
        username=username,
        password_hash=hash_password(password),
        role=store.ROLE_USER,
        created_by="register",
        permanent=permanent,
        expires_at=expires_at,
    )
    _clear_rate(f"register:{ip}")
    return user


# ---------------- 登录 ----------------


def authenticate(username: str, password: str, *, ip: str = "") -> dict[str, Any]:
    _check_rate(f"login:{ip}:{username.lower()}")
    user = store.get_user_by_username(username.strip())
    if user is None or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user["status"] != store.USER_ACTIVE:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    _clear_rate(f"login:{ip}:{username.lower()}")
    store.update_user(user["id"], last_login_at=store._now())
    return user


# ---------------- 会话 ----------------


def issue_session(user: dict[str, Any], request: Request) -> tuple[str, int]:
    token = new_session_token()
    store.create_session(
        token_hash=hash_token(token),
        user_id=user["id"],
        expires_at=validity.fmt_ts(validity.now_ts() + SESSION_TTL_SECONDS),
        ip=_client_ip(request),
        ua=request.headers.get("user-agent", ""),
    )
    return token, SESSION_TTL_SECONDS


def current_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = store.get_session(hash_token(token))
    if session is None:
        return None
    return store.get_user(session["user_id"])


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if user["status"] != store.USER_ACTIVE:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return user


def require_active_user(request: Request) -> dict[str, Any]:
    """需要有下载权限（未过期、未被禁用）。"""
    user = require_user(request)
    if not validity.is_active(user):
        raise HTTPException(
            status_code=403,
            detail="账号未开通或已过期，请联系管理员续期",
        )
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = require_user(request)
    if user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def client_ip(request: Request) -> str:
    return _client_ip(request)


def user_public(user: dict[str, Any]) -> dict[str, Any]:
    """返回给前端的用户信息（不含口令哈希）。"""
    info = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "status": user["status"],
        "created_at": user["created_at"],
        "last_login_at": user.get("last_login_at"),
    }
    info.update(validity.status_fields(user))
    return info
