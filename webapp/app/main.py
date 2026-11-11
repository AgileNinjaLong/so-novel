"""FastAPI 应用入口：认证、任务、来源切换、后台管理。"""

from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import auth, store, validity
from .config import settings
from .plugins import build_plugins, default_source, describe_plugin
from .plugins.base import Plugin
from .scheduler import EnqueueError, Scheduler, SwitchError
from .security import new_registration_key, unique_nanoid

STATIC_DIR = Path(__file__).resolve().parent / "static"

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    store.purge_expired_sessions()
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
    if path.startswith("/static/") or path == "/healthz":
        return await call_next(request)
    if path in {"/login", "/register"}:
        if auth.current_user(request) is not None:
            return RedirectResponse("/", status_code=303)
        return await call_next(request)
    if path in {"/api/auth/login", "/api/auth/register", "/api/meta"}:
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
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    invite = str(payload.get("invite_key") or "")
    if not store.registration_key():
        raise HTTPException(status_code=403, detail="管理员尚未生成注册密钥，当前无法注册")
    user = await run_in_threadpool(
        auth.register_user, username, password, invite, ip=auth.client_ip(request)
    )
    token, ttl = auth.issue_session(user, request)
    return _set_session(
        JSONResponse({"user": auth.user_public(user)}, status_code=201), token, ttl
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
    scheduler: Scheduler = state["scheduler"]
    user = auth.current_user(request)
    return {
        "app": {
            "active_source": store.active_source(default_source(plugins)),
            "pending_switch": store.pending_switch(),
            "poll_ms": settings.poll_interval_ms,
            "registration_open": bool(store.registration_key()),
            "password_required": True,
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
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能取消自己的任务")
    try:
        return state["scheduler"].cancel(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.get("/api/tasks/{task_id}/download")
async def api_download(request: Request, task_id: str):
    user = request.state.user
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user["id"] and user["role"] != store.ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只能下载自己的文件")
    if task["status"] != store.STATUS_SUCCESS or not task["file_path"]:
        raise HTTPException(status_code=409, detail="文件尚未就绪")
    path = Path(task["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail="文件已不存在")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/api/cleanup")
async def api_cleanup(request: Request, payload: dict[str, Any] | None = Body(default=None)):
    auth.require_admin(request)
    scheduler: Scheduler = state["scheduler"]
    statuses = (store.STATUS_FAILED, store.STATUS_CANCELED)
    if payload and payload.get("include_success"):
        statuses = statuses + (store.STATUS_SUCCESS,)
    return scheduler.cleanup_finished(statuses)


# ---------------- 后台管理 ----------------


@app.get("/api/admin/overview")
async def api_admin_overview(request: Request):
    auth.require_admin(request)
    key = store.registration_key()
    scheduler: Scheduler = state["scheduler"]
    return {
        "registration_key": key,
        "registration_key_created_at": store.get_setting("registration_key_created_at"),
        "users": [_admin_user_view(u) for u in store.list_users()],
        "user_count": store.count_users(),
        "task_counts": store.task_counts(),
        "active_source": store.active_source(),
        "queue_length": len(store.queued_tasks()),
        "grant_presets": list(validity.GRANT_PRESETS),
        "max_days": validity.MAX_DAYS,
        "tasks": scheduler.snapshot(request.state.user)["tasks"],
    }


@app.post("/api/admin/key")
async def api_admin_rotate_key(request: Request):
    admin = auth.require_admin(request)

    def exists(key: str) -> bool:
        return store.registration_key() == key

    key = unique_nanoid(21, exists)
    store.set_registration_key(key, created_by=admin["username"])
    return {
        "registration_key": key,
        "created_at": store.get_setting("registration_key_created_at"),
    }


@app.delete("/api/admin/key")
async def api_admin_clear_key(request: Request):
    auth.require_admin(request)
    store.delete_setting("registration_key")
    store.delete_setting("registration_key_created_at")
    store.delete_setting("registration_key_created_by")
    return {"registration_key": ""}


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


@app.post("/api/admin/tasks/{task_id}/cancel")
async def api_admin_cancel_task(request: Request, task_id: str):
    auth.require_admin(request)
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state["scheduler"].cancel(task_id)


def _admin_user_view(user: dict[str, Any]) -> dict[str, Any]:
    view = auth.user_public(user)
    view["task_count"] = len(
        [t for t in store.list_tasks(limit=1000) if t.get("user_id") == user["id"]]
    )
    return view


# ---------------- 页面 ----------------


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
