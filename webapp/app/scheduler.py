"""全局单线程下载调度器 + 来源切换语义。

核心约束（来自需求）：
1. 同一时刻只运行一个下载任务（全局单线程），其余任务在队列中等待，前端显示「排队中（第 N 位）」。
2. 同一时刻只允许一个「来源/插件」处于启用状态：任何时刻队列中不得混有多个来源的任务。
3. 切换来源时，若当前有任务正在下载，有两种策略：
   - after_current（默认）：等当前任务下载结束后再生效；期间旧来源的排队任务立即取消，
     且不允许再向旧来源提交新任务。
   - cancel_now：立即取消正在下载的任务和旧来源的排队任务，然后立刻切换。
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Any

from . import store
from .config import settings
from .plugins.base import CanceledError, Plugin

PRUNE_KEEP = 200


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return f"{size:.1f} GB"


def _wipe_temp_root() -> None:
    """启动时清空中转目录：旧进程留下的临时文件不应继续存在。"""
    shutil.rmtree(settings.temp_root, ignore_errors=True)
    settings.temp_root.mkdir(parents=True, exist_ok=True)


class SwitchError(Exception):
    def __init__(self, message: str, state: dict[str, Any] | None = None):
        super().__init__(message)
        self.state = state or {}


class EnqueueError(Exception):
    pass


class Scheduler:
    def __init__(self, plugins: dict[str, Plugin], default_source: str):
        self._plugins = plugins
        self._default_source = default_source
        self._cv = threading.Condition()
        self._running_task_id: str | None = None
        self._cancels: dict[str, threading.Event] = {}
        self._deliverables: dict[str, Path] = {}
        self._paused: set[str] = set()
        self._stop = False
        self._thread: threading.Thread | None = None
        self._sweeper: threading.Thread | None = None

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if store.active_source(self._default_source) not in self._plugins:
            store.set_setting("active_source", self._default_source)
        # 重启后遗留的 running 任务不可能继续，直接标记失败
        store.recover_after_restart()
        # 待接收任务的临时文件在重启后已无意义
        store.recover_pending_ready()
        _wipe_temp_root()
        self._thread = threading.Thread(
            target=self._worker_loop, name="novel-download-worker", daemon=True
        )
        self._thread.start()
        self._sweeper = threading.Thread(
            target=self._sweep_loop, name="novel-temp-sweeper", daemon=True
        )
        self._sweeper.start()

    def shutdown(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        for plugin in self._plugins.values():
            try:
                plugin.shutdown()
            except Exception:
                pass

    # ---------------- 对外状态 ----------------
    def snapshot(self, viewer: dict[str, Any] | None = None) -> dict[str, Any]:
        active = store.active_source(self._default_source)
        pending = store.pending_switch()
        running = store.running_task()
        queued = store.queued_tasks()
        positions = {t["id"]: i + 1 for i, t in enumerate(queued)}
        viewer_id = (viewer or {}).get("id")
        viewer_is_admin = (viewer or {}).get("role") == store.ROLE_ADMIN
        tasks: list[dict[str, Any]] = []
        for task in store.list_tasks(limit=PRUNE_KEEP):
            mine = bool(viewer_id) and task.get("user_id") == viewer_id
            can_manage = mine or viewer_is_admin
            item = {
                "id": task["id"],
                "source": task["source"],
                "user": task["user_name"],
                "title": task["title"],
                "fmt": task["fmt"],
                "status": task["status"],
                "progress": round(float(task["progress"] or 0), 1),
                "chapters_done": task["chapters_done"],
                "chapters_total": task["chapters_total"],
                "message": task["message"],
                # 别人的失败原因不展示，避免泄露他人请求信息
                "error": task["error"] if can_manage else None,
                "created_at": task["created_at"],
                "started_at": task["started_at"],
                "finished_at": task["finished_at"],
                "delivered_at": task["delivered_at"],
                "size_bytes": task["size_bytes"] if can_manage else 0,
                "book_ref": task["book_ref"] if can_manage else None,
                "has_file": can_manage and task["status"] == store.STATUS_READY,
                "mine": mine,
                "can_cancel": can_manage
                and task["status"] in {store.STATUS_QUEUED, store.STATUS_RUNNING},
                "can_pause": can_manage
                and task["status"] in {store.STATUS_QUEUED, store.STATUS_RUNNING},
                "can_receive": can_manage and task["status"] == store.STATUS_READY,
                "can_retry": can_manage
                and task["status"]
                in {store.STATUS_PAUSED, store.STATUS_DELIVERED, store.STATUS_EXPIRED,
                    store.STATUS_FAILED, store.STATUS_CANCELED},
            }
            if task["status"] == store.STATUS_QUEUED:
                item["queue_position"] = positions.get(task["id"], 0)
            tasks.append(item)
        return {
            "active_source": active,
            "pending_switch": pending,
            "running": (
                {"id": running["id"], "title": running["title"], "source": running["source"]}
                if running
                else None
            ),
            "queue_length": len(queued),
            "counts": store.task_counts(),
            "tasks": tasks,
        }

    # ---------------- 提交任务 ----------------
    def enqueue(
        self,
        *,
        source: str,
        user_id: str,
        user_name: str,
        title: str,
        book_ref: str,
        fmt: str,
    ) -> dict[str, Any]:
        with self._cv:
            active = store.active_source(self._default_source)
            pending = store.pending_switch()
            if pending and pending.get("source") != active:
                raise EnqueueError(
                    f"来源切换即将生效（目标：{self._plugin_name(pending['source'])}），"
                    f"当前处于「{self._plugin_name(active)}」，请等待切换完成后再提交。"
                )
            if source != active:
                raise EnqueueError(
                    f"当前启用的来源是「{self._plugin_name(active)}」，"
                    f"提交前请先切换到「{self._plugin_name(source)}」。"
                )
            plugin = self._plugins.get(source)
            if plugin is None:
                raise EnqueueError(f"未知来源：{source}")
            status = plugin.status()
            if not status.ready:
                raise EnqueueError(f"来源不可用：{status.detail}")
            if fmt not in plugin.capabilities.formats:
                raise EnqueueError(
                    f"「{plugin.name}」不支持格式 {fmt}，可选：{'/'.join(plugin.capabilities.formats)}"
                )
            task = store.create_task(
                source=source,
                user_id=user_id,
                user_name=user_name,
                title=title.strip() or "未命名",
                book_ref=book_ref.strip(),
                fmt=fmt,
            )
            position = store.queue_position(task["id"])
            self._cv.notify_all()
        return {"task": task, "queue_position": position}

    # ---------------- 暂停（不可续传） --------------
    def pause(self, task_id: str) -> dict[str, Any]:
        """暂停 = 终止当前任务且不保留进度；之后只能「重新下载」（重新排队）。

        上游没有可续传的暂停（so-novel 明确无断点续传），因此不做伪续传。
        """
        with self._cv:
            task = store.get_task(task_id)
            if task is None:
                raise KeyError(task_id)
            if task["status"] == store.STATUS_QUEUED:
                store.update_task(
                    task_id,
                    status=store.STATUS_PAUSED,
                    finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    message="已暂停（尚未开始）；如需下载请「重新下载」重新排队",
                )
                self._cv.notify_all()
                return {"paused": True, "was_running": False}
            if task["status"] == store.STATUS_READY:
                self._drop_temp(task_id)
                store.finish_task(
                    task_id,
                    store.STATUS_PAUSED,
                    message="已暂停并删除临时文件；如需下载请「重新下载」重新排队",
                )
                self._cv.notify_all()
                return {"paused": True, "was_running": False}
            if task["status"] != store.STATUS_RUNNING:
                raise ValueError("任务已结束，无法暂停")

            self._paused.add(task_id)
            event = self._cancels.get(task_id)
            if event is not None:
                event.set()
            plugin = self._plugins.get(task["source"])
            if plugin is not None:
                try:
                    plugin.cancel(task_id)
                except Exception:
                    pass
            store.update_task(task_id, message="正在暂停…")
            return {"paused": True, "was_running": True}

    def _mark_stopped(self, task_id: str, reason: str = "") -> None:
        """任务被中断：按是否「暂停」决定最终状态。"""
        self._drop_temp(task_id)
        if task_id in self._paused:
            self._paused.discard(task_id)
            store.finish_task(
                task_id,
                store.STATUS_PAUSED,
                message="已暂停，进度已丢弃；如需继续请「重新下载」（会重新排队）",
                error=reason or "已暂停",
            )
        else:
            store.finish_task(
                task_id, store.STATUS_CANCELED, message="已取消", error=reason or "已取消"
            )

    # ---------------- 取消 / 删除 --------------
    def cancel(self, task_id: str) -> dict[str, Any]:
        with self._cv:
            task = store.get_task(task_id)
            if task is None:
                raise KeyError(task_id)
            if task["status"] == store.STATUS_QUEUED:
                store.update_task(
                    task_id,
                    status=store.STATUS_CANCELED,
                    finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    message="用户取消（排队中）",
                )
                self._cv.notify_all()
                return {"canceled": True, "was_running": False}

            if task["status"] == store.STATUS_READY:
                # 待接收的文件直接丢弃
                self._drop_temp(task_id)
                store.finish_task(
                    task_id,
                    store.STATUS_CANCELED,
                    message="已取消，临时文件已删除",
                    error="已取消",
                )
                self._cv.notify_all()
                return {"canceled": True, "was_running": False}

            if task["status"] == store.STATUS_RUNNING:
                self._paused.discard(task_id)
                event = self._cancels.get(task_id)
                if event is not None:
                    event.set()
                plugin = self._plugins.get(task["source"])
                if plugin is not None:
                    try:
                        plugin.cancel(task_id)
                    except Exception:
                        pass
                store.update_task(task_id, message="正在取消…")
                return {"canceled": True, "was_running": True}
        return {"canceled": False, "was_running": False, "reason": "任务已结束"}

    # ---------------- 清理 --------------
    def cleanup_finished(
        self, statuses: tuple[str, ...] = (store.STATUS_FAILED, store.STATUS_CANCELED)
    ) -> dict[str, Any]:
        """删除已结束的任务记录及其临时目录（默认只清理失败/取消，保留已交付的记录）。"""
        with self._cv:
            removed = store.purge_tasks(statuses)
            for task in removed:
                self._drop_temp(task["id"])
            self._cv.notify_all()
        return {"removed": len(removed), "ids": [t["id"] for t in removed]}

    # ---------------- 来源切换 --------------
    def request_switch(self, source: str, mode: str = "after_current") -> dict[str, Any]:
        if source not in self._plugins:
            raise SwitchError(f"未知来源：{source}")
        if mode not in {"after_current", "cancel_now"}:
            raise SwitchError(f"未知切换策略：{mode}")
        plugin = self._plugins[source]
        status = plugin.status()
        if not status.ready:
            raise SwitchError(f"来源不可用：{status.detail}")

        with self._cv:
            active = store.active_source(self._default_source)
            if active == source:
                store.set_pending_switch(None)
                self._cv.notify_all()
                return {
                    "active_source": active,
                    "pending_switch": None,
                    "canceled": [],
                    "applied": True,
                    "message": f"当前已是「{plugin.name}」",
                }

            running = store.running_task()
            if running is None:
                canceled = self._cancel_other_queued(source)
                store.set_setting("active_source", source)
                store.set_pending_switch(None)
                self._cv.notify_all()
                return {
                    "active_source": source,
                    "pending_switch": None,
                    "canceled": canceled,
                    "applied": True,
                    "message": f"已切换到「{plugin.name}」",
                }

            if mode == "cancel_now":
                canceled = self._cancel_other_queued(source)
                event = self._cancels.get(running["id"])
                if event is not None:
                    event.set()
                old_plugin = self._plugins.get(running["source"])
                if old_plugin is not None:
                    try:
                        old_plugin.cancel(running["id"])
                    except Exception:
                        pass
                store.set_setting("active_source", source)
                store.set_pending_switch(None)
                self._cv.notify_all()
                return {
                    "active_source": source,
                    "pending_switch": None,
                    "canceled": canceled,
                    "applied": True,
                    "message": (
                        f"已切换到「{plugin.name}」，"
                        f"正在下载的「{running['title']}」已被取消"
                    ),
                }

            # after_current：只允许当前正在下载的那个任务收尾
            canceled = self._cancel_other_queued(source)
            pending = {
                "source": source,
                "mode": mode,
                "requested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "waiting_for": running["id"],
            }
            store.set_pending_switch(pending)
            self._cv.notify_all()
            return {
                "active_source": active,
                "pending_switch": pending,
                "canceled": canceled,
                "applied": False,
                "message": (
                    f"「{self._plugin_name(active)}」正在下载「{running['title']}」，"
                    f"结束后将自动切换到「{plugin.name}」；旧来源的排队任务已取消"
                ),
            }

    # ---------------- 内部工具 --------------
    def _plugin_name(self, source: str) -> str:
        plugin = self._plugins.get(source)
        return plugin.name if plugin else source

    def _cancel_other_queued(self, target_source: str) -> list[dict[str, Any]]:
        canceled = store.cancel_queued(lambda t: t["source"] != target_source)
        return [
            {"id": t["id"], "title": t["title"], "user": t["user_name"]} for t in canceled
        ]

    def _apply_pending_if_idle(self) -> None:
        """仅在没有运行任务时调用：应用待切换的来源。"""
        pending = store.pending_switch()
        if not pending:
            return
        target = pending.get("source")
        active = store.active_source(self._default_source)
        if not target or target == active:
            store.set_pending_switch(None)
            return
        self._cancel_other_queued(target)
        store.set_setting("active_source", target)
        store.set_pending_switch(None)

    # ---------------- 工作线程 --------------
    def _worker_loop(self) -> None:
        while True:
            with self._cv:
                if self._stop:
                    return
                self._apply_pending_if_idle()
                task = store.next_queued_task()
                if task is None:
                    self._cv.wait(timeout=2.0)
                    continue
                if task["source"] != store.active_source(self._default_source):
                    # 理论上不会发生（切换时已取消旧来源任务），兜底取消
                    store.update_task(
                        task["id"],
                        status=store.STATUS_CANCELED,
                        finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        message="来源已切换，任务作废",
                    )
                    continue
                store.mark_running(task["id"])
                self._running_task_id = task["id"]
                cancel_event = threading.Event()
                self._cancels[task["id"]] = cancel_event

            try:
                self._run_one(task, cancel_event)
            except Exception as exc:  # noqa: BLE001 - 任何插件/IO 异常都不能拖垮工作线程
                try:
                    self._drop_temp(task["id"])
                    store.finish_task(
                        task["id"],
                        store.STATUS_FAILED,
                        error=f"内部错误：{exc}",
                        message="下载失败",
                    )
                except Exception:
                    pass

            with self._cv:
                self._running_task_id = None
                self._cancels.pop(task["id"], None)
                self._cv.notify_all()

    def _run_one(self, task: dict[str, Any], cancel_event: threading.Event) -> None:
        plugin = self._plugins.get(task["source"])
        if plugin is None:
            store.finish_task(task["id"], store.STATUS_FAILED, error="来源插件不存在")
            return

        last_progress = {"ts": 0.0, "pct": -1.0, "done": -1, "total": -1}

        def progress(
            done: int | None = None,
            total: int | None = None,
            percent: float | None = None,
            message: str | None = None,
            title: str | None = None,
        ) -> None:
            now = time.time()
            changed = False
            if percent is not None:
                changed = abs(float(percent) - last_progress["pct"]) >= 0.5
                last_progress["pct"] = float(percent)
            if done is not None and done != last_progress["done"]:
                last_progress["done"] = done
                changed = True
            if total is not None and total != last_progress["total"]:
                last_progress["total"] = total
                changed = True
            if message:
                changed = True
            if title:
                changed = True
                try:
                    store.update_task(task["id"], title=title)
                except Exception:
                    pass
            if not changed or (now - last_progress["ts"]) < 0.4:
                return
            last_progress["ts"] = now
            fields: dict[str, Any] = {
                "progress": max(0.0, min(100.0, last_progress["pct"] if last_progress["pct"] >= 0 else 0.0)),
                "chapters_done": max(0, last_progress["done"]),
                "chapters_total": max(0, last_progress["total"]),
                "message": message or "",
            }
            try:
                store.update_task(task["id"], **fields)
            except Exception:
                pass

        try:
            result = plugin.download(
                task=task,
                progress=progress,
                cancel_event=cancel_event,
                # 上游只能写磁盘，这里给每个任务一个临时目录；交付后立刻删除
                library_dir=str(settings.temp_dir_for(task["id"])),
            )
        except CanceledError:
            self._mark_stopped(task["id"])
            return
        except Exception as exc:  # noqa: BLE001 - 上游异常统一落库
            if cancel_event.is_set():
                self._mark_stopped(task["id"], str(exc)[:2000])
            else:
                self._drop_temp(task["id"])
                store.finish_task(
                    task["id"], store.STATUS_FAILED, error=str(exc), message="下载失败"
                )
            return

        if cancel_event.is_set():
            self._mark_stopped(task["id"])
            return

        path = Path(result.file_path) if result.file_path else None
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            self._drop_temp(task["id"])
            store.finish_task(
                task["id"],
                store.STATUS_FAILED,
                error="下载结束但没有生成文件",
                message="下载失败",
            )
            return

        size = path.stat().st_size
        self._deliverables[task["id"]] = path
        store.update_task(task["id"], progress=100.0)
        store.finish_task(
            task["id"],
            store.STATUS_READY,
            message=f"文件已就绪（{_human_size(size)}），请尽快点击接收；服务器不留存",
            size_bytes=size,
            file_path=str(path),
        )
        if result.title:
            try:
                store.update_task(task["id"], title=result.title)
            except Exception:
                pass

    # ---------------- 交付（流式传输后删除） --------------
    def deliverable_path(self, task_id: str) -> Path | None:
        path = self._deliverables.get(task_id)
        if path and path.is_file():
            return path
        # 兜底：按任务临时目录找（进程重启后字典会丢失，此时由 TTL 清理）
        candidates = list((settings.temp_root / task_id).rglob("*"))
        files = [p for p in candidates if p.is_file() and p.stat().st_size > 0]
        if files:
            return max(files, key=lambda p: p.stat().st_size)
        return None

    def complete_delivery(self, task_id: str) -> None:
        """文件传输完成后调用：删除临时文件并标记已交付。"""
        self._drop_temp(task_id)
        store.mark_delivered(task_id)

    def _drop_temp(self, task_id: str) -> None:
        self._deliverables.pop(task_id, None)
        shutil.rmtree(settings.temp_root / task_id, ignore_errors=True)

    def _sweep_loop(self) -> None:
        """定期清理超过接收时限的临时文件。"""
        interval = 60
        while True:
            with self._cv:
                if self._stop:
                    return
                self._cv.wait(timeout=interval)
            if self._stop:
                return
            try:
                self._sweep_once()
            except Exception as exc:  # noqa: BLE001
                print(f"[scheduler] 清理临时文件失败: {exc}")

    def _sweep_once(self) -> None:
        ttl_seconds = max(1, settings.file_ttl_min) * 60
        now = time.time()
        for task in store.ready_tasks():
            task_dir = settings.temp_root / task["id"]
            age = now - task_dir.stat().st_mtime if task_dir.is_dir() else ttl_seconds + 1
            if age > ttl_seconds:
                self._drop_temp(task["id"])
                store.mark_expired(task["id"])
        # 清理没有对应记录的孤儿目录
        with self._cv:
            self._cv.notify_all()
