# -*- coding: utf-8 -*-
"""统一响应外壳：{code,message,data,traceId,timestamp}（表 3-31）。"""
from __future__ import annotations

from datetime import datetime, timezone


def envelope(data, trace_id: str = "") -> dict:
    return {"code": "OK", "message": "", "data": data, "traceId": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
