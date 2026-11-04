# -*- coding: utf-8 -*-
"""CLI 三个子命令：run / config / report。

run 走完整链路：ParserFactory 选解析器 → RuleSet（模板方法）判定 →
Report（契约校验）→ Renderer（策略）输出 → 退出码三档。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

import typer

from codereview.cli.parser import ParserFactory
from codereview.cli.render import get_renderer
from codereview.contract.models import Finding, Report, Status
from codereview.infra import config as cfgmod
from codereview.infra import db as dbmod
from codereview.infra import repo as repomod
from codereview.infra.ruleset import RULESETS, PyRuleSet

app = typer.Typer(add_completion=False, help="CodeReviewAI 命令行（C 线）")


def _collect(path: str) -> list[dict]:
    units: list[dict] = []
    if os.path.isfile(path):
        paths = [path]
    else:
        paths = [os.path.join(dp, f) for dp, _, fs in os.walk(path) for f in fs
                 if f.endswith((".py", ".js", ".ts", ".tsx"))]
    for p in sorted(paths):
        parser = ParserFactory.for_path(p)
        with open(p, encoding="utf-8", errors="replace") as fh:
            units.extend(parser.parse(p, fh.read()))
    return units


@app.command()
def run(path: str = typer.Argument(".", help="文件或目录"),
        fmt: str = typer.Option(None, "--format", "-f", help="text/json/sarif"),
        fail_on: str = typer.Option(None, "--fail-on", help="blocking/warning/none"),
        save: bool = typer.Option(False, "--save", help="写入报告库"),
        out: str = typer.Option(None, "--out", help="另存到文件")):
    """跑一次审查，按退出码判定是否阻断。"""
    t0 = time.perf_counter()
    conf, sources = cfgmod.load(os.path.dirname(os.path.abspath(path)) if os.path.isdir(path) else os.path.dirname(os.path.abspath(path)),
                                {"format": fmt, "fail_on": fail_on})
    units = _collect(path)
    findings = RULESETS[PyRuleSet.name].run(units)
    counts = PyRuleSet.counts_of(findings)
    report = Report(
        run_id=str(uuid.uuid4()), repo="cs24107/CodeReviewAI", git_ref="working-tree",
        commit_sha="0" * 40, status=Status.done,
        started_at=datetime.now(timezone.utc),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        counts=counts, kinds=sorted({f.rule_kind for f in findings}), findings=findings,
    )
    text = get_renderer(conf["format"]).render(report)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    if save:
        conn = dbmod.init()
        repomod.insert_run(conn, report.model_dump(mode="json"))
        conn.close()
    else:
        typer.echo(text)
    typer.echo(f"-- 配置来源：{' → '.join(sources)}；耗时 {report.duration_ms} ms；"
               f"{len(units)} 行、{counts.total} 条", err=True)
    raise typer.Exit(cfgmod.exit_code(report.model_dump(), conf["fail_on"]))


@app.command()
def config(path: str = typer.Argument(".")):
    """打印三级合并后的配置与来源。"""
    conf, sources = cfgmod.load(path)
    typer.echo(json.dumps({"config": conf, "sources": sources}, ensure_ascii=False, indent=2))


@app.command()
def report(run_id: str, fmt: str = typer.Option("text", "--format", "-f"),
           db_path: str = typer.Option(None, "--db")):
    """从库里取一份已有报告并重新渲染。"""
    conn = dbmod.init(db_path)
    data = repomod.get_run(conn, run_id)
    conn.close()
    typer.echo(get_renderer(fmt).render(Report(**data)))


if __name__ == "__main__":
    app()
