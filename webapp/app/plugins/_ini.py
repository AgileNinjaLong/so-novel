"""极简 INI 读写：只用于生成 so-novel 的单任务 config.ini。"""

from __future__ import annotations

import configparser
from pathlib import Path


def _new_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(
        interpolation=None,
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,
        strict=False,
    )
    parser.optionxform = str  # 保留键名大小写（hutool Setting 对大小写不敏感，但保持一致更清晰）
    return parser


def load(path: str | None) -> configparser.ConfigParser:
    parser = _new_parser()
    if path and Path(path).is_file():
        parser.read(path, encoding="utf-8")
    # 保证基础 section 存在
    for section in ("global", "download", "source", "crawl", "web", "cookie", "proxy"):
        if not parser.has_section(section):
            parser.add_section(section)
    return parser


def write_overrides(base_path: str | None, target_path: str, overrides: dict[str, dict[str, str]]) -> None:
    parser = load(base_path)
    for section, values in overrides.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in values.items():
            parser.set(section, key, str(value))
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as fp:
        parser.write(fp)
