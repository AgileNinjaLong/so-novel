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

import threading
import time
from typing import Any

from . import store
from .plugins.base import CanceledError, Plugin

PRUNE_KEEP = 200


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
        self._stop = False
        self._thread: threading.Thread | None = None

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if store.active_source(self._default_source) not in self._plugins:
            store.set_setting("active_source", self._default_source)
        # 重启后遗留的 running 任务不可能继续，直接标记失败
        store.recover_after_restart()
        self._thread = threading.Thread(
            target=self._worker_loop, name="novel-download-worker", daemon=True
        )
        self._thread.start()

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
    def snapshot(self) -> dict[str, Any]:
        active = store.active_source(self._default_source)
        pending = store.pending_switch()
        running = store.running_task()
        queued = store.queued_tasks()
        positions = {t["id"]: i + 1 for i, t in enumerate(queued)}
        tasks: list[dict[str, Any]] = []
        for task in store.list_tasks(limit=PRUNE_KEEP):
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
                "error": task["error"],
                "created_at": task["created_at"],
                "started_at": task["started_at"],
                "finished_at": task["finished_at"],
                "has_file": bool(task["file_path"]),
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
        self, *, source: str, user_name: str, title: str, book_ref: str, fmt: str
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
                user_name=user_name,
                title=title.strip() or "未命名",
                book_ref=book_ref.strip(),
                fmt=fmt,
            )
            position = store.queue_position(task["id"])
            self._cv.notify_all()
        return {"task": task, "queue_position": position}

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
            if task["status"] == store.STATUS_RUNNING:
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

            self._run_one(task, cancel_event)

            with self._cv:
                self._running_task_id = None
                self._cancels.pop(task["id"], None)
                self._cv.notify_all()

    def _run_one(self, task: dict[str, Any], cancel_event: threading.Event) -> None:
        from .config import settings

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
                library_dir=str(settings.library_dir),
            )
        except CanceledError:
            store.finish_task(
                task["id"], store.STATUS_CANCELED, message="已取消", error="已取消"
            )
            return
        except Exception as exc:  # noqa: BLE001 - 上游异常统一落库
            if cancel_event.is_set():
                store.finish_task(
                    task["id"], store.STATUS_CANCELED, message="已取消", error=str(exc)[:2000]
                )
            else:
                store.finish_task(
                    task["id"], store.STATUS_FAILED, error=str(exc), message="下载失败"
                )
            return

        if cancel_event.is_set():
            store.finish_task(
                task["id"], store.STATUS_CANCELED, message="已取消", error="已取消"
            )
            return
        store.update_task(task["id"], progress=100.0)
        store.finish_task(
            task["id"],
            store.STATUS_SUCCESS,
            file_path=result.file_path,
            message="下载完成",
        )
        if result.title:
            try:
                store.update_task(task["id"], title=result.title)
            except Exception:
                pass
