# -*- coding: utf-8 -*-
"""审查任务相关 6 个接口。"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse

from codereview.api.envelope import envelope
from codereview.contract.errors import ApiError, ErrorCode
from codereview.infra import db, repo

router = APIRouter(prefix="/api/v1", tags=["reviews"])


def _conn():
    return db.init(os.environ.get("CODEREVIEW_DB", ":memory:"))


@router.post("/reviews", status_code=202)
def create_review(payload: dict, request: Request):
    repo_name = payload.get("repo")
    git_ref = payload.get("git_ref")
    if not repo_name or not git_ref:
        raise ApiError(ErrorCode.BAD_REQUEST, "repo 与 git_ref 必填",
                       "示例：{repo:/'cs24107/CodeReviewAI', git_ref:/'abc1234'}")
    run_id = str(uuid.uuid4())
    conn = _conn()
    try:
        repo.insert_run(conn, {
            "run_id": run_id, "repo": repo_name, "git_ref": git_ref,
            "commit_sha": payload.get("commit_sha", "0" * 40),
            "status": "queued", "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "counts": {"blocking": 0, "warning": 0, "info": 0, "total": 0},
            "findings": [],
        })
    finally:
        conn.close()
    return envelope({"run_id": run_id, "status": "queued"},
                    getattr(request.state, "trace_id", ""))


@router.get("/reviews")
def list_reviews(request: Request, page: int = Query(1, ge=1),
                 size: int = Query(20, ge=1),
                 cursor: str | None = Query(None, description="上一页返回的 next_cursor"),
                 level: str | None = None, repo_name: str | None = Query(None, alias="repo")):
    conn = _conn()
    try:
        data = repo.list_runs(conn, page=page, size=size, level=level, repo=repo_name,
                              cursor=cursor)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.get("/reviews/{run_id}")
def get_review(run_id: str, request: Request):
    conn = _conn()
    try:
        data = repo.get_run(conn, run_id)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.get("/reviews/{run_id}/findings")
def get_findings(run_id: str, request: Request, page: int = Query(1, ge=1),
                 size: int = Query(50, ge=1), level: str | None = None):
    conn = _conn()
    try:
        data = repo.list_findings(conn, run_id, page=page, size=size, level=level)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.post("/reviews/{run_id}/rerun", status_code=202)
def rerun(run_id: str, request: Request):
    conn = _conn()
    try:
        old = repo.get_run(conn, run_id)
        new_id = str(uuid.uuid4())
        repo.insert_run(conn, {**old, "run_id": new_id, "status": "queued",
                               "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "findings": [], "counts": {"blocking": 0, "warning": 0, "info": 0, "total": 0}})
    finally:
        conn.close()
    return envelope({"run_id": new_id, "from": run_id},
                    getattr(request.state, "trace_id", ""))


@router.get("/reviews/{run_id}/export", response_class=PlainTextResponse)
def export(run_id: str, format: str = "json"):
    if format not in ("json", "sarif"):
        raise ApiError(ErrorCode.BAD_REQUEST, "format 只支持 json/sarif", "PDF 排在实验五")
    conn = _conn()
    try:
        data = repo.get_run(conn, run_id)
    finally:
        conn.close()
    if format == "json":
        return PlainTextResponse(json.dumps(data, ensure_ascii=False, indent=2))
    from codereview.cli.render import SarifRenderer
    from codereview.contract.models import Report
    return PlainTextResponse(SarifRenderer().render(Report(**data)))
