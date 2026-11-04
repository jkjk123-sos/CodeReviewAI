# -*- coding: utf-8 -*-
"""策略模式：报告格式化。

三个实现共用 Report，输出形态不同；调用方只认 Renderer 接口。
加一种格式 = 加一个类 + 注册一行，调用方零改动（图 3-9 的落点）。
"""
from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

from codereview.contract.models import Report


@runtime_checkable
class Renderer(Protocol):
    name: str

    def render(self, report: Report) -> str:  # pragma: no cover - 协议声明
        ...


class TextRenderer:
    name = "text"

    def render(self, report: Report) -> str:
        c = report.counts
        head = f"[{report.status.value}] {report.repo}@{report.git_ref[:12]}  " \
               f"{c.blocking} 阻断 / {c.warning} 警告 / {c.info} 提示"
        if report.status.value == "partial":
            head += f"  ({report.status_reason.value if report.status_reason else '-'})"
        lines = [head]
        by_kind: dict[str, list] = {}
        for f in report.findings:
            by_kind.setdefault(f.rule_kind, []).append(f)
        for kind, items in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"  {kind}（{len(items)}）")
            for f in items[:5]:
                path = f.file_path if len(f.file_path) <= 48 else "…" + f.file_path[-47:]
                lines.append(f"    {path}:{f.line_start}  [{f.rule}] {f.message}")
            if len(items) > 5:
                lines.append(f"    … 另 {len(items) - 5} 条")
        return "\n".join(lines)


class JsonRenderer:
    name = "json"

    def render(self, report: Report) -> str:
        return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)


class SarifRenderer:
    """SARIF 2.1.0 最小可用子集：满足 CI 插件消费，不做规则全量描述。"""
    name = "sarif"

    def render(self, report: Report) -> str:
        results = []
        for f in report.findings:
            results.append({
                "ruleId": f.rule,
                "level": {"blocking": "error", "warning": "warning", "info": "note"}[f.level.value],
                "message": {"text": f.message},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.file_path},
                        "region": {"startLine": f.line_start,
                                   **({"endLine": f.line_end} if f.line_end else {})},
                    }
                }],
            })
        doc = {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{
                "tool": {"driver": {"name": "codereview", "version": "0.3.0",
                                    "rules": [{"id": k} for k in sorted(report.kinds)]}},
                "results": results,
            }],
        }
        return json.dumps(doc, ensure_ascii=False, indent=2)


RENDERERS: dict[str, Renderer] = {
    TextRenderer.name: TextRenderer(),
    JsonRenderer.name: JsonRenderer(),
    SarifRenderer.name: SarifRenderer(),
}


def get_renderer(fmt: str) -> Renderer:
    try:
        return RENDERERS[fmt]
    except KeyError:
        raise KeyError(f"未知格式 {fmt}，可选 {sorted(RENDERERS)}") from None
