RID = "0f2c3b1a-0000-4000-8000-000000000001"


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_13_routes_registered():
    from codereview.api.app import app
    paths = set(app.openapi()["paths"])
    expect = {"/healthz", "/api/v1/reviews", "/api/v1/reviews/{run_id}",
              "/api/v1/reviews/{run_id}/findings", "/api/v1/reviews/{run_id}/rerun",
              "/api/v1/reviews/{run_id}/export", "/api/v1/rules",
              "/api/v1/rules/{rule}", "/api/v1/rules/{rule}/examples",
              "/api/v1/stats/summary", "/api/v1/stats/trend", "/api/v1/stats/by-rule"}
    assert expect <= paths, f"缺路由：{expect - paths}"


def test_envelope_shape(seeded):
    body = seeded.get("/api/v1/reviews").json()
    assert set(body) == {"code", "message", "data", "traceId", "timestamp"}


def test_list_and_detail(seeded):
    lst = seeded.get("/api/v1/reviews").json()["data"]
    assert lst["total"] == 1 and lst["items"][0]["run_id"] == RID
    detail = seeded.get(f"/api/v1/reviews/{RID}").json()["data"]
    assert detail["counts"]["blocking"] == 1 and len(detail["findings"]) == 4
    assert detail["kinds"] == sorted({"可变默认参数", "裸 except", "函数过长"})


def test_pagination_guard(seeded):
    r = seeded.get("/api/v1/reviews", params={"size": 500})
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "E4001" and body["hint"]


def test_not_found(seeded):
    r = seeded.get("/api/v1/reviews/nope")
    assert r.status_code == 404 and r.json()["code"] == "E4041"


def test_findings_paging_and_filter(seeded):
    d = seeded.get(f"/api/v1/reviews/{RID}/findings",
                   params={"size": 2, "level": "warning"}).json()["data"]
    assert d["total"] == 2 and len(d["items"]) == 2


def test_export_json_and_sarif(seeded):
    j = seeded.get(f"/api/v1/reviews/{RID}/export", params={"format": "json"})
    s = seeded.get(f"/api/v1/reviews/{RID}/export", params={"format": "sarif"})
    assert j.status_code == 200 and '"run_id"' in j.text
    assert '"2.1.0"' in s.text
    bad = seeded.get(f"/api/v1/reviews/{RID}/export", params={"format": "pdf"})
    assert bad.status_code == 400


def test_stats(seeded):
    assert seeded.get("/api/v1/stats/summary").json()["data"]["runs"] == 1
    assert "points" in seeded.get("/api/v1/stats/trend").json()["data"]
    by_rule = seeded.get("/api/v1/stats/by-rule").json()["data"]["items"]
    assert by_rule[0]["count"] == 2


def test_cursor_pagination_has_no_overlap_or_gap(client, monkeypatch):
    """游标翻页：5 条数据按 2 条一页翻完，不重不漏。"""
    import os
    from codereview.infra import db, repo
    conn = db.init(os.environ["CODEREVIEW_DB"])
    for i in range(5):
        repo.insert_run(conn, {
            "run_id": f"00000000-0000-4000-8000-00000000000{i}", "repo": "cs24107/CodeReviewAI",
            "git_ref": f"c{i}", "commit_sha": f"{i}" * 40, "status": "done",
            "started_at": f"2026-12-0{i + 1}T10:00:00+00:00", "finished_at": None,
            "duration_ms": 100, "counts": {"blocking": 0, "warning": 0, "info": 0, "total": 0},
            "findings": []})
    conn.close()
    seen, cur, pages = [], None, 0
    while True:
        q = {"size": 2} | ({"cursor": cur} if cur else {})
        data = client.get("/api/v1/reviews", params=q).json()["data"]
        seen += [i["run_id"] for i in data["items"]]
        pages += 1
        cur = data["next_cursor"]
        if not cur or pages > 10:
            break
    assert len(seen) == 5 and len(set(seen)) == 5, seen
    assert seen == sorted(seen, reverse=True), "游标翻页必须严格按时间倒序"


def test_page_and_cursor_conflict(seeded):
    r = seeded.get("/api/v1/reviews", params={"page": 2, "cursor": "abc"})
    assert r.status_code == 400 and "cursor" in r.json()["hint"]


def test_deep_page_guard(seeded):
    r = seeded.get("/api/v1/reviews", params={"page": 101})
    assert r.status_code == 400 and "cursor" in r.json()["message"]


def test_bad_cursor(seeded):
    r = seeded.get("/api/v1/reviews", params={"cursor": "!!!not-base64"})
    assert r.status_code == 400 and r.json()["code"] == "E4001"
