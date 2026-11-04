import pytest
from pydantic import ValidationError

from codereview.contract.models import Counts, Finding, Report, Status, StatusReason

BASE = dict(run_id="r1", repo="cs24107/CodeReviewAI", git_ref="main",
            commit_sha="a" * 40, status=Status.done,
            started_at="2026-12-01T10:00:00+08:00")


def f(level="blocking", kind="可变默认参数"):
    return Finding(rule="R", rule_kind=kind, level=level, file_path="a.py",
                   line_start=1, message="m")


def test_v01_total_mismatch():
    with pytest.raises(ValidationError, match="V-01"):
        Report(**BASE, counts=Counts(blocking=1, total=2), findings=[f()])


def test_v02_kinds_mismatch():
    with pytest.raises(ValidationError, match="V-02"):
        Report(**BASE, counts=Counts(blocking=1, total=1), findings=[f()], kinds=["别的类"])


def test_v03_partial_needs_reason():
    with pytest.raises(ValidationError, match="V-03"):
        Report(**{**BASE, "status": Status.partial},
               counts=Counts(), findings=[], kinds=[])


def test_v03_partial_with_reason_ok():
    r = Report(**{**BASE, "status": Status.partial,
                  "status_reason": StatusReason.engine_timeout},
               counts=Counts(), findings=[], kinds=[])
    assert r.status_reason is StatusReason.engine_timeout


def test_finding_line_order():
    with pytest.raises(ValidationError):
        Finding(rule="R", rule_kind="k", level="info", file_path="a.py",
                line_start=10, line_end=3, message="m")
