"""SQLite 持久化：用户、会话、任务、全局设置。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterable

from .config import settings

# 任务状态：
# queued(排队中) -> running(下载中) -> ready(待接收) -> delivered(已交付)
# paused(已暂停，只能重新下载) / failed / canceled / expired(未接收已清理)
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_READY = "ready"
STATUS_DELIVERED = "delivered"
STATUS_SUCCESS = "delivered"  # 兼容旧代码/测试里的命名
STATUS_PAUSED = "paused"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"
STATUS_EXPIRED = "expired"

ROLE_USER = "user"
ROLE_ADMIN = "admin"

USER_ACTIVE = "active"
USER_BANNED = "banned"

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def init_db() -> None:
    with _lock:
        conn = _connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                permanent INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ip TEXT,
                ua TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                user_name TEXT NOT NULL DEFAULT '匿名',
                title TEXT NOT NULL,
                book_ref TEXT NOT NULL,
                fmt TEXT NOT NULL,
                status TEXT NOT NULL,
                seq INTEGER NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                chapters_done INTEGER NOT NULL DEFAULT 0,
                chapters_total INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                file_path TEXT,
                error TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                delivered_at TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status_seq ON tasks(status, seq);

            CREATE TABLE IF NOT EXISTS invite_keys (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL DEFAULT 'bound',
                days INTEGER NOT NULL DEFAULT 0,
                permanent INTEGER NOT NULL DEFAULT 0,
                username TEXT,
                password_plain TEXT,
                status TEXT NOT NULL DEFAULT 'unused',
                note TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT,
                used_at TEXT,
                used_by TEXT,
                used_by_name TEXT
            );

            CREATE TABLE IF NOT EXISTS throttle (
                scope_key TEXT PRIMARY KEY,
                fail_count INTEGER NOT NULL DEFAULT 0,
                window_start REAL NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0
            );
            """
        )
        # 兼容旧库：tasks 表可能没有 user_id / user_name
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "user_id" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        if "user_name" not in columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN user_name TEXT NOT NULL DEFAULT '匿名'"
            )
        if "size_bytes" not in columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0"
            )
        if "delivered_at" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN delivered_at TEXT")
        # 旧版本把完成状态记为 success 且文件常驻服务器；新模型文件不落库，
        # 因此历史记录统一视为「已交付」，并清掉文件路径。
        conn.execute("UPDATE tasks SET status = 'delivered' WHERE status = 'success'")
        conn.execute("UPDATE tasks SET file_path = NULL WHERE status != 'ready'")
        conn.commit()


# ---------------- 设置 ----------------


def get_setting(key: str, default: str | None = None) -> str | None:
    with _lock:
        row = _connection().execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def delete_setting(key: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()


def active_source(default: str = "sonovel") -> str:
    return get_setting("active_source", default) or default


def pending_switch() -> dict[str, Any] | None:
    raw = get_setting("pending_switch", "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def set_pending_switch(value: dict[str, Any] | None) -> None:
    if value is None:
        delete_setting("pending_switch")
    else:
        set_setting("pending_switch", json.dumps(value, ensure_ascii=False))


def registration_key() -> str:
    """旧版「全局注册密钥」：仅为兼容历史数据保留读取，新流程已改为 invite_keys。"""
    return get_setting("registration_key", "") or ""


# ---------------- 用户 ----------------


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def create_user(
    *,
    user_id: str,
    username: str,
    password_hash: str,
    role: str = ROLE_USER,
    created_by: str = "",
    permanent: bool = False,
    expires_at: str | None = None,
) -> dict[str, Any]:
    with _lock:
        conn = _connection()
        conn.execute(
            """
            INSERT INTO users(id, username, password_hash, role, status, permanent,
                              expires_at, created_at, created_by)
            VALUES(?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                password_hash,
                role,
                1 if permanent else 0,
                expires_at,
                _now(),
                created_by or None,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row)


def get_user(user_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return _row_to_user(row) if row else None


def username_exists(username: str) -> bool:
    return get_user_by_username(username) is not None


def list_users() -> list[dict[str, Any]]:
    with _lock:
        rows = _connection().execute(
            "SELECT * FROM users ORDER BY role ASC, created_at DESC"
        ).fetchall()
    return [_row_to_user(r) for r in rows]


def count_users() -> int:
    with _lock:
        return int(
            _connection()
            .execute("SELECT COUNT(*) AS c FROM users")
            .fetchone()["c"]
        )


def update_user(user_id: str, **fields: Any) -> None:
    allowed = {
        "password_hash",
        "status",
        "permanent",
        "expires_at",
        "role",
        "last_login_at",
        "username",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"不允许更新的字段: {sorted(unknown)}")
    if not fields:
        return
    columns = ", ".join(f"{k} = ?" for k in fields)
    with _lock:
        conn = _connection()
        conn.execute(
            f"UPDATE users SET {columns} WHERE id = ?", (*fields.values(), user_id)
        )
        conn.commit()


def delete_user(user_id: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()


# ---------------- 会话 ----------------


def create_session(
    *,
    token_hash: str,
    user_id: str,
    expires_at: str,
    ip: str = "",
    ua: str = "",
) -> None:
    with _lock:
        conn = _connection()
        conn.execute(
            """
            INSERT INTO sessions(token_hash, user_id, created_at, expires_at, ip, ua)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (token_hash, user_id, _now(), expires_at, ip[:64], ua[:255]),
        )
        conn.commit()


def get_session(token_hash: str, now: str | None = None) -> dict[str, Any] | None:
    now = now or _now()
    with _lock:
        row = _connection().execute(
            "SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)
        ).fetchone()
    if row is None:
        return None
    if row["expires_at"] <= now:
        delete_session(token_hash)
        return None
    return dict(row)


def delete_session(token_hash: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()


def delete_user_sessions(user_id: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()


def purge_expired_sessions() -> int:
    now = _now()
    with _lock:
        conn = _connection()
        cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.commit()
    return int(cur.rowcount or 0)


# ---------------- 任务 ----------------


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def create_task(
    *,
    source: str,
    user_id: str,
    user_name: str,
    title: str,
    book_ref: str,
    fmt: str,
) -> dict[str, Any]:
    task_id = uuid.uuid4().hex[:12]
    now = _now()
    with _lock:
        conn = _connection()
        seq = (
            conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS s FROM tasks").fetchone()["s"]
        )
        conn.execute(
            """
            INSERT INTO tasks(id, source, user_id, user_name, title, book_ref, fmt,
                              status, seq, progress, chapters_done, chapters_total,
                              message, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, '', ?)
            """,
            (
                task_id,
                source,
                user_id,
                user_name,
                title,
                book_ref,
                fmt,
                STATUS_QUEUED,
                seq,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row)


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return _row_to_task(row) if row else None


def list_tasks(limit: int = 200) -> list[dict[str, Any]]:
    with _lock:
        rows = _connection().execute(
            "SELECT * FROM tasks ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def queued_tasks() -> list[dict[str, Any]]:
    with _lock:
        rows = _connection().execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY seq ASC", (STATUS_QUEUED,)
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def next_queued_task() -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY seq ASC LIMIT 1",
            (STATUS_QUEUED,),
        ).fetchone()
    return _row_to_task(row) if row else None


def running_task() -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY seq ASC LIMIT 1",
            (STATUS_RUNNING,),
        ).fetchone()
    return _row_to_task(row) if row else None


def queue_position(task_id: str) -> int:
    """返回排队位置（1 表示下一个执行）；不在排队中返回 0。"""
    with _lock:
        conn = _connection()
        task = conn.execute(
            "SELECT seq, status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not task or task["status"] != STATUS_QUEUED:
            return 0
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE status = ? AND seq <= ?",
            (STATUS_QUEUED, task["seq"]),
        ).fetchone()["c"]
    return int(count)


def update_task(task_id: str, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "status",
        "progress",
        "chapters_done",
        "chapters_total",
        "message",
        "file_path",
        "error",
        "started_at",
        "finished_at",
        "title",
        "user_id",
        "user_name",
        "size_bytes",
        "delivered_at",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"不允许更新的字段: {sorted(unknown)}")
    columns = ", ".join(f"{k} = ?" for k in fields)
    with _lock:
        conn = _connection()
        conn.execute(
            f"UPDATE tasks SET {columns} WHERE id = ?", (*fields.values(), task_id)
        )
        conn.commit()


def mark_running(task_id: str) -> None:
    update_task(task_id, status=STATUS_RUNNING, started_at=_now(), message="正在下载…")


def finish_task(
    task_id: str,
    status: str,
    *,
    error: str | None = None,
    file_path: str | None = None,
    message: str | None = None,
    size_bytes: int | None = None,
) -> None:
    fields: dict[str, Any] = {"status": status, "finished_at": _now()}
    if error is not None:
        fields["error"] = error[:2000]
    if file_path is not None:
        fields["file_path"] = file_path
    if message is not None:
        fields["message"] = message[:500]
    if size_bytes is not None:
        fields["size_bytes"] = int(size_bytes)
    update_task(task_id, **fields)


def mark_delivered(task_id: str) -> None:
    update_task(
        task_id,
        status=STATUS_DELIVERED,
        delivered_at=_now(),
        file_path=None,
        message="已传输到本机，服务器已删除临时文件",
    )


def mark_expired(task_id: str, reason: str = "超过接收时限，临时文件已清理") -> None:
    update_task(
        task_id,
        status=STATUS_EXPIRED,
        finished_at=_now(),
        file_path=None,
        message=reason,
    )


def ready_tasks() -> list[dict[str, Any]]:
    with _lock:
        rows = _connection().execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY seq ASC", (STATUS_READY,)
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def cancel_queued(predicate) -> list[dict[str, Any]]:
    """取消满足条件的排队任务，返回被取消的任务列表。"""
    canceled: list[dict[str, Any]] = []
    for task in queued_tasks():
        if predicate(task):
            update_task(
                task["id"],
                status=STATUS_CANCELED,
                finished_at=_now(),
                message="来源切换，已取消",
            )
            canceled.append(task)
    return canceled


def recover_after_restart() -> list[str]:
    """服务重启：把遗留的 running 任务标记为失败，排队任务保留。"""
    with _lock:
        conn = _connection()
        rows = conn.execute(
            "SELECT id FROM tasks WHERE status = ?", (STATUS_RUNNING,)
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            conn.execute(
                "UPDATE tasks SET status = ?, finished_at = ?, error = ? WHERE status = ?",
                (STATUS_FAILED, _now(), "服务重启导致任务中断", STATUS_RUNNING),
            )
            conn.commit()
    return ids


def count_tasks_for_user(user_id: str) -> int:
    with _lock:
        row = _connection().execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row["c"])


def purge_all_non_admin() -> dict[str, int]:
    """维护脚本用：清空所有非管理员用户、密钥与任务记录（不删文件，稍后统一清临时目录）。"""
    with _lock:
        conn = _connection()
        users = conn.execute(
            "SELECT id FROM users WHERE role != ?", (ROLE_ADMIN,)
        ).fetchall()
        ids = [row["id"] for row in users]
        for user_id in ids:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        keys = conn.execute("DELETE FROM invite_keys").rowcount
        tasks = conn.execute("DELETE FROM tasks").rowcount
        conn.commit()
    return {"users": len(ids), "keys": int(keys or 0), "tasks": int(tasks or 0)}


def task_counts() -> dict[str, int]:
    with _lock:
        rows = _connection().execute(
            "SELECT status, COUNT(*) AS c FROM tasks GROUP BY status"
        ).fetchall()
    return {row["status"]: int(row["c"]) for row in rows}


def purge_tasks(statuses: Iterable[str]) -> list[dict[str, Any]]:
    """删除指定状态的记录（只允许已结束的状态），返回被删除的行。"""
    wanted = [
        s
        for s in statuses
        if s
        in {
            STATUS_FAILED,
            STATUS_CANCELED,
            STATUS_PAUSED,
            STATUS_DELIVERED,
            STATUS_EXPIRED,
        }
    ]
    if not wanted:
        return []
    placeholders = ", ".join("?" for _ in wanted)
    with _lock:
        conn = _connection()
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE status IN ({placeholders})", wanted
        ).fetchall()
        if rows:
            conn.execute(f"DELETE FROM tasks WHERE status IN ({placeholders})", wanted)
            conn.commit()
    return [_row_to_task(r) for r in rows]


def recover_pending_ready() -> list[str]:
    """服务重启：待接收任务的临时文件已不存在，统一标记为过期。"""
    with _lock:
        conn = _connection()
        rows = conn.execute(
            "SELECT id FROM tasks WHERE status = ?", (STATUS_READY,)
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            conn.execute(
                "UPDATE tasks SET status = ?, finished_at = ?, error = ? WHERE status = ?",
                (STATUS_EXPIRED, _now(), "服务重启，临时文件已清理", STATUS_READY),
            )
            conn.commit()
    return ids


# ---------------- 邀请密钥（一钥一用户） ----------------


def _row_to_key(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def invite_key_code_exists(code: str) -> bool:
    with _lock:
        row = _connection().execute(
            "SELECT 1 FROM invite_keys WHERE key = ?", (code,)
        ).fetchone()
    return row is not None


def create_invite_key(
    *,
    key_id: str,
    code: str,
    mode: str,
    days: int,
    permanent: bool,
    username: str | None = None,
    password_plain: str | None = None,
    note: str = "",
    created_by: str = "",
) -> dict[str, Any]:
    with _lock:
        conn = _connection()
        conn.execute(
            """
            INSERT INTO invite_keys(id, key, mode, days, permanent, username,
                                    password_plain, status, note, created_at, created_by)
            VALUES(?, ?, ?, ?, ?, ?, ?, 'unused', ?, ?, ?)
            """,
            (
                key_id,
                code,
                mode,
                int(days),
                1 if permanent else 0,
                username,
                password_plain,
                note or "",
                _now(),
                created_by or None,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM invite_keys WHERE id = ?", (key_id,)).fetchone()
    return _row_to_key(row)


def get_invite_key(key_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM invite_keys WHERE id = ?", (key_id,)
        ).fetchone()
    return _row_to_key(row) if row else None


def get_invite_key_by_code(code: str) -> dict[str, Any] | None:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM invite_keys WHERE key = ?", (code,)
        ).fetchone()
    return _row_to_key(row) if row else None


def list_invite_keys(limit: int = 500) -> list[dict[str, Any]]:
    with _lock:
        rows = _connection().execute(
            "SELECT * FROM invite_keys ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_key(r) for r in rows]


def mark_invite_key_used(key_id: str, user_id: str, username: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute(
            "UPDATE invite_keys SET status = 'used', used_at = ?, used_by = ?, "
            "used_by_name = ? WHERE id = ?",
            (_now(), user_id, username, key_id),
        )
        conn.commit()


def bind_invite_key(key_id: str, *, user_id: str, username: str, password_plain: str) -> None:
    """注册成功后把密钥与用户账号绑定：后台据此展示账号与密码。"""
    with _lock:
        conn = _connection()
        conn.execute(
            "UPDATE invite_keys SET status = 'used', username = ?, password_plain = ?, "
            "used_at = ?, used_by = ?, used_by_name = ? WHERE id = ?",
            (username, password_plain, _now(), user_id, username, key_id),
        )
        conn.commit()


def revoke_invite_key(key_id: str) -> bool:
    with _lock:
        conn = _connection()
        cur = conn.execute(
            "UPDATE invite_keys SET status = 'revoked' WHERE id = ? AND status = 'unused'",
            (key_id,),
        )
        conn.commit()
    return bool(cur.rowcount)


def delete_invite_key(key_id: str) -> bool:
    with _lock:
        conn = _connection()
        cur = conn.execute("DELETE FROM invite_keys WHERE id = ?", (key_id,))
        conn.commit()
    return bool(cur.rowcount)


def invite_key_stats() -> dict[str, int]:
    with _lock:
        rows = _connection().execute(
            "SELECT status, COUNT(*) AS c FROM invite_keys GROUP BY status"
        ).fetchall()
    return {row["status"]: int(row["c"]) for row in rows}


# ---------------- 暴力破解防护（持久化计数） ----------------


def throttle_state(scope_key: str) -> dict[str, Any]:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM throttle WHERE scope_key = ?", (scope_key,)
        ).fetchone()
    if row is None:
        return {"scope_key": scope_key, "fail_count": 0, "window_start": 0.0,
                "locked_until": 0.0, "updated_at": 0.0}
    return dict(row)


def throttle_upsert(
    scope_key: str, *, fail_count: int, window_start: float, locked_until: float
) -> None:
    with _lock:
        conn = _connection()
        conn.execute(
            """
            INSERT INTO throttle(scope_key, fail_count, window_start, locked_until, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                fail_count = excluded.fail_count,
                window_start = excluded.window_start,
                locked_until = excluded.locked_until,
                updated_at = excluded.updated_at
            """,
            (scope_key, int(fail_count), float(window_start), float(locked_until), time.time()),
        )
        conn.commit()


def throttle_clear(scope_key: str) -> None:
    with _lock:
        conn = _connection()
        conn.execute("DELETE FROM throttle WHERE scope_key = ?", (scope_key,))
        conn.commit()


def throttle_purge_stale(older_than_seconds: float = 7 * 24 * 3600) -> int:
    cutoff = time.time() - older_than_seconds
    with _lock:
        conn = _connection()
        cur = conn.execute("DELETE FROM throttle WHERE updated_at < ?", (cutoff,))
        conn.commit()
    return int(cur.rowcount or 0)
