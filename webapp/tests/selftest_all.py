"""总自测：依次跑完所有模块的测试，并输出一张结果矩阵。

用法：
    python tests/selftest_all.py                 # 单元 + 黑盒 + 服务端 API 检查
    python tests/selftest_all.py --live          # 额外跑真实环境测试（需服务已启动）
    python tests/selftest_all.py --live --url http://127.0.0.1:8099

会运行：
  单元：test_security / test_validity / test_throttle / test_keys / test_scheduler
  黑盒：test_auth_blackbox（进程内起真实 HTTP 服务）
  真实环境（--live）：e2e_live（密钥注册/搜索/下载/接收/暂停）+ test_receive_browser（浏览器接收）
  接口探针：健康检查、静态资源、页面路由、未登录拦截、未知路径 404
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

try:  # Windows 控制台默认 GBK，避免 emoji/箭头导致编码异常
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UNIT_SUITES = [
    ("安全：nanoid/口令/令牌", "test_security.py"),
    ("有效期：叠加/封顶/永久", "test_validity.py"),
    ("抗暴力破解：计数/锁定/持久化", "test_throttle.py"),
    ("密钥：一钥一账号/绑定/单次", "test_keys.py"),
    ("日志隔离：任务日志不串台", "test_log_filter.py"),
    ("搜索服务：并发限流与缓存", "test_searchsvc.py"),
    ("调度器：单线程/切换/交付/TTL/删除", "test_scheduler.py"),
]
BLACKBOX_SUITES = [
    ("认证与后台：真实 HTTP 黑盒", "test_auth_blackbox.py"),
]
LIVE_SUITES = [
    ("真实环境：注册/搜索/下载/暂停", "e2e_live.py"),
    ("真实上游：连续两本不串台", "test_title_stability.py"),
    ("浏览器接收：落盘 + ack 删除", "test_receive_browser.py"),
    ("界面删除：勾选批量/单条/后台分组", "test_delete_ui.py"),
]


def run_suite(name: str, filename: str, env: dict[str, str]) -> tuple[bool, float, str]:
    started = time.time()
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / filename)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    elapsed = time.time() - started
    tail = ""
    for line in proc.stdout.splitlines():
        if line.strip():
            tail = line.strip()
    if proc.returncode != 0:
        tail = tail or (proc.stderr.splitlines()[-1] if proc.stderr else "未知错误")
    return proc.returncode == 0, elapsed, tail


def probe(base: str) -> list[tuple[str, bool, str]]:
    """对运行中的服务做一组快速接口探针。"""
    results: list[tuple[str, bool, str]] = []
    client = httpx.Client(base_url=base, timeout=10, follow_redirects=False)
    try:
        r = client.get("/healthz")
        results.append(("健康检查 /healthz", r.status_code == 200, f"HTTP {r.status_code}"))

        r = client.get("/login")
        results.append(("登录页可访问", r.status_code == 200, f"HTTP {r.status_code}"))
        r = client.get("/register")
        results.append(("注册页可访问", r.status_code == 200, f"HTTP {r.status_code}"))

        r = client.get("/static/app.js")
        results.append(("前端脚本可加载", r.status_code == 200 and len(r.content) > 1000,
                        f"HTTP {r.status_code} {len(r.content)}B"))
        r = client.get("/static/style.css")
        results.append(("样式表可加载", r.status_code == 200 and len(r.content) > 500,
                        f"HTTP {r.status_code} {len(r.content)}B"))

        r = client.get("/")
        results.append(("未登录访问首页被拦截", r.status_code in (303, 401), f"HTTP {r.status_code}"))
        r = client.get("/api/state")
        results.append(("未登录访问队列被拒", r.status_code == 401, f"HTTP {r.status_code}"))
        r = client.get("/api/admin/overview")
        results.append(("未登录访问后台被拒", r.status_code == 401, f"HTTP {r.status_code}"))

        r = client.get("/definitely-not-exist")
        # 未登录时未匹配路径会被登录门禁重定向（303）或直接 401，两种都算正确拦截
        results.append(
            ("未登录未知路径被拦截", r.status_code in (303, 401, 404), f"HTTP {r.status_code}")
        )

        # 登录后再测真正的 404
        login = httpx.Client(base_url=base, timeout=10, follow_redirects=True)
        try:
            login.post(
                "/api/auth/login",
                json={
                    "username": os.environ.get("ADMIN_USERNAME", "root"),
                    "password": os.environ.get("ADMIN_PASSWORD", "admin-pass-123"),
                },
            )
            r404 = login.get("/definitely-not-exist")
            results.append(("已登录未知路径返回 404", r404.status_code == 404, f"HTTP {r404.status_code}"))
        finally:
            login.close()

        meta = client.get("/api/meta").json()
        results.append(("meta 暴露密钥库存", "unused_keys" in meta.get("app", {}),
                        f"unused={meta.get('app', {}).get('unused_keys')}"))
        results.append(("meta 暴露接收时限", "file_ttl_min" in meta.get("app", {}),
                        f"ttl={meta.get('app', {}).get('file_ttl_min')} 分钟"))
        plugins = meta.get("plugins", [])
        results.append(("两个来源插件已注册", len(plugins) >= 2, f"{len(plugins)} 个"))
    finally:
        client.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="额外运行真实环境测试")
    parser.add_argument("--url", default=os.environ.get("WEBAPP_URL", "http://127.0.0.1:8099"))
    args = parser.parse_args()

    env = dict(os.environ)
    env.setdefault("WEBAPP_URL", args.url)

    rows: list[tuple[str, bool, float, str]] = []
    print("=" * 68)
    print("小说下载 WebUI · 总自测")
    print("=" * 68)

    for name, filename in UNIT_SUITES + BLACKBOX_SUITES:
        print(f">> {name} ({filename}) ...", flush=True)
        ok, elapsed, tail = run_suite(name, filename, env)
        rows.append((name, ok, elapsed, tail))
        print(f"  {'PASS' if ok else 'FAIL'}  {elapsed:.1f}s  {tail[:70]}")

    if args.live:
        reachable = False
        try:
            reachable = httpx.get(args.url.rstrip("/") + "/healthz", timeout=5).status_code == 200
        except Exception:
            reachable = False
        if not reachable:
            print(f">> 跳过真实环境测试：{args.url} 不可达")
        else:
            for name, filename in LIVE_SUITES:
                print(f">> {name} ({filename}) ...", flush=True)
                ok, elapsed, tail = run_suite(name, filename, env)
                rows.append((name, ok, elapsed, tail))
                print(f"  {'PASS' if ok else 'FAIL'}  {elapsed:.1f}s  {tail[:70]}")

    if args.live:
        print(">> 接口探针 ...", flush=True)
        try:
            for label, ok, detail in probe(args.url.rstrip("/")):
                rows.append((label, ok, 0.0, detail))
                print(f"  {'PASS' if ok else 'FAIL'}  {label}: {detail}")
        except Exception as exc:
            rows.append(("接口探针", False, 0.0, str(exc)))
            print(f"  FAIL  接口探针异常：{exc}")

    print()
    print("=" * 68)
    passed = sum(1 for _, ok, _, _ in rows if ok)
    print(f"结果：{passed}/{len(rows)} 通过")
    for name, ok, elapsed, tail in rows:
        assert_time = f"{elapsed:5.1f}s" if elapsed else "   probe"
        print(f"  [{'PASS' if ok else 'FAIL'}] {assert_time}  {name}")
    print("=" * 68)
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
