# -*- coding: utf-8 -*-
"""报告契约：11 个顶层字段 + finding 7 字段 + 三条校验（实验二 §4.5 的代码落实）。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Level(str, Enum):
    blocking = "blocking"
    warning = "warning"
    info = "info"


class Status(str, Enum):
    queued = "queued"
    parsing = "parsing"
    judging = "judging"
    rendering = "rendering"
    persisting = "persisting"
    done = "done"
    partial = "partial"
    failed = "failed"


class StatusReason(str, Enum):
    parse_failed = "parse_failed"
    engine_timeout = "engine_timeout"
    db_unavailable = "db_unavailable"


class Finding(BaseModel):
    rule: str = Field(min_length=1, max_length=64)
    rule_kind: str = Field(min_length=1, max_length=64)
    level: Level
    file_path: str = Field(min_length=1)
    line_start: int = Field(gt=0)
    line_end: Optional[int] = None
    message: str = Field(min_length=1, max_length=500)
    suggestion: Optional[str] = None
    fixable: bool = False
    fingerprint: Optional[str] = Field(default=None, min_length=32, max_length=32)

    @model_validator(mode="after")
    def _line_order(self) -> "Finding":
        if self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end 不能小于 line_start")
        return self


class Counts(BaseModel):
    blocking: int = Field(default=0, ge=0)
    warning: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class Report(BaseModel):
    """报告本体。字段顺序与表 3-30（11 个顶层字段）一致。"""

    schema_version: Literal["2.0"] = "2.0"
    run_id: str
    repo: str
    git_ref: str
    commit_sha: str = Field(min_length=40, max_length=40)
    status: Status
    status_reason: Optional[StatusReason] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    counts: Counts
    kinds: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)

    # V-01：三个数加起来必须等于 total
    @model_validator(mode="after")
    def _v01_total(self) -> "Report":
        c = self.counts
        if c.blocking + c.warning + c.info != c.total:
            raise ValueError("V-01 失败：blocking+warning+info != total")
        if self.findings and len(self.findings) != c.total:
            raise ValueError("V-01 失败：findings 条数与 total 不一致")
        return self

    # V-02：kinds 必须是 findings 里 rule_kind 的去重集合
    @model_validator(mode="after")
    def _v02_kinds(self) -> "Report":
        actual = {f.rule_kind for f in self.findings}
        if set(self.kinds) != actual:
            raise ValueError("V-02 失败：kinds 与 findings 的 rule_kind 去重不一致")
        return self

    # V-03：partial 时 findings 可为空；done 时不得为 null（有默认空列表即满足）
    @model_validator(mode="after")
    def _v03_partial(self) -> "Report":
        if self.status is Status.partial and self.status_reason is None:
            raise ValueError("V-03 失败：partial 必须带 status_reason")
        if self.status is Status.failed and self.status_reason is None:
            raise ValueError("V-03 失败：failed 必须带 status_reason")
        return self
