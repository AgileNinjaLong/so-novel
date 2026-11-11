"""准备离线构建所需的 vendor/ 目录（Linux 版上游产物）。

服务器访问 GitHub 慢或不通时，在能下载的机器上执行本脚本，把产物打包上传，
服务器再用 docker-compose.offline.yml 离线构建。

用法：
    # 1) 先下载两个 Linux 产物（可用镜像加速）
    curl -L -o sonovel-linux_x64.tar.gz \
      https://gh-proxy.com/https://github.com/freeok/so-novel/releases/download/v1.12.0/sonovel-linux_x64.tar.gz
    curl -L -o TomatoNovelDownloader-Linux_amd64-v2.4.16 \
      https://gh-proxy.com/https://github.com/zhongbai2333/Tomato-Novel-Downloader/releases/download/v2.4.16/TomatoNovelDownloader-Linux_amd64-v2.4.16

    # 2) 生成 vendor/
    python scripts/prepare_vendor.py --sonovel sonovel-linux_x64.tar.gz \
        --tomato TomatoNovelDownloader-Linux_amd64-v2.4.16

产物结构：
    vendor/sonovel/app.jar, vendor/sonovel/rules/...
    vendor/tomato/bin/Tomato-Novel-Downloader
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_jar_root(base: Path) -> Path | None:
    if (base / "app.jar").is_file():
        return base
    for child in base.rglob("app.jar"):
        return child.parent
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sonovel", required=True, help="sonovel-linux_*.tar.gz 路径")
    parser.add_argument("--tomato", required=True, help="TomatoNovelDownloader-Linux_* 可执行文件路径")
    parser.add_argument("--out", default=str(ROOT / "vendor"), help="输出目录（默认 webapp/vendor）")
    args = parser.parse_args()

    out = Path(args.out)
    sonovel_dir = out / "sonovel"
    tomato_bin = out / "tomato" / "bin"
    sonovel_dir.mkdir(parents=True, exist_ok=True)
    tomato_bin.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] 解包 so-novel：{args.sonovel}")
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(args.sonovel) as tar:
            tar.extractall(tmp, filter="data")
        root = find_jar_root(Path(tmp))
        if root is None:
            print("错误：压缩包里找不到 app.jar")
            return 1
        shutil.copytree(root, sonovel_dir, dirs_exist_ok=True)
        size_kb = (sonovel_dir / "app.jar").stat().st_size // 1024
        print(f"  → {sonovel_dir}（app.jar {size_kb} KB）")

    print(f"[2/3] 拷贝番茄二进制：{args.tomato}")
    target = tomato_bin / "Tomato-Novel-Downloader"
    shutil.copy2(args.tomato, target)
    # 加上可执行位（Windows 上拷贝也不影响 Docker 构建里的 chmod）
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  → {target}（{target.stat().st_size // 1024} KB）")

    print("[3/3] 校验")
    ok = (sonovel_dir / "app.jar").is_file() and (sonovel_dir / "rules").is_dir() and target.is_file()
    print(f"  app.jar={'OK' if (sonovel_dir / 'app.jar').is_file() else 'MISSING'} "
          f"rules={'OK' if (sonovel_dir / 'rules').is_dir() else 'MISSING'} "
          f"tomato={'OK' if target.is_file() else 'MISSING'}")
    print("完成。服务器上执行：docker compose -f docker-compose.offline.yml up -d --build" if ok
          else "失败：产物不完整")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
