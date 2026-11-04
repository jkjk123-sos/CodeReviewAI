from codereview.cli.parser import JsParser, ParserFactory, PyParser
from codereview.cli.render import RENDERERS, get_renderer
from codereview.contract.models import Counts, Finding, Report, Status
from codereview.infra.ruleset import PyRuleSet


def make_report():
    f = Finding(rule="PY-BARE-EXCEPT", rule_kind="裸 except", level="warning",
                file_path="a.py", line_start=3, message="裸 except")
    return Report(run_id="r1", repo="cs24107/CodeReviewAI", git_ref="main",
                  commit_sha="a" * 40, status=Status.done,
                  started_at="2026-12-01T10:00:00+08:00", duration_ms=12,
                  counts=Counts(warning=1, total=1), kinds=["裸 except"], findings=[f])


def test_strategy_registry_has_three():
    assert sorted(RENDERERS) == ["json", "sarif", "text"]


def test_strategy_unknown_format():
    try:
        get_renderer("pdf")
    except KeyError as e:
        assert "pdf" in str(e)
    else:
        raise AssertionError("应当抛 KeyError")


def test_sarif_shape():
    import json
    doc = json.loads(get_renderer("sarif").render(make_report()))
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["results"][0]["level"] == "warning"


def test_factory_by_suffix():
    assert isinstance(ParserFactory.for_path("a.py"), PyParser)
    assert isinstance(ParserFactory.for_path("b.ts"), JsParser)
    try:
        ParserFactory.for_path("c.go")
    except ValueError as e:
        assert "go" in str(e)
    else:
        raise AssertionError("应当抛 ValueError")


def test_template_method_dedupes_and_grades():
    rs = PyRuleSet()
    units = [{"file_path": "a.py", "line": 1, "text": "except:", "is_comment": False, "is_blank": False},
             {"file_path": "a.py", "line": 1, "text": "except:", "is_comment": False, "is_blank": False}]
    hits = rs.run(units)
    assert len(hits) == 1                      # 去重生效
    assert hits[0].level.value == "warning"    # 分级按 rules 表
    assert len(hits[0].fingerprint) == 32
