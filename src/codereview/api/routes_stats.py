# -*- coding: utf-8 -*-
"""统计相关 3 个接口。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Query, Request

from codereview.api.envelope import envelope
from codereview.infra import db, repo

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


def _conn():
    return db.init(os.environ.get("CODEREVIEW_DB", ":memory:"))


@router.get("/summary")
def summary(request: Request):
    conn = _conn()
    try:
        data = repo.stats_summary(conn)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.get("/trend")
def trend(request: Request, weeks: int = Query(8, ge=1, le=52)):
    conn = _conn()
    try:
        data = repo.stats_trend(conn, weeks=weeks)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.get("/by-rule")
def by_rule(request: Request, top: int = Query(10, ge=1, le=50)):
    conn = _conn()
    try:
        data = repo.stats_by_rule(conn, top=top)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))
