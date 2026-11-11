"""认证与会话：注册密钥校验、登录、Cookie 会话、管理员引导、限流。"""

from __future__ import annotations

import os
import re
import threading
from typing import Any

from fastapi import HTTPException, Request

from . import store, throttle, validity
from .security import (
    hash_password,
    hash_token,
    new_session_token,
    unique_nanoid,
    verify_password,
)

SESSION_COOKIE = "novel_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]{3,24}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


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


# ---------------- 注册密钥（一钥一用户） ----------------

KEY_MODE_OPEN = "open"
KEY_MODE_BOUND = "bound"


def key_public_info(code: str, *, ip: str = "-") -> dict[str, Any]:
    """注册页/前台可查询的密钥信息（绑定型会直接给出预置账号密码）。"""
    throttle.check("keyinfo_ip", ip)
    row = store.get_invite_key_by_code(code.strip())
    if row is None:
        throttle.record_failure("keyinfo_ip", ip)
        return {"valid": False, "reason": "密钥不存在"}
    if row["status"] == "used":
        throttle.record_failure("keyinfo_ip", ip)
        # 已使用的密钥仍展示它绑定的账号，方便持有人/管理员确认
        return {
            "valid": False,
            "reason": "该密钥已被使用",
            "username": row.get("username") or "",
            "password": row.get("password_plain") or "",
            "used_at": row.get("used_at"),
            "used_by_name": row.get("used_by_name") or "",
        }
    if row["status"] == "revoked":
        throttle.record_failure("keyinfo_ip", ip)
        return {"valid": False, "reason": "该密钥已被管理员撤销"}
    throttle.clear("keyinfo_ip", ip)
    info = {
        "valid": True,
        "mode": row["mode"],
        "days": row["days"],
        "permanent": bool(row["permanent"]),
        "days_text": "永久" if row["permanent"] else f"{row['days']} 天",
        # 一钥一账号：无论是否已使用，都把对应账号密码展示出来
        "username": row.get("username") or "",
        "password": row.get("password_plain") or "",
    }
    return info


def redeem_key(
    code: str, username: str = "", password: str = "", *, ip: str = "-"
) -> dict[str, Any]:
    """用密钥激活一个账号；密钥只能用一次，账号密码由管理员预置。"""
    throttle.check("redeem_ip", ip)
    throttle.check("register_ip", ip)
    row = store.get_invite_key_by_code(code.strip())
    if row is None:
        throttle.record_failure("redeem_ip", ip)
        raise HTTPException(status_code=403, detail="注册密钥不存在")
    if row["status"] != "unused":
        throttle.record_failure("redeem_ip", ip)
        raise HTTPException(
            status_code=403,
            detail="该密钥已被使用或已撤销，请联系管理员重新获取",
        )

    if row["mode"] == KEY_MODE_BOUND or (row.get("username") and row.get("password_plain")):
        username = (row["username"] or "").strip()
        password = row["password_plain"] or ""
        if not username or not password:
            raise HTTPException(status_code=500, detail="密钥的账号数据不完整")
    else:
        # 兼容历史遗留的开放型密钥（新流程不再生成）
        username = username.strip()
        if not USERNAME_RE.match(username):
            throttle.record_failure("redeem_ip", ip)
            raise HTTPException(
                status_code=400,
                detail="用户名需 3-24 位，可用中英文、数字、下划线、短横线",
            )
        if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
            throttle.record_failure("redeem_ip", ip)
            raise HTTPException(
                status_code=400, detail=f"密码长度需 {PASSWORD_MIN}-{PASSWORD_MAX} 位"
            )

    if store.username_exists(username):
        throttle.record_failure("redeem_ip", ip)
        raise HTTPException(status_code=409, detail="该账号已存在，请联系管理员")

    permanent = bool(row["permanent"])
    expires_at = None
    if not permanent:
        expires_at = validity.fmt_ts(
            validity.now_ts() + max(0, int(row["days"])) * validity.SECONDS_PER_DAY
        )

    user = store.create_user(
        user_id=unique_nanoid(16, lambda _id: store.get_user(_id) is not None),
        username=username,
        password_hash=hash_password(password),
        role=store.ROLE_USER,
        created_by=f"key:{row['key']}",
        permanent=permanent,
        expires_at=expires_at,
    )
    store.mark_invite_key_used(row["id"], user["id"], username)
    throttle.clear("redeem_ip", ip)
    throttle.clear("register_ip", ip)
    return user


def _gen_username(exists: Any) -> str:
    from .security import nanoid

    for _ in range(20):
        candidate = "u" + nanoid(7, "abcdefghjkmnpqrstuvwxyz23456789")
        if not exists(candidate):
            return candidate
    raise HTTPException(status_code=500, detail="生成用户名失败")


def _gen_password() -> str:
    from .security import nanoid

    return nanoid(10, "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789")


def generate_invite_keys(
    *,
    days: int,
    count: int = 1,
    username: str = "",
    password: str = "",
    note: str = "",
    created_by: str = "",
) -> list[dict[str, Any]]:
    """管理员生成「一钥一账号」的密钥。

    - 填了用户名：必须同时给密码（或留空自动生成），且只能生成 1 把；
    - 用户名留空：按数量自动生成账号与密码，每把密钥对应不同账号。
    """
    if days not in validity.GRANT_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"days 只能是 {'/'.join(str(d) for d in validity.GRANT_PRESETS)}",
        )
    username = username.strip()
    if username:
        count = 1
        if not USERNAME_RE.match(username):
            raise HTTPException(
                status_code=400,
                detail="用户名需 3-24 位，可用中英文、数字、下划线、短横线",
            )
        if password and not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
            raise HTTPException(
                status_code=400, detail=f"密码需 {PASSWORD_MIN}-{PASSWORD_MAX} 位"
            )
        if store.username_exists(username):
            raise HTTPException(status_code=409, detail="该用户名已被占用")
    else:
        password = ""
    count = max(1, min(20, int(count)))

    permanent = days >= validity.PERMANENT_DAYS
    created: list[dict[str, Any]] = []
    for _ in range(count):
        uname = username or _gen_username(store.username_exists)
        pwd = password or _gen_password()
        code = unique_nanoid(21, store.invite_key_code_exists)
        key_id = unique_nanoid(16, lambda _id: store.get_invite_key(_id) is not None)
        created.append(
            store.create_invite_key(
                key_id=key_id,
                code=code,
                mode=KEY_MODE_BOUND,
                days=days,
                permanent=permanent,
                username=uname,
                password_plain=pwd,
                note=note,
                created_by=created_by,
            )
        )
    return created


# ---------------- 登录 ----------------


def authenticate(username: str, password: str, *, ip: str = "") -> dict[str, Any]:
    """登录：按账号与 IP 双重限流，失败计数持久化，防止撞库。"""
    username = username.strip()
    throttle.check("login_ip", ip or "-")
    throttle.check("login_user", username.lower())

    user = store.get_user_by_username(username)
    ok = user is not None and verify_password(password, user["password_hash"])
    if not ok or user is None:
        throttle.record_failure("login_ip", ip or "-")
        throttle.record_failure("login_user", username.lower())
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user["status"] != store.USER_ACTIVE:
        throttle.record_failure("login_user", username.lower())
        raise HTTPException(status_code=403, detail="账号已被禁用")

    throttle.clear("login_ip", ip or "-")
    throttle.clear("login_user", username.lower())
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
