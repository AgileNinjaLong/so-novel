"""FastAPI 应用入口。"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import store
from .config import settings
from .plugins import build_plugins, default_source, describe_plugin
from .plugins.base import Plugin
from .scheduler import EnqueueError, Scheduler, SwitchError

STATIC_DIR = Path(__file__).resolve().parent / "static"
COOKIE_NAME = "webapp_auth"
USER_COOKIE = "webapp_user"

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    plugins: dict[str, Plugin] = build_plugins()
    scheduler = Scheduler(plugins, default_source(plugins))
    scheduler.start()
    state["plugins"] = plugins
    state["scheduler"] = scheduler
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title="So-Novel 多源下载 WebUI", lifespan=lifespan, docs_url=None, redoc_url=None)


# ---------------- 认证（可选，设置 WEBAPP_PASSWORD 后生效） -------------


def _auth_token() -> str | None:
    if not settings.password:
        return None
    token = os.environ.get("WEBAPP_AUTH_TOKEN")
    if not token:
        token = secrets.token_urlsafe(24)
        os.environ["WEBAPP_AUTH_TOKEN"] = token
    return token


def _is_authenticated(request: Request) -> bool:
    token = _auth_token()
    if token is None:
        return True
    return request.cookies.get(COOKIE_NAME) == token


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    public = (
        not settings.password
        or path == "/api/login"
        or path == "/api/meta"
        or path == "/healthz"
        or path.startswith("/static/")
        or path == "/login"
    )
    if not public and path.startswith("/api/") and not _is_authenticated(request):
        return JSONResponse(
            {"error": "unauthorized", "message": "需要登录"}, status_code=401
        )
    if not public and path == "/" and not _is_authenticated(request):
        return FileResponse(STATIC_DIR / "login.html")
    return await call_next(request)


@app.post("/api/login")
async def api_login(payload: dict[str, Any] = Body(...)):
    if not settings.password:
        return {"ok": True}
    if payload.get("password") != settings.password:
        raise HTTPException(status_code=403, detail="密码错误")
    token = _auth_token()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        COOKIE_NAME, token or "", httponly=True, samesite="lax", max_age=30 * 24 * 3600
    )
    return response


@app.post("/api/logout")
async def api_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------- 元信息 -------------


@app.get("/api/meta")
async def api_meta(request: Request):
    plugins: dict[str, Plugin] = state["plugins"]
    scheduler: Scheduler = state["scheduler"]
    snapshot = scheduler.snapshot()
    return {
        "app": {
            "password_required": bool(settings.password),
            "authenticated": _is_authenticated(request),
            "poll_ms": settings.poll_interval_ms,
            "active_source": snapshot["active_source"],
            "pending_switch": snapshot["pending_switch"],
        },
        "plugins": [describe_plugin(p) for p in plugins.values()],
    }


@app.get("/api/state")
async def api_state():
    scheduler: Scheduler = state["scheduler"]
    return scheduler.snapshot()


# ---------------- 来源切换 ----------------


@app.post("/api/source")
async def api_switch_source(payload: dict[str, Any] = Body(...)):
    scheduler: Scheduler = state["scheduler"]
    source = str(payload.get("source") or "").strip()
    mode = str(payload.get("mode") or "after_current").strip()
    try:
        result = scheduler.request_switch(source, mode)
    except SwitchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


# ---------------- 搜索 -------------


@app.get("/api/search")
async def api_search(q: str, source: str | None = None):
    plugins: dict[str, Plugin] = state["plugins"]
    scheduler: Scheduler = state["scheduler"]
    snapshot = scheduler.snapshot()
    target = source or snapshot["active_source"]
    if target != snapshot["active_source"]:
        raise HTTPException(
            status_code=409,
            detail="只能搜索当前启用的来源，请先切换来源",
        )
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
        # 搜索可能触发番茄服务首次启动（耗时数十秒），必须放到线程池里，避免阻塞事件循环
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


def _user_name(request: Request) -> str:
    raw = request.cookies.get(USER_COOKIE, "")
    try:
        name = unquote(raw).strip()[:24]
    except Exception:
        name = ""
    return name or "匿名"


@app.post("/api/tasks")
async def api_create_task(request: Request, payload: dict[str, Any] = Body(...)):
    scheduler: Scheduler = state["scheduler"]
    source = str(payload.get("source") or "").strip()
    title = str(payload.get("title") or "").strip()
    book_ref = str(payload.get("book_ref") or "").strip()
    fmt = str(payload.get("fmt") or "").strip()
    if not source or not book_ref or not fmt:
        raise HTTPException(status_code=400, detail="source / book_ref / fmt 不能为空")
    if not title:
        title = book_ref
    try:
        result = scheduler.enqueue(
            source=source,
            user_name=_user_name(request),
            title=title,
            book_ref=book_ref,
            fmt=fmt,
        )
    except EnqueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    response = JSONResponse(result, status_code=201)
    # Cookie 只能放 ASCII，昵称做 URL 编码
    response.set_cookie(
        USER_COOKIE, quote(_user_name(request), safe=""), max_age=30 * 24 * 3600, samesite="lax"
    )
    return response


@app.post("/api/me")
async def api_set_me(request: Request, payload: dict[str, Any] = Body(...)):
    name = str(payload.get("name") or "").strip()[:24] or "匿名"
    response = JSONResponse({"name": name})
    response.set_cookie(
        USER_COOKIE,
        quote(name, safe=""),
        max_age=30 * 24 * 3600,
        samesite="lax",
        httponly=False,
    )
    return response


@app.get("/api/tasks")
async def api_list_tasks():
    scheduler: Scheduler = state["scheduler"]
    return scheduler.snapshot()


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str):
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.delete("/api/tasks/{task_id}")
async def api_cancel_task(task_id: str):
    scheduler: Scheduler = state["scheduler"]
    try:
        return scheduler.cancel(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.post("/api/cleanup")
async def api_cleanup(payload: dict[str, Any] | None = Body(default=None)):
    scheduler: Scheduler = state["scheduler"]
    statuses = (store.STATUS_FAILED, store.STATUS_CANCELED)
    if payload and payload.get("include_success"):
        statuses = statuses + (store.STATUS_SUCCESS,)
    return scheduler.cleanup_finished(statuses)


@app.get("/api/tasks/{task_id}/download")
async def api_download(task_id: str):
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != store.STATUS_SUCCESS or not task["file_path"]:
        raise HTTPException(status_code=409, detail="文件尚未就绪")
    path = Path(task["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail="文件已不存在")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
    )


@app.get("/healthz")
async def healthz():
    scheduler: Scheduler = state["scheduler"]
    snapshot = scheduler.snapshot()
    return {"ok": True, "active_source": snapshot["active_source"]}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")
