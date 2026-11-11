"""黑盒测试：真实 HTTP 服务上的密钥注册 / 登录 / 权限 / 后台管理。

覆盖：
- 未登录无法进入界面（页面 303，接口 401）
- 没有未使用密钥时，注册关闭且注册接口 403
- 一钥一用户：开放型注册后密钥失效、重复使用 403
- 绑定型：预置账号密码出现在 key-info 与后台，兑换后可直接用该密码登录
- 管理员按 1/31/124/372/999999 天叠加；999999 变永久
- 被禁用用户会话立刻失效；普通用户无法访问后台
- 密钥撤销/清空、管理员重置密码
- 登出后会话失效、错误口令 401、连续失败 429

运行：python tests/test_auth_blackbox.py
"""

from __future__ import annotations

import sys
import uuid
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


def make_keys(admin, **kwargs):
    return body(admin.post("/api/admin/keys", json=kwargs))["keys"]


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
        check(anon.get("/api/auth/key-info?key=nope").json()["valid"] is False, "密钥查询可匿名访问")

        print("[2] 没有未使用密钥：注册关闭")
        meta = body(anon.get("/api/meta"))
        check(meta["app"]["registration_open"] is False, "meta 显示注册关闭")
        resp = anon.post(
            "/api/auth/register",
            json={"key": "NOT-A-KEY", "username": unique_name(), "password": "password123"},
        )
        check(resp.status_code == 403, "无有效密钥注册 403")

        print("[3] 管理员登录与后台总览")
        admin = client(base)
        check(
            admin.post("/api/auth/login", json={"username": "root", "password": "admin-pass-123"}).status_code
            == 200,
            "管理员登录成功",
        )
        me = body(admin.get("/api/auth/me"))["user"]
        check(me["role"] == "admin" and me["permanent"] is True, "管理员角色正确且永久")
        overview = body(admin.get("/api/admin/overview"))
        check(overview["user_count"] == 1, "初始只有管理员")
        check(overview["keys"] == [], "初始没有密钥")
        check(overview["grant_presets"] == [1, 31, 124, 372, 999999], "档位与需求一致")

        print("[4] 生成开放型密钥（372 天）→ 注册开放")
        keys = make_keys(admin, days=372, count=2, mode="open")
        check(len(keys) == 2, "一次生成 2 把")
        check(len({k["key"] for k in keys}) == 2, "两把互不相同")
        check(all(k["status"] == "unused" and k["days_text"] == "372 天" for k in keys), "状态与天数正确")
        meta = body(anon.get("/api/meta"))
        check(meta["app"]["registration_open"] is True, "meta 显示注册开放")
        check(meta["app"]["unused_keys"] == 2, "剩余可用密钥 2 把")

        print("[5] 一钥一用户：注册成功且密钥立即失效")
        info = body(anon.get("/api/auth/key-info?key=" + keys[0]["key"]))
        check(info["valid"] and info["mode"] == "open", "key-info 返回开放型")
        name = unique_name("alice")
        user_a = client(base)
        resp = user_a.post(
            "/api/auth/register",
            json={"key": keys[0]["key"], "username": name, "password": "password123"},
        )
        check(resp.status_code == 201, "注册成功")
        user_data = body(resp)["user"]
        check(user_data["username"] == name, "账号名为填写的用户名")
        check(user_data["remaining_days"] == 372, "有效期来自密钥（372 天）")
        check(user_data["active"] is True, "注册即可用")
        again = anon.post(
            "/api/auth/register",
            json={"key": keys[0]["key"], "username": unique_name(), "password": "password123"},
        )
        check(again.status_code == 403, "同一把密钥不能再用")
        key_info_after = body(anon.get("/api/auth/key-info?key=" + keys[0]["key"]))
        check(key_info_after["valid"] is False, "已用密钥查询为不可用")

        print("[6] 绑定型密钥：预置账号密码可见、可直接登录")
        bound = make_keys(admin, days=31, mode="bound", username=unique_name("bob"), password="bobby-pass-1")
        bk = bound[0]
        check(bk["mode"] == "bound" and bk["username"].startswith("bob"), "绑定型带回预置账号")
        check(bk["password"] == "bobby-pass-1", "后台列表能看到预置密码")
        info = body(anon.get("/api/auth/key-info?key=" + bk["key"]))
        check(info["mode"] == "bound" and info["username"] == bk["username"] and info["password"] == "bobby-pass-1",
              "注册页能显示预置账号密码")
        bob = client(base)
        resp = bob.post("/api/auth/register", json={"key": bk["key"]})
        check(resp.status_code == 201, "绑定型密钥可直接注册")
        check(body(resp)["user"]["username"] == bk["username"], "账号即预置用户名")
        check(body(resp)["user"]["remaining_days"] == 31, "有效期 31 天")
        check(bob.post("/api/auth/login", json={"username": bk["username"], "password": "bobby-pass-1"}).status_code == 200,
              "预置密码可登录")
        bob.post("/api/auth/register", json={"key": bk["key"]})
        check(body(anon.get("/api/auth/key-info?key=" + bk["key"]))["valid"] is False, "绑定型密钥同样单次使用")

        print("[7] 管理员可见密钥状态与使用者")
        keys_now = body(admin.get("/api/admin/keys"))["keys"]
        used = [k for k in keys_now if k["status"] == "used"]
        check(len(used) >= 2, "已使用的密钥被标记")
        check(any(k["used_by_name"] == name for k in used), "记录了使用者")
        check(body(admin.get("/api/admin/keys"))["stats"]["unused"] >= 1, "统计含未使用数量")

        print("[8] 有效期叠加 / 永久 / 非法档位")
        uid = user_data["id"]
        r = body(admin.post(f"/api/admin/users/{uid}/grant", json={"days": 1}))["user"]
        check(r["remaining_days"] == 373, "372 + 1 = 373 天（叠加）")
        r = body(admin.post(f"/api/admin/users/{uid}/grant", json={"days": 999999}))["user"]
        check(r["permanent"] is True and r["remaining_days"] is None, "999999 → 永久")
        check(admin.post(f"/api/admin/users/{uid}/grant", json={"days": 7}).status_code == 400, "非法档位 400")

        print("[9] 权限矩阵：普通用户不能进后台、不能动别人的任务")
        check(user_a.get("/api/admin/overview").status_code == 403, "用户访问后台 403")
        check(user_a.post("/api/admin/keys", json={"days": 1}).status_code == 403, "用户生成密钥 403")
        check(user_a.post(f"/api/admin/users/{uid}/grant", json={"days": 1}).status_code == 403, "用户给自己加时长 403")

        print("[10] 注册后能提交下载（测试环境无插件 → 409 来源不可用）")
        resp = user_a.post(
            "/api/tasks",
            json={"source": "sonovel", "title": "t", "book_ref": "r", "fmt": "txt"},
        )
        check(resp.status_code == 409, "通过权限校验（被来源未就绪拦截）")

        print("[11] 删除密钥与撤销")
        fresh = make_keys(admin, days=1, count=1, mode="open")[0]
        check(admin.delete(f"/api/admin/keys/{fresh['id']}?hard=1").status_code == 200, "硬删除密钥记录")
        check(body(anon.get("/api/auth/key-info?key=" + fresh["key"]))["valid"] is False, "删除后不可用")
        fresh2 = make_keys(admin, days=1, count=1, mode="open")[0]
        check(admin.delete(f"/api/admin/keys/{fresh2['id']}").status_code == 200, "撤销未使用密钥")
        resp = anon.post(
            "/api/auth/register",
            json={"key": fresh2["key"], "username": unique_name(), "password": "password123"},
        )
        check(resp.status_code == 403, "撤销后注册 403")

        print("[12] 管理员重置密码")
        reset = body(admin.post(f"/api/admin/users/{uid}/password"))
        check(len(reset["password"]) >= 8, "返回新密码")
        check(user_a.get("/api/state").status_code == 401, "重置后原会话失效")
        check(
            client(base).post("/api/auth/login", json={"username": name, "password": reset["password"]}).status_code == 200,
            "新密码可登录",
        )

        print("[13] 禁用用户 → 登录被拒、既有会话立即失效")
        victim = client(base)
        check(
            victim.post("/api/auth/login", json={"username": name, "password": reset["password"]}).status_code == 200,
            "禁用前可登录（持有会话）",
        )
        check(admin.post(f"/api/admin/users/{uid}/status", json={"status": "banned"}).status_code == 200, "禁用成功")
        check(victim.get("/api/state").status_code == 401, "禁用后原有会话立即失效")
        check(
            client(base).post("/api/auth/login", json={"username": name, "password": reset["password"]}).status_code == 403,
            "禁用后无法再登录",
        )

        print("[14] 管理员不能禁用/删除自己")
        admin_id = body(admin.get("/api/auth/me"))["user"]["id"]
        check(admin.post(f"/api/admin/users/{admin_id}/status", json={"status": "banned"}).status_code == 400, "不能禁用自己")
        check(admin.delete(f"/api/admin/users/{admin_id}").status_code == 400, "不能删除自己")

        print("[15] 绑定的预置用户名冲突")
        taken = bk["username"]
        resp = admin.post(
            "/api/admin/keys",
            json={"days": 1, "mode": "bound", "username": taken, "password": "password123"},
        )
        check(resp.status_code == 409, "预置用户名已存在时 409")

        print("[16] 登出与限流")
        check(bob.post("/api/auth/logout").status_code == 200, "登出成功")
        check(bob.get("/api/state").status_code == 401, "登出后 401")
        bad = client(base)
        check(bad.post("/api/auth/login", json={"username": "root", "password": "wrong-pass"}).status_code == 401, "错误口令 401")
        codes = [bad.post("/api/auth/login", json={"username": "root", "password": "x"}).status_code for _ in range(9)]
        check(429 in codes, "连续失败触发 429 限流")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
