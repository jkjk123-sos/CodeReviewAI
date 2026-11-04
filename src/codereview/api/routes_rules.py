# -*- coding: utf-8 -*-
"""规则相关 3 个接口。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request

from codereview.api.envelope import envelope
from codereview.contract.errors import ApiError, ErrorCode
from codereview.infra import db, repo

router = APIRouter(prefix="/api/v1", tags=["rules"])

EXAMPLES = {
    "PY-MUTABLE-DEFAULT": ["def add(item, bucket=[]):  # 反例", "def add(item, bucket=None):  # 正例"],
    "PY-BARE-EXCEPT": ["try://n    f()\nexcept:  # 反例\n    pass", "except OSError as e:  # 正例"],
    "PY-HARDCODED-SECRET": ["token = 'abc123'  # 反例", "token = os.environ['TOKEN']  # 正例"],
}


def _conn():
    return db.init(os.environ.get("CODEREVIEW_DB", ":memory:"))


@router.get("/rules")
def list_rules(request: Request, lang: str | None = None, level: str | None = None):
    conn = _conn()
    try:
        data = repo.list_rules(conn, lang=lang, level=level)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.get("/rules/{rule}")
def get_rule(rule: str, request: Request):
    conn = _conn()
    try:
        data = repo.get_rule(conn, rule)
    finally:
        conn.close()
    return envelope(data, getattr(request.state, "trace_id", ""))


@router.get("/rules/{rule}/examples")
def get_examples(rule: str, limit: int = 5):
    if rule not in EXAMPLES:
        raise ApiError(ErrorCode.NOT_FOUND, f"{rule} 没有示例", "GET /api/v1/rules 看可用规则")
    return envelope({"rule": rule, "items": EXAMPLES[rule][:limit]})
