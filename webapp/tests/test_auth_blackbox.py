"""黑盒测试：真实 HTTP 服务上的注册/登录/权限/后台管理。

覆盖需求：
- 未登录无法进入界面（页面 303 跳登录，接口 401）
- 管理员未生成密钥时，注册直接拒绝
- 注册必须密钥正确；错误密钥 403
- 注册后默认无有效期，提交下载被 403 拦截
- 管理员按 1/31/124/372/999999 天叠加，999999 变永久
- 被禁用用户会话立刻失效；普通用户无法访问后台
- 登出后会话失效

运行：python tests/test_auth_blackbox.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import client, start_server, unique_name  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED.append(label)


def body(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def main() -> int:
    with start_server() as srv:
        base = srv.base_url
        anon = client(base)

        print("[1] 未登录：不能进入界面，接口全部 401")
        resp = anon.get("/")
        check(resp.status_code == 303 and resp.headers.get("location") == "/login", "首页跳转 /login")
        check(anon.get("/api/state").status_code == 401, "/api/state 401")
        check(anon.post("/api/tasks", json={}).status_code == 401, "提交任务 401")
        check(anon.get("/api/admin/overview").status_code == 401, "后台接口 401")
        check(anon.get("/login").status_code == 200, "登录页可匿名访问")
        check(anon.get("/register").status_code == 200, "注册页可匿名访问")

        print("[2] 管理员未生成密钥：注册被拒绝")
        meta = body(anon.get("/api/meta"))
        check(meta["app"]["registration_open"] is False, "meta 显示注册关闭")
        resp = anon.post(
            "/api/auth/register",
            json={"username": unique_name(), "password": "password123", "invite_key": ""},
        )
        check(resp.status_code == 403, "无密钥注册 403")

        print("[3] 管理员登录与后台总览")
        admin = client(base)
        resp = admin.post(
            "/api/auth/login", json={"username": "root", "password": "admin-pass-123"}
        )
        check(resp.status_code == 200, "管理员登录成功")
        check(body(resp)["user"]["role"] == "admin", "角色为 admin")
        check(body(resp)["user"]["permanent"] is True, "管理员永久有效")
        resp = admin.get("/api/admin/overview")
        check(resp.status_code == 200, "后台总览可访问")
        overview = body(resp)
        check(overview["user_count"] == 1, "初始只有管理员 1 人")
        check(overview["registration_key"] == "", "初始没有注册密钥")
        check(overview["grant_presets"] == [1, 31, 124, 372, 999999], "档位与需求一致")

        print("[4] 生成注册密钥")
        resp = admin.post("/api/admin/key")
        check(resp.status_code == 200, "生成密钥成功")
        key = body(resp)["registration_key"]
        check(len(key) == 21, "密钥长度 21")
        meta = body(anon.get("/api/meta"))
        check(meta["app"]["registration_open"] is True, "meta 显示注册已开放")

        print("[5] 注册：错误密钥 403 / 正确密钥 201")
        name = unique_name("alice")
        resp = anon.post(
            "/api/auth/register",
            json={"username": name, "password": "password123", "invite_key": key[:-1] + "X"},
        )
        check(resp.status_code == 403, "错误密钥被拒绝")
        user_a = client(base)
        resp = user_a.post(
            "/api/auth/register",
            json={"username": name, "password": "password123", "invite_key": key},
        )
        check(resp.status_code == 201, "正确密钥注册成功")
        user_data = body(resp)["user"]
        check(user_data["active"] is False, "新用户默认未开通")
        check(user_data["remaining_days"] == 0, "新用户剩余 0 天")
        check(user_data["role"] == "user", "新用户角色为 user")

        print("[6] 未开通用户：能看队列，但不能提交下载")
        check(user_a.get("/api/state").status_code == 200, "未开通用户可查看队列")
        resp = user_a.post(
            "/api/tasks",
            json={"source": "sonovel", "title": "t", "book_ref": "r", "fmt": "txt"},
        )
        check(resp.status_code == 403, "未开通用户提交下载 403")
        check("未开通" in str(body(resp).get("detail", "")), "错误信息说明了原因")

        print("[7] 管理员给用户叠加 1 天 → 可提交")
        resp = admin.post(f"/api/admin/users/{user_data['id']}/grant", json={"days": 1})
        check(resp.status_code == 200, "叠加 1 天成功")
        granted = body(resp)["user"]
        check(granted["remaining_days"] == 1, "剩余 1 天")
        check(granted["active"] is True, "账号变为可用")
        resp = user_a.post(
            "/api/tasks",
            json={"source": "sonovel", "title": "t", "book_ref": "r", "fmt": "txt"},
        )
        # 测试环境没有安装上游二进制，因此这里应当是「来源不可用」而不是权限错误
        check(resp.status_code == 409, "开通后通过权限校验（被来源未就绪拦截 409）")

        print("[8] 再叠加 31 天 → 累加为 32 天")
        resp = admin.post(f"/api/admin/users/{user_data['id']}/grant", json={"days": 31})
        granted = body(resp)["user"]
        check(granted["remaining_days"] == 32, "1 + 31 = 32 天（叠加而非覆盖）")

        print("[9] 非法档位被拒绝")
        resp = admin.post(f"/api/admin/users/{user_data['id']}/grant", json={"days": 7})
        check(resp.status_code == 400, "非预设档位 400")

        print("[10] 999999 → 永久")
        resp = admin.post(f"/api/admin/users/{user_data['id']}/grant", json={"days": 999999})
        granted = body(resp)["user"]
        check(granted["permanent"] is True, "标记为永久")
        check(granted["remaining_days"] is None, "永久不再显示剩余天数")

        print("[11] 普通用户无权访问后台")
        check(user_a.get("/api/admin/overview").status_code == 403, "用户访问后台 403")
        check(user_a.post("/api/admin/key").status_code == 403, "用户生成密钥 403")
        check(
            user_a.post(f"/api/admin/users/{user_data['id']}/grant", json={"days": 1}).status_code
            == 403,
            "用户自己加时长 403",
        )

        print("[12] 后台能看到用户与有效期")
        overview = body(admin.get("/api/admin/overview"))
        check(overview["user_count"] == 2, "用户数变为 2")
        alice = [u for u in overview["users"] if u["id"] == user_data["id"]][0]
        check(alice["permanent"] is True, "用户列表显示永久")

        print("[13] 禁用用户 → 会话立即失效")
        resp = admin.post(f"/api/admin/users/{user_data['id']}/status", json={"status": "banned"})
        check(resp.status_code == 200, "禁用成功")
        check(user_a.get("/api/state").status_code == 401, "被禁用后会话失效（401）")
        check(user_a.get("/api/admin/overview").status_code == 401, "被禁用后后台也 401")

        print("[14] 管理员不能禁用/删除自己")
        admin_id = body(admin.get("/api/auth/me"))["user"]["id"]
        check(
            admin.post(f"/api/admin/users/{admin_id}/status", json={"status": "banned"}).status_code
            == 400,
            "不能禁用自己",
        )
        check(admin.delete(f"/api/admin/users/{admin_id}").status_code == 400, "不能删除自己")

        print("[15] 轮换密钥后旧密钥立即失效")
        old_key = key
        new_key = body(admin.post("/api/admin/key"))["registration_key"]
        check(new_key != old_key, "新密钥不同于旧密钥")
        resp = anon.post(
            "/api/auth/register",
            json={"username": unique_name("bob"), "password": "password123", "invite_key": old_key},
        )
        check(resp.status_code == 403, "旧密钥注册失败")
        name2 = unique_name("bob")
        resp = anon.post(
            "/api/auth/register",
            json={"username": name2, "password": "password123", "invite_key": new_key},
        )
        check(resp.status_code == 201, "新密钥注册成功")

        print("[16] 重复用户名注册 409")
        resp = anon.post(
            "/api/auth/register",
            json={"username": name, "password": "password123", "invite_key": new_key},
        )
        check(resp.status_code == 409, "重名注册 409")

        print("[17] 清空密钥 → 关闭注册")
        check(admin.delete("/api/admin/key").status_code == 200, "清空密钥成功")
        meta = body(anon.get("/api/meta"))
        check(meta["app"]["registration_open"] is False, "注册已关闭")
        resp = anon.post(
            "/api/auth/register",
            json={"username": unique_name("carol"), "password": "password123", "invite_key": new_key},
        )
        check(resp.status_code == 403, "关闭后注册 403")

        print("[18] 登出与会话失效")
        bob = client(base)
        login_name = name2
        resp = bob.post("/api/auth/login", json={"username": login_name, "password": "password123"})
        check(resp.status_code == 200, "新用户登录成功")
        check(bob.post("/api/auth/logout").status_code == 200, "登出成功")
        check(bob.get("/api/state").status_code == 401, "登出后 401")

        print("[19] 错误口令与限流")
        bad = client(base)
        resp = bad.post("/api/auth/login", json={"username": "root", "password": "wrong-pass"})
        check(resp.status_code == 401, "错误口令 401")
        codes = [
            bad.post("/api/auth/login", json={"username": "root", "password": "x"}).status_code
            for _ in range(9)
        ]
        check(429 in codes, "连续失败触发 429 限流")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
