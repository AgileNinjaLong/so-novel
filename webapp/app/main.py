"""FastAPI 应用入口：认证、任务、来源切换、后台管理。"""

from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import auth, store, validity
from .config import settings
from .plugins import build_plugins, default_source, describe_plugin
from .plugins.base import Plugin
from .scheduler import EnqueueError, Scheduler, SwitchError
from .security import hash_password, unique_nanoid

STATIC_DIR = Path(__file__).resolve().parent / "static"

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    store.purge_expired_sessions()
    # 旧版本曾把小说长期保存在 data/library；新模型不保留任何成品文件
    import shutil

    shutil.rmtree(settings.data_dir / "library", ignore_errors=True)
    plugins: dict[str, Plugin] = build_plugins()
    scheduler = Scheduler(plugins, default_source(plugins))
    scheduler.start()
    state["plugins"] = plugins
    state["scheduler"] = scheduler
    print(f"[auth] {auth.ensure_admin()}")
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title="小说下载 WebUI", lifespan=lifespan, docs_url=None, redoc_url=None)

PAGE_HTML = {
    "/": "index.html",
    "/login": "login.html",
    "/register": "register.html",
    "/admin": "admin.html",
}


@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path

    # 公开资源
    if path.startswith("/static/") or path in {"/healthz", "/favicon.ico"}:
        return await call_next(request)
    if path in {"/login", "/register"}:
        if auth.current_user(request) is not None:
            return RedirectResponse("/", status_code=303)
        return await call_next(request)
    if path in {"/api/auth/login", "/api/auth/register", "/api/auth/key-info", "/api/meta"}:
        return await call_next(request)

    user = auth.current_user(request)
    if user is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    request.state.user = user
    return await call_next(request)


# ---------------- 认证 ----------------


def _set_session(response: JSONResponse, token: str, max_age: int) -> JSONResponse:
    secure = settings.cookie_secure
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return response


@app.get("/api/auth/me")
async def api_me(request: Request):
    user = auth.require_user(request)
    return {"user": auth.user_public(user)}


@app.post("/api/auth/register")
async def api_register(request: Request, payload: dict[str, Any] = Body(...)):
    key = str(payload.get("key") or payload.get("invite_key") or "").strip()
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    if not key:
        raise HTTPException(status_code=400, detail="请填写注册密钥")
    ip = auth.client_ip(request)
    # 只在真正兑换时校验（redeem_key 内部会给出具体原因），避免被「密钥查询」的限流误伤
    user = await run_in_threadpool(auth.redeem_key, key, username, password, ip=ip)
    token, ttl = auth.issue_session(user, request)
    return _set_session(
        JSONResponse({"user": auth.user_public(user)}, status_code=201), token, ttl
    )


@app.get("/api/auth/key-info")
async def api_key_info(request: Request, key: str):
    """注册页先查询密钥：一钥一账号，直接返回对应的账号密码。"""
    return await run_in_threadpool(
        auth.key_public_info, key, ip=auth.client_ip(request)
    )


@app.post("/api/auth/login")
async def api_login(request: Request, payload: dict[str, Any] = Body(...)):
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    user = await run_in_threadpool(
        auth.authenticate, username, password, ip=auth.client_ip(request)
    )
    token, ttl = auth.issue_session(user, request)
    return _set_session(JSONResponse({"user": auth.user_public(user)}), token, ttl)


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        from .security import hash_token

        store.delete_session(hash_token(token))
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


# ---------------- 元信息 ----------------


@app.get("/api/meta")
async def api_meta(request: Request):
    plugins: dict[str, Plugin] = state["plugins"]
    user = auth.current_user(request)
    key_stats = store.invite_key_stats()
    return {
        "app": {
            "active_source": store.active_source(default_source(plugins)),
            "pending_switch": store.pending_switch(),
            "poll_ms": settings.poll_interval_ms,
            "registration_open": key_stats.get("unused", 0) > 0,
            "unused_keys": key_stats.get("unused", 0),
            "file_ttl_min": settings.file_ttl_min,
            "cookie_secure": settings.cookie_secure,
        },
        "user": auth.user_public(user) if user else None,
        "plugins": [describe_plugin(p) for p in plugins.values()],
    }


@app.get("/api/state")
async def api_state(request: Request):
    scheduler: Scheduler = state["scheduler"]
    viewer = request.state.user
    return scheduler.snapshot(viewer)


# ---------------- 来源切换 ----------------


@app.post("/api/source")
async def api_switch_source(request: Request, payload: dict[str, Any] = Body(...)):
    auth.require_active_user(request)
    scheduler: Scheduler = state["scheduler"]
    source = str(payload.get("source") or "").strip()
    mode = str(payload.get("mode") or "after_current").strip()
    try:
        result = scheduler.request_switch(source, mode)
    except SwitchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


# ---------------- 搜索 ----------------


@app.get("/api/search")
async def api_search(request: Request, q: str, source: str | None = None):
    auth.require_active_user(request)
    plugins: dict[str, Plugin] = state["plugins"]
    scheduler: Scheduler = state["scheduler"]
    snapshot = scheduler.snapshot(request.state.user)
    target = source or snapshot["active_source"]
    if target != snapshot["active_source"]:
        raise HTTPException(status_code=409, detail="只能搜索当前启用的来源，请先切换来源")
    plugin = plugins.get(target)
    if plugin is None:
        raise HTTPException(status_code=400, detail="未知来源")
    if not plugin.capabilities.search:
        raise HTTPException(
            status_code=400,
            detail=f"「{plugin.name}」不支持按书名搜索：{plugin.capabilities.input_hint}",
        )
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入书名")
    try:
        items = await run_in_threadpool(plugin.search, query)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"搜索失败：{exc}")
    return {
        "source": target,
        "items": [
            {
                "title": item.title,
                "author": item.author,
                "book_ref": item.book_ref,
                "extra": item.extra,
            }
            for item in items
        ],
    }


# ---------------- 任务 ----------------


@app.post("/api/tasks")
async def api_create_task(request: Request, payload: dict[str, Any] = Body(...)):
    user = auth.require_active_user(request)
    scheduler: Scheduler = state["scheduler"]
    source = str(payload.get("source") or "").strip()
    title = str(payload.get("title") or "").strip()
    book_ref = str(payload.get("book_ref") or "").strip()
    fmt = str(payload.get("fmt") or "").strip()
    if not source or not book_ref or not fmt:
        raise HTTPException(status_code=400, detail="source / book_ref / fmt 不能为空")
    try:
        result = scheduler.enqueue(
            source=source,
            user_id=user["id"],
            user_name=user["username"],
            title=title or book_ref,
            book_ref=book_ref,
            fmt=fmt,
        )
    except EnqueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse(result, status_code=201)


@app.get("/api/tasks")
async def api_list_tasks(request: Request):
    return state["scheduler"].snapshot(request.state.user)


@app.get("/api/tasks/{task_id}")
async def api_get_task(request: Request, task_id: str):
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="无权查看该任务")
    return task


@app.delete("/api/tasks/{task_id}")
async def api_cancel_task(request: Request, task_id: str):
    """删除单条任务：排队/运行中会先取消，待接收会丢弃文件，已结束直接删记录。"""
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能删除自己的任务")
    try:
        return state["scheduler"].remove_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.post("/api/tasks/bulk-delete")
async def api_bulk_delete_tasks(request: Request, payload: dict[str, Any] = Body(...)):
    """批量删除任务记录（普通用户只能删自己的）。"""
    user = request.state.user
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="请提供要删除的任务 id 列表")
    if len(ids) > 200:
        raise HTTPException(status_code=400, detail="一次最多删除 200 条")
    owner = None if user["role"] == store.ROLE_ADMIN else user["id"]
    return state["scheduler"].remove_tasks([str(i) for i in ids], user_id=owner)


@app.get("/api/tasks/{task_id}/download")
async def api_download(request: Request, task_id: str):
    """把临时文件流式传给用户浏览器。

    注意：**不会**在响应结束时自动删除文件。浏览器无法告知服务端「用户是否真的保存成功」，
    因此删除动作由前端在完整拿到文件后调用 `/ack` 触发；未 ack 的文件按 TTL 自动清理。
    """
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能接收自己的文件")
    if task["status"] != store.STATUS_READY:
        raise HTTPException(
            status_code=409,
            detail="文件不在待接收状态（可能已接收、已过期或仍在下载）",
        )

    scheduler: Scheduler = state["scheduler"]
    path = scheduler.deliverable_path(task_id)
    if path is None or not path.is_file():
        store.mark_expired(task_id, "临时文件已不存在，请重新下载")
        raise HTTPException(status_code=410, detail="临时文件已失效，请重新发起下载")

    size = path.stat().st_size
    filename = path.name
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    # ASCII 回退文件名 + RFC 5987 的 UTF-8 文件名
    ascii_name = "".join(c if ord(c) < 128 and c not in '"\\' else "_" for c in filename)
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )

    def iter_file():
        with open(path, "rb") as fp:
            while True:
                chunk = fp.read(256 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=media_type,
        headers={"Content-Disposition": disposition, "Content-Length": str(size)},
    )


@app.post("/api/tasks/{task_id}/ack")
async def api_ack_delivery(request: Request, task_id: str):
    """由前端在文件完整保存到本机后调用：立即删除服务器上的临时文件。"""
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能确认接收自己的文件")
    if task["status"] != store.STATUS_READY:
        raise HTTPException(status_code=409, detail="文件不在待接收状态")
    scheduler: Scheduler = state["scheduler"]
    scheduler.complete_delivery(task_id)
    return {"ok": True, "deleted": True}


@app.post("/api/tasks/{task_id}/pause")
async def api_pause_task(request: Request, task_id: str):
    """暂停：终止任务并丢弃进度；之后只能「重新下载」（重新排队）。"""
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能暂停自己的任务")
    try:
        return state["scheduler"].pause(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.post("/api/tasks/{task_id}/retry")
async def api_retry_task(request: Request, task_id: str):
    """按原参数重新排队（文件已被接收或过期后使用）。"""
    user = auth.require_active_user(request)
    old = store.get_task(task_id)
    if old is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if old["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能重试自己的任务")
    scheduler: Scheduler = state["scheduler"]
    try:
        result = scheduler.enqueue(
            source=old["source"],
            user_id=user["id"],
            user_name=user["username"],
            title=old["title"],
            book_ref=old["book_ref"],
            fmt=old["fmt"],
        )
    except EnqueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse(result, status_code=201)


@app.post("/api/cleanup")
async def api_cleanup(request: Request, payload: dict[str, Any] | None = Body(default=None)):
    auth.require_admin(request)
    scheduler: Scheduler = state["scheduler"]
    statuses = (store.STATUS_FAILED, store.STATUS_CANCELED, store.STATUS_EXPIRED)
    if payload and payload.get("include_delivered"):
        statuses = statuses + (store.STATUS_DELIVERED,)
    return scheduler.cleanup_finished(statuses)


# ---------------- 后台管理 ----------------


@app.get("/api/admin/overview")
async def api_admin_overview(request: Request):
    auth.require_admin(request)
    scheduler: Scheduler = state["scheduler"]
    keys = store.list_invite_keys(limit=50)
    return {
        "users": [_admin_user_view(u) for u in store.list_users()],
        "user_count": store.count_users(),
        "task_counts": store.task_counts(),
        "active_source": store.active_source(),
        "queue_length": len(store.queued_tasks()),
        "grant_presets": list(validity.GRANT_PRESETS),
        "max_days": validity.MAX_DAYS,
        # 只回传最近 50 把，避免后台页面无限增长
        "keys": [_key_view(k) for k in keys],
        "key_total": len(store.list_invite_keys(limit=1000)),
        "key_stats": store.invite_key_stats(),
        "file_ttl_min": settings.file_ttl_min,
        "storage_mode": "stream-and-delete",
        "tasks": scheduler.snapshot(request.state.user)["tasks"],
    }


@app.get("/api/admin/keys")
async def api_admin_keys(request: Request):
    auth.require_admin(request)
    return {
        "keys": [_key_view(k) for k in store.list_invite_keys()],
        "stats": store.invite_key_stats(),
        "presets": list(validity.GRANT_PRESETS),
    }


@app.post("/api/admin/keys")
async def api_admin_create_keys(request: Request, payload: dict[str, Any] = Body(...)):
    admin = auth.require_admin(request)
    days_raw = payload.get("days")
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="days 必须是整数")
    try:
        count = int(payload.get("count") or 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="count 必须是整数")
    created = await run_in_threadpool(
        auth.generate_invite_keys,
        days=days,
        count=count,
        note=str(payload.get("note") or ""),
        created_by=admin["username"],
    )
    return {"keys": [_key_view(k) for k in created]}


@app.delete("/api/admin/keys/{key_id}")
async def api_admin_revoke_key(request: Request, key_id: str, hard: bool = False):
    auth.require_admin(request)
    row = store.get_invite_key(key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="密钥不存在")
    if hard:
        store.delete_invite_key(key_id)
        return {"deleted": True}
    if not store.revoke_invite_key(key_id):
        raise HTTPException(status_code=409, detail="只有未使用的密钥可以撤销")
    return {"revoked": True}


@app.post("/api/admin/users/{user_id}/password")
async def api_admin_reset_password(request: Request, user_id: str):
    auth.require_admin(request)
    target = store.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    from .security import nanoid

    new_password = nanoid(12, "abcdefghjkmnpqrstuvwxyz23456789")
    store.update_user(user_id, password_hash=hash_password(new_password))
    store.delete_user_sessions(user_id)
    return {"user": _admin_user_view(store.get_user(user_id) or target), "password": new_password}


@app.post("/api/admin/users/{user_id}/grant")
async def api_admin_grant(request: Request, user_id: str, payload: dict[str, Any] = Body(...)):
    auth.require_admin(request)
    target = store.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    raw_days = payload.get("days")
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="days 必须是整数")
    if days not in validity.GRANT_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"days 只能是 {'/'.join(str(d) for d in validity.GRANT_PRESETS)}",
        )
    fields = validity.grant(target, days)
    store.update_user(user_id, **fields)
    return {"user": _admin_user_view(store.get_user(user_id) or target)}


@app.post("/api/admin/users/{user_id}/status")
async def api_admin_status(request: Request, user_id: str, payload: dict[str, Any] = Body(...)):
    admin = auth.require_admin(request)
    target = store.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    status = str(payload.get("status") or "")
    if status not in {store.USER_ACTIVE, store.USER_BANNED}:
        raise HTTPException(status_code=400, detail="status 只能是 active/banned")
    if target["id"] == admin["id"] and status == store.USER_BANNED:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    store.update_user(user_id, status=status)
    if status == store.USER_BANNED:
        store.delete_user_sessions(user_id)
    return {"user": _admin_user_view(store.get_user(user_id) or target)}


@app.delete("/api/admin/users/{user_id}")
async def api_admin_delete_user(request: Request, user_id: str):
    admin = auth.require_admin(request)
    target = store.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target["id"] == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己")
    store.delete_user(user_id)
    return {"ok": True}


@app.post("/api/admin/tasks/bulk-delete")
async def api_admin_bulk_delete(request: Request, payload: dict[str, Any] = Body(...)):
    auth.require_admin(request)
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="请提供要删除的任务 id 列表")
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="一次最多删除 500 条")
    return state["scheduler"].remove_tasks([str(i) for i in ids])


@app.delete("/api/admin/tasks/{task_id}")
async def api_admin_delete_task(request: Request, task_id: str):
    auth.require_admin(request)
    try:
        return state["scheduler"].remove_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.post("/api/admin/tasks/{task_id}/cancel")
async def api_admin_cancel_task(request: Request, task_id: str):
    auth.require_admin(request)
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state["scheduler"].cancel(task_id)


def _key_view(row: dict[str, Any]) -> dict[str, Any]:
    bound = bool(row.get("username"))
    return {
        "id": row["id"],
        "key": row["key"],
        "mode": row["mode"],
        "days": row["days"],
        "permanent": bool(row["permanent"]),
        "days_text": "永久" if row["permanent"] else f"{row['days']} 天",
        "bound": bound,
        "username": row.get("username") or "",
        "password": row.get("password_plain") or "",
        "status": row["status"],
        "note": row.get("note") or "",
        "created_at": row["created_at"],
        "created_by": row.get("created_by") or "",
        "used_at": row.get("used_at"),
        "used_by_name": row.get("used_by_name") or "",
    }


def _admin_user_view(user: dict[str, Any]) -> dict[str, Any]:
    view = auth.user_public(user)
    view["task_count"] = store.count_tasks_for_user(user["id"])
    return view


# ---------------- 页面 ----------------


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """老浏览器会直接请求 /favicon.ico，返回站点图标避免 404。"""
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login")
async def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/register")
async def register_page():
    return FileResponse(STATIC_DIR / "register.html")


@app.get("/admin")
async def admin_page(request: Request):
    if request.state.user.get("role") != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return FileResponse(STATIC_DIR / "admin.html")
