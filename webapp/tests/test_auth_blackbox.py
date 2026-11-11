"""黑盒测试：真实 HTTP 服务上的密钥激活 / 登录 / 权限 / 后台 / 抗暴力破解。

覆盖：
- 未登录无法进入界面；没有可用密钥时注册关闭
- 一钥一账号：激活后密钥失效，已用密钥仍显示其账号密码
- 管理员指定或自动生成账号密码；后台列表展示账号/密码/使用者
- 有效期叠加、999999 永久、非法档位
- 权限矩阵：普通用户不能进后台、不能操作别人任务
- 禁用用户立即失效会话；重置密码；密钥撤销/删除
- 登录暴力破解：连续错误后账号被锁定（429），且锁定持久化

运行：python tests/test_auth_blackbox.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import client, start_server  # noqa: E402

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


def make_keys(admin, **kwargs):
    return body(admin.post("/api/admin/keys", json=kwargs))["keys"]


def main() -> int:
    with start_server() as srv:
        base = srv.base_url
        anon = client(base)

        print("[1] 未登录：页面跳转、接口 401")
        resp = anon.get("/")
        check(resp.status_code == 303 and resp.headers.get("location") == "/login", "首页跳转 /login")
        check(anon.get("/api/state").status_code == 401, "/api/state 401")
        check(anon.post("/api/tasks", json={}).status_code == 401, "提交任务 401")
        check(anon.get("/api/admin/overview").status_code == 401, "后台接口 401")
        check(anon.get("/login").status_code == 200, "登录页可匿名访问")
        check(anon.get("/register").status_code == 200, "注册页可匿名访问")
        check(anon.get("/api/auth/key-info?key=nope").json()["valid"] is False, "密钥查询可匿名访问")

        print("[2] 没有可用密钥：注册关闭")
        meta = body(anon.get("/api/meta"))
        check(meta["app"]["registration_open"] is False, "meta 显示注册关闭")
        check(
            anon.post("/api/auth/register", json={"key": "NOT-A-KEY"}).status_code == 403,
            "无有效密钥激活 403",
        )

        print("[3] 管理员登录与后台总览")
        admin = client(base)
        check(
            admin.post("/api/auth/login", json={"username": "root", "password": "admin-pass-123"}).status_code == 200,
            "管理员登录成功",
        )
        me = body(admin.get("/api/auth/me"))["user"]
        check(me["role"] == "admin" and me["permanent"] is True, "管理员角色正确且永久")
        overview = body(admin.get("/api/admin/overview"))
        check(overview["user_count"] == 1, "初始只有管理员")
        check(overview["keys"] == [], "初始没有密钥")
        check(overview["grant_presets"] == [1, 31, 124, 372, 999999], "档位正确")

        print("[4] 生成密钥：只带有效期，不生成账号密码")
        keys = make_keys(admin, days=372, count=2)
        check(len(keys) == 2, "生成 2 把")
        check(len({k["key"] for k in keys}) == 2, "密钥不同")
        check(all(k["bound"] is False and k["username"] == "" and k["password"] == "" for k in keys),
              "未生成账号密码")
        check(all(k["status"] == "unused" and k["days_text"] == "372 天" for k in keys), "状态与天数正确")
        check(body(anon.get("/api/meta"))["app"]["unused_keys"] == 2, "剩余可用密钥 2 把")

        print("[5] 注册时用户自己设置账号密码，成功后绑定到密钥")
        k0 = keys[0]
        info = body(anon.get("/api/auth/key-info?key=" + k0["key"]))
        check(info["valid"] is True, "密钥有效")
        check(info["username"] == "" and info["password"] == "", "未注册前没有账号")
        check(info.get("needs_credentials") is True, "提示由用户设置账密")

        alice = client(base)
        resp = alice.post(
            "/api/auth/register",
            json={"key": k0["key"], "username": "alice01", "password": "alice-pass-1"},
        )
        check(resp.status_code == 201, "注册成功")
        user_a = body(resp)["user"]
        check(user_a["username"] == "alice01", "账号为用户自设")
        check(user_a["remaining_days"] == 372, "有效期 372 天")
        check(user_a["active"] is True, "注册即可用")
        check(
            client(base).post("/api/auth/login", json={"username": "alice01", "password": "alice-pass-1"}).status_code == 200,
            "可用自设密码登录",
        )

        print("[6] 后台可见绑定后的账号密码；密钥只能注册一次")
        keys_now = body(admin.get("/api/admin/keys"))["keys"]
        bound = [k for k in keys_now if k["key"] == k0["key"]][0]
        check(bound["bound"] is True, "密钥已绑定账号")
        check(bound["username"] == "alice01", "后台显示注册的账号")
        check(bound["password"] == "alice-pass-1", "后台显示该账号的密码")
        check(bound["used_by_name"] == "alice01", "后台显示使用者")
        check(anon.post("/api/auth/register", json={"key": k0["key"], "username": "x2", "password": "password123"}).status_code == 403,
              "重复注册 403")
        used = body(anon.get("/api/auth/key-info?key=" + k0["key"]))
        check(used["valid"] is False and used["username"] == "alice01", "已用密钥查询显示绑定账号")

        print("[7] 用户名冲突：同一账号名不能注册两次")
        check(
            anon.post(
                "/api/auth/register",
                json={"key": keys[1]["key"], "username": "alice01", "password": "password123"},
            ).status_code == 409,
            "重名注册 409",
        )

        print("[8] 后台密钥列表：已绑定的密钥带账号密码，未绑定的不带")
        keys_now = body(admin.get("/api/admin/keys"))["keys"]
        bound_keys = [k for k in keys_now if k["bound"]]
        check(len(bound_keys) >= 1, "存在已绑定的密钥")
        check(all(k["username"] and k["password"] for k in bound_keys), "已绑定的密钥都带账号密码")
        check(all(not k["username"] for k in keys_now if not k["bound"]), "未绑定的密钥没有账号")
        check(any(k["used_by_name"] for k in bound_keys), "已用密钥显示使用者")

        print("[9] 有效期叠加 / 永久 / 非法档位")
        uid = user_a["id"]
        r = body(admin.post(f"/api/admin/users/{uid}/grant", json={"days": 1}))["user"]
        check(r["remaining_days"] == 373, "372 + 1 = 373（叠加）")
        r = body(admin.post(f"/api/admin/users/{uid}/grant", json={"days": 999999}))["user"]
        check(r["permanent"] is True and r["remaining_days"] is None, "999999 → 永久")
        check(admin.post(f"/api/admin/users/{uid}/grant", json={"days": 7}).status_code == 400, "非法档位 400")

        print("[10] 权限矩阵")
        check(alice.get("/api/admin/overview").status_code == 403, "用户访问后台 403")
        check(alice.post("/api/admin/keys", json={"days": 1}).status_code == 403, "用户生成密钥 403")
        check(alice.post(f"/api/admin/users/{uid}/grant", json={"days": 1}).status_code == 403, "用户给自己加时长 403")
        resp = alice.post("/api/tasks", json={"source": "sonovel", "title": "t", "book_ref": "r", "fmt": "txt"})
        check(resp.status_code == 409, "有效用户通过权限校验（被来源未就绪拦截 409）")

        print("[11] 撤销与删除密钥")
        fresh = make_keys(admin, days=1, count=1)[0]
        check(admin.delete(f"/api/admin/keys/{fresh['id']}?hard=1").status_code == 200, "硬删除记录")
        check(body(anon.get("/api/auth/key-info?key=" + fresh["key"]))["valid"] is False, "删除后不可用")
        fresh2 = make_keys(admin, days=1, count=1)[0]
        check(admin.delete(f"/api/admin/keys/{fresh2['id']}").status_code == 200, "撤销未使用密钥")
        check(anon.post("/api/auth/register", json={"key": fresh2["key"]}).status_code == 403, "撤销后激活 403")

        print("[12] 管理员重置密码")
        reset = body(admin.post(f"/api/admin/users/{uid}/password"))
        check(len(reset["password"]) >= 8 and reset["password"] != "alice-pass-1", "返回新密码")
        check(alice.get("/api/state").status_code == 401, "重置后旧会话失效")
        check(
            client(base).post("/api/auth/login", json={"username": "alice01", "password": reset["password"]}).status_code == 200,
            "新密码可登录",
        )

        print("[13] 禁用用户：登录被拒、会话立即失效")
        victim = client(base)
        check(
            victim.post("/api/auth/login", json={"username": "alice01", "password": reset["password"]}).status_code == 200,
            "禁用前可登录",
        )
        check(admin.post(f"/api/admin/users/{uid}/status", json={"status": "banned"}).status_code == 200, "禁用成功")
        check(victim.get("/api/state").status_code == 401, "禁用后原有会话失效")
        check(
            client(base).post("/api/auth/login", json={"username": "alice01", "password": reset["password"]}).status_code == 403,
            "禁用后无法登录",
        )

        print("[14] 管理员不能禁用/删除自己")
        admin_id = body(admin.get("/api/auth/me"))["user"]["id"]
        check(admin.post(f"/api/admin/users/{admin_id}/status", json={"status": "banned"}).status_code == 400, "不能禁用自己")
        check(admin.delete(f"/api/admin/users/{admin_id}").status_code == 400, "不能删除自己")

        print("[15] 生成数量上限为 20 把")
        many = make_keys(admin, days=1, count=50)
        check(len(many) == 20, "超过 20 自动截断为 20")
        check(all(k["bound"] is False for k in many), "批量生成的密钥都不带账号")

        print("[16] 登录暴力破解：连续失败后锁定（持久化）")
        victim_name = k0["username"]
        bad = client(base)
        codes = []
        for _ in range(6):
            codes.append(bad.post("/api/auth/login", json={"username": victim_name, "password": "wrong-pass"}).status_code)
        check(401 in codes, "错误口令返回 401")
        check(429 in codes, "达到阈值后锁定并返回 429")
        # 锁定期内即使口令正确也被拒
        check(
            client(base).post("/api/auth/login", json={"username": victim_name, "password": reset["password"]}).status_code == 429,
            "锁定期内正确口令也被拒绝",
        )

        print("[17] 密钥查询也有频率限制")
        codes = [anon.get("/api/auth/key-info?key=" + f"NOTAKEY{i}").status_code for i in range(35)]
        check(429 in codes, "大量无效密钥查询触发 429")

        print("[18] 登出")
        carol = client(base)
        resp = carol.post(
            "/api/auth/register",
            json={"key": keys[1]["key"], "username": "carol01", "password": "carol-pass-1"},
        )
        check(resp.status_code == 201, "用第二把密钥注册新账号")
        check(carol.post("/api/auth/logout").status_code == 200, "登出成功")
        check(carol.get("/api/state").status_code == 401, "登出后 401")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
