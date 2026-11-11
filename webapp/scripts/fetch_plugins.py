"""下载上游发布产物到本地运行目录（不编译源码，直接引用官方 Release）。

用法：
    python scripts/fetch_plugins.py                 # 按当前平台下载两个插件
    python scripts/fetch_plugins.py --plugins sonovel
    python scripts/fetch_plugins.py --platform linux --plugins tomato

产物布局（与 app/config.py 的默认路径一致）：
    <data>/plugins/sonovel/app.jar      so-novel CLI
    <data>/plugins/sonovel/config.ini   基础配置（每任务会再生成一份覆盖版）
    <data>/plugins/sonovel/rules/       书源规则（CLI 必需）
    <data>/plugins/tomato/bin/Tomato-Novel-Downloader[.exe]
    <data>/plugins/java/...             可选：便携 JRE 21（so-novel 需要 Java 21）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

UA = {"User-Agent": "novel-webapp-fetch"}
DATA_DIR = Path(os.environ.get("WEBAPP_DATA_DIR") or (Path(__file__).resolve().parent.parent / "data"))


def log(msg: str) -> None:
    print(msg, flush=True)


def api(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        log(f"  已存在，跳过下载：{dest.name}（{dest.stat().st_size / 1048576:.1f} MB）")
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    log(f"  下载 {url}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fp:
        total = int(resp.headers.get("Content-Length") or 0)
        read = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fp.write(chunk)
            read += len(chunk)
            if total:
                pct = read * 100 // total
                print(f"\r  {pct:3d}% ({read / 1048576:.1f}/{total / 1048576:.1f} MB)", end="", flush=True)
    print()
    tmp.replace(dest)
    return dest


def pick_asset(assets: list[dict], keywords: list[str]) -> dict | None:
    for asset in assets:
        name = asset["name"]
        if all(k in name for k in keywords):
            return asset
    return None


def fetch_sonovel(platform: str) -> None:
    log("[so-novel] 获取最新 Release")
    release = api("https://api.github.com/repos/freeok/so-novel/releases/latest")
    keywords = {
        "windows": ["sonovel-windows", ".tar.gz"],
        "linux": ["sonovel-linux_x64", ".tar.gz"],
        "linux-arm64": ["sonovel-linux_arm64", ".tar.gz"],
        "macos": ["sonovel-macos_arm64", ".tar.gz"],
    }.get(platform)
    if not keywords:
        raise SystemExit(f"不支持的平台：{platform}")
    asset = pick_asset(release["assets"], keywords)
    if asset is None:
        raise SystemExit(f"没有找到匹配的发布包（{keywords}），可用：{[a['name'] for a in release['assets']]}")

    work = DATA_DIR / "plugins" / "sonovel"
    work.mkdir(parents=True, exist_ok=True)
    archive = work / asset["name"]
    download(asset["browser_download_url"], archive)

    log("  解包（只取 app.jar / config.ini / rules / fonts）")
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(archive, "r:gz") as tar:
            members = [m for m in tar.getmembers() if m.isfile() or m.isdir()]
            for member in members:
                name = member.name.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    continue
                tar.extract(member, tmp, filter="data")
        root = _find_root(Path(tmp))
        wanted = ["app.jar", "config.ini", "rules", "fonts", "readme.txt", "DISCLAIMER.md"]
        for name in wanted:
            src = root / name
            if not src.exists():
                continue
            dst = work / name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        log(f"  完成：{work}（tag={release['tag_name']}）")
    try:
        archive.unlink()
    except OSError:
        pass


def _find_root(base: Path) -> Path:
    """发布包通常有单一顶层目录（如 SoNovel/），返回含 app.jar 的那一层。"""
    if (base / "app.jar").is_file():
        return base
    for child in base.iterdir():
        if child.is_dir() and (child / "app.jar").is_file():
            return child
    for child in base.iterdir():
        if child.is_dir():
            inner = _find_root(child)
            if (inner / "app.jar").is_file():
                return inner
    return base


def fetch_tomato(platform: str) -> None:
    log("[tomato] 获取最新 Release")
    release = api("https://api.github.com/repos/zhongbai2333/Tomato-Novel-Downloader/releases/latest")
    assets = release["assets"]
    tag = release["tag_name"]
    arch = os.environ.get("NOVEL_ARCH", "amd64")

    if platform == "windows":
        asset = pick_asset(assets, ["Win64", ".exe"]) or pick_asset(assets, ["WinArm64", ".exe"])
        bin_name = "Tomato-Novel-Downloader.exe"
    elif platform == "linux":
        keyword = "Linux_musl_amd64" if arch == "amd64" else "Linux_musl_arm64"
        asset = pick_asset(assets, [keyword, tag]) or pick_asset(assets, ["Linux_amd64", tag])
        bin_name = "Tomato-Novel-Downloader"
    else:
        raise SystemExit(f"不支持的平台：{platform}")
    if asset is None:
        raise SystemExit(f"没有找到匹配的番茄二进制，可用：{[a['name'] for a in assets]}")

    dest_dir = DATA_DIR / "plugins" / "tomato" / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / bin_name
    download(asset["browser_download_url"], dest)
    if not platform == "windows":
        dest.chmod(0o755)
    log(f"  完成：{dest}（tag={tag}）")


def fetch_java(platform: str) -> None:
    log("[java] 获取便携 JRE 21（仅在宿主机没有 Java 21 时需要）")
    arch = "aarch64" if os.environ.get("NOVEL_ARCH") == "arm64" else "x64"
    os_name = "windows" if platform == "windows" else "linux"
    data = api(
        f"https://api.adoptium.net/v3/assets/latest/21/hotspot"
        f"?architecture={arch}&image_type=jre&os={os_name}&vendor=eclipse"
    )
    pkg = data[0]["binary"]["package"]
    dest_dir = DATA_DIR / "plugins" / "java"
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / pkg["name"]
    download(pkg["link"], archive)
    log("  解包 JRE")
    if pkg["name"].endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest_dir)
    else:
        with tarfile.open(archive) as tar:
            tar.extractall(dest_dir, filter="data")
    for child in dest_dir.iterdir():
        if child.is_dir() and child.name.lower().startswith(("jdk-", "jre-")):
            java = child / "bin" / ("java.exe" if platform == "windows" else "java")
            if java.is_file() and platform != "windows":
                java.chmod(0o755)
            log(f"  完成：{java}")
            break
    try:
        archive.unlink()
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugins", default="sonovel,tomato", help="sonovel,tomato,all")
    parser.add_argument("--platform", default="windows" if sys.platform.startswith("win") else "linux")
    parser.add_argument("--with-java", action="store_true", help="同时下载便携 JRE 21")
    args = parser.parse_args()

    wanted = {p.strip() for p in args.plugins.split(",") if p.strip()}
    if "all" in wanted:
        wanted = {"sonovel", "tomato"}
    log(f"目标目录：{DATA_DIR}（平台：{args.platform}）")

    if "sonovel" in wanted:
        fetch_sonovel(args.platform)
    if "tomato" in wanted:
        fetch_tomato(args.platform)
    if args.with_java:
        fetch_java(args.platform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
