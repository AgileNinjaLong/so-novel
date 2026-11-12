"""为搜索生成一份「剔除慢源」的规则文件（search.json）。

背景：so-novel 的聚合搜索会并行查询全部书源，总耗时≈最慢的那个源。
某些源从云服务器访问很慢（Cloudflare 或直接连不上），会把搜索结果拖到 10~30 秒。
把这类源从**搜索**用的规则里剔除（下载仍可用完整 main.json），搜索会快很多。

用法（在数据卷的 rules 目录下执行，或指定路径）：

    python scripts/trim_search_rules.py \
        --rules /data/plugins/sonovel/rules/main.json \
        --exclude biquge365.net 52bqg.com \
        --out /data/plugins/sonovel/rules/search.json

然后在环境变量里指定：SONOVEL_SEARCH_RULES=search.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_SLOW = ["biquge365.net", "52bqg.com"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", default="main.json", help="完整规则文件路径")
    parser.add_argument("--out", default="search.json", help="输出的搜索专用规则文件")
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=DEFAULT_SLOW,
        help=f"要剔除的域名片段（默认：{' '.join(DEFAULT_SLOW)}）",
    )
    args = parser.parse_args()

    src = Path(args.rules)
    if not src.is_file():
        print(f"规则文件不存在：{src}")
        return 1

    data = json.loads(src.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else list(data.values())

    kept, dropped = [], []
    for item in items:
        url = str((item or {}).get("url", ""))
        name = (item or {}).get("name", "?")
        if any(frag in url for frag in args.exclude):
            dropped.append((name, url))
        else:
            kept.append(item)

    Path(args.out).write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"保留 {len(kept)} 个来源 → {args.out}")
    for name, url in dropped:
        print(f"  剔除：{name} ({url})")
    print("保留：", "、".join(str(i.get("name", "?")) for i in kept))
    print("\n记得设置环境变量：SONOVEL_SEARCH_RULES=search.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
