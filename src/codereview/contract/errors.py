# -*- coding: utf-8 -*-
"""统一错误码：{code, message, hint}，HTTP 状态与 code 一一对应（表 3-31）。"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    BAD_REQUEST = "E4001"
    UNAUTHORIZED = "E4010"
    FORBIDDEN = "E4030"
    NOT_FOUND = "E4041"
    CONFLICT = "E4090"
    RATE_LIMITED = "E4290"
    TIMEOUT = "E5041"
    INTERNAL = "E5000"


HTTP_STATUS = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.TIMEOUT: 504,
    ErrorCode.INTERNAL: 500,
}


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.code]

    def to_body(self) -> dict:
        return {"code": self.code.value, "message": self.message, "hint": self.hint}
