"""维护脚本：清空演示/测试数据（保留管理员账号与上游二进制）。

用法（先停止服务，避免 SQLite 并发写）：
    WEBAPP_DATA_DIR=/path/to/data python scripts/reset_demo.py
    WEBAPP_DATA_DIR=... python scripts/reset_demo.py --keep-users   # 只清任务与密钥

会删除：非管理员用户、会话、注册密钥、任务记录，以及 runtime/tmp 临时文件。
不会删除：plugins/（上游 jar、rules、番茄二进制、JRE）、管理员账号。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import store  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-users", action="store_true", help="保留普通用户，只清任务与密钥")
    args = parser.parse_args()

    store.init_db()
    print(f"数据目录：{settings.data_dir}")

    with store._lock:  # noqa: SLF001 - 维护脚本直接用底层连接
        conn = store._connection()  # noqa: SLF001
        if args.keep_users:
            keys = conn.execute("DELETE FROM invite_keys").rowcount
            tasks = conn.execute("DELETE FROM tasks").rowcount
            conn.commit()
            users_removed = 0
        else:
            keys = conn.execute("DELETE FROM invite_keys").rowcount
            tasks = conn.execute("DELETE FROM tasks").rowcount
            users = conn.execute(
                "SELECT id FROM users WHERE role != ?", (store.ROLE_ADMIN,)
            ).fetchall()
            for row in users:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
                conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))
            conn.execute("DELETE FROM throttle")
            conn.commit()
            users_removed = len(users)

    removed_tmp = shutil.rmtree(settings.temp_root, ignore_errors=True) is None
    settings.temp_root.mkdir(parents=True, exist_ok=True)

    print(f"已删除：用户 {users_removed} 个、密钥 {keys} 把、任务 {tasks} 条、临时目录{'已清理' if removed_tmp else '清理失败'}")
    print(f"保留管理员：{[u['username'] for u in store.list_users()]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
