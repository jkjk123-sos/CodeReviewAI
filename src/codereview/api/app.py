# -*- coding: utf-8 -*-
"""FastAPI 装配：13 个路由 + 统一错误出口 + healthz。

响应体统一 {code,message,data,traceId,timestamp}（表 3-31），
错误走 exception_handler，路由里不写 try/except。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from codereview.api import routes_reviews, routes_rules, routes_stats
from codereview.api.envelope import envelope
from codereview.contract.errors import ApiError
from codereview.infra import db

_STATIC = Path(__file__).parent / "static"

# 关掉 FastAPI 自带的 /docs：它从 cdn.jsdelivr.net 拉 Swagger 资源，
# 而该域名在部分校园网/企业网里 TLS 握手会被中断，页面只剩白屏。
# 改用本地资源，见下面的 /docs 与 /ui。
app = FastAPI(title="CodeReviewAI C 线 API", version="1.0.0",
              docs_url=None, redoc_url=None)


@app.middleware("http")
async def add_trace(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    body = exc.to_body()
    body.update({"data": None, "traceId": getattr(request.state, "trace_id", ""),
                 "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return JSONResponse(status_code=exc.http_status, content=body)


@app.get("/healthz")
def healthz():
    conn = db.init(os.environ.get("CODEREVIEW_DB", ":memory:"))
    try:
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    finally:
        conn.close()
    return {"status": "ok" if db_ok else "degraded",
            "deps": {"db": "up" if db_ok else "down", "engine": "up" if os.environ.get("ENGINE", "local") == "local" else "unknown"},
            "version": app.version}


app.include_router(routes_reviews.router)
app.include_router(routes_rules.router)
app.include_router(routes_stats.router)


# —— 本地接口页面 ——
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/docs", include_in_schema=False)
def docs_page():
    """Swagger UI，资源全部本地化，不依赖 CDN。"""
    return HTMLResponse((_STATIC / "docs.html").read_text(encoding="utf-8"))


@app.get("/ui", include_in_schema=False)
def ui_console():
    """轻量控制台：零外部依赖，直读 openapi.json 渲染。"""
    return HTMLResponse((_STATIC / "ui.html").read_text(encoding="utf-8"))
