# -*- coding: utf-8 -*-
"""三级配置合并：内置默认 → 仓库 .codereview.toml → 命令行参数。

覆盖顺序固定，且每次都把"谁覆盖了谁"记进 sources，写进 config_snapshot。
出问题时能回答"这个 fail_on 是哪来的"（Q-07 的整改）。
"""
from __future__ import annotations

import os
from typing import Any

DEFAULTS: dict[str, Any] = {
    "format": "text",
    "fail_on": "blocking",      # blocking | warning | none
    "timeout_s": 30,
    "max_findings": 500,
    "ignore": [],
    "rules": {},
}


def _parse_toml(text: str) -> dict:
    """极简 TOML 子集：key = value / [section] / key = ["a","b"]。"""
    import tomllib
    return tomllib.loads(text)


def load(repo_dir: str | None = None, cli_overrides: dict | None = None) -> tuple[dict, list[str]]:
    cfg = dict(DEFAULTS)
    sources = ["default"]
    if repo_dir:
        path = os.path.join(repo_dir, ".codereview.toml")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                cfg.update(_parse_toml(fh.read()))
            sources.append(f"repo:{os.path.basename(path)}")
    for k, v in (cli_overrides or {}).items():
        if v is not None:
            cfg[k] = v
            sources.append(f"cli:{k}")
    if cfg["fail_on"] not in ("blocking", "warning", "none"):
        raise ValueError(f"fail_on 非法：{cfg['fail_on']}")
    return cfg, sources


def exit_code(report: dict, fail_on: str) -> int:
    """退出码三档：0 通过 / 1 有阻断 / 2 工具自身失败（表 3-33）。"""
    if report["status"] == "failed":
        return 2
    if fail_on == "none":
        return 0
    if fail_on == "warning":
        return 1 if (report["counts"]["blocking"] or report["counts"]["warning"]) else 0
    return 1 if report["counts"]["blocking"] else 0
