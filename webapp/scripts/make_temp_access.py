"""生成「临时控制」凭据：一个临时管理员账号 + 一个一次性注册密钥。

用法（先停服务，脚本直接写库）：

    WEBAPP_DATA_DIR=/data python scripts/make_temp_access.py
    WEBAPP_DATA_DIR=/data python scripts/make_temp_access.py --days 1 --note "临时调试"

撤销：后台「用户列表」里把临时管理员删掉，或
    WEBAPP_DATA_DIR=/data python scripts/reset_demo.py   （会清空所有普通用户与密钥）

注意：脚本直接操作 SQLite，请先停掉 webapp 再执行，避免并发写。
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, store, validity  # noqa: E402
from app.config import settings  # noqa: E402


def random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-name", default="tempctl", help="临时管理员用户名")
    parser.add_argument("--days", type=int, default=1, help="注册密钥有效期（天）")
    parser.add_argument("--count", type=int, default=1, help="生成几个注册密钥")
    parser.add_argument("--note", default="临时访问", help="密钥备注")
    args = parser.parse_args()

    store.init_db()
    print(f"数据目录：{settings.data_dir}")

    # 1) 临时管理员（永久有效，便于随时进后台；用完可删除）
    name = args.admin_name
    if store.get_user_by_username(name) is not None:
        print(f"[跳过] 管理员 {name} 已存在，未改动其密码")
        admin_password = ""
    else:
        admin_password = random_password()
        admin_user = store.create_user(
            user_id=auth.unique_nanoid(16, lambda _id: store.get_user(_id) is not None),
            username=name,
            password_hash=auth.hash_password(admin_password),
            role=store.ROLE_ADMIN,
            created_by="temp-access",
            permanent=True,
            expires_at=None,
        )
        print(f"[已创建] 临时管理员：{admin_user['username']} / {admin_password}")

    # 2) 一次性注册密钥（给普通用户体验注册流程）
    keys = auth.generate_invite_keys(
        days=args.days, count=args.count, note=args.note, created_by="temp-access"
    )
    for k in keys:
        print(f"[已创建] 注册密钥：{k['key']}　有效期：{'永久' if k['permanent'] else str(k['days']) + ' 天'}")

    print()
    print("=== 交给对方的凭据 ===")
    if admin_password:
        print(f"后台账号：{name}")
        print(f"后台密码：{admin_password}")
    print(f"注册密钥：{keys[0]['key']}")
    print("======================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
