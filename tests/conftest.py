import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CODEREVIEW_DB", str(tmp_path / "t.sqlite3"))
    from codereview.api.app import app
    from codereview.infra import db
    db.init(str(tmp_path / "t.sqlite3")).close()
    return TestClient(app)


@pytest.fixture()
def seeded(client):
    from codereview.infra import db, repo
    conn = db.init(os.environ["CODEREVIEW_DB"])
    repo.insert_run(conn, {
        "run_id": "0f2c3b1a-0000-4000-8000-000000000001", "repo": "cs24107/CodeReviewAI",
        "git_ref": "abc1234", "commit_sha": "a" * 40, "status": "done",
        "started_at": "2026-12-01T10:00:00+00:00", "finished_at": "2026-12-01T10:00:02+00:00",
        "duration_ms": 1830,
        "counts": {"blocking": 1, "warning": 2, "info": 1, "total": 4},
        "findings": [
            {"rule": "PY-MUTABLE-DEFAULT", "rule_kind": "可变默认参数", "level": "blocking",
             "file_path": "sample/utils.py", "line_start": 7, "message": "参数默认值用了可变对象",
             "fixable": True, "fingerprint": "f" * 32},
            {"rule": "PY-BARE-EXCEPT", "rule_kind": "裸 except", "level": "warning",
             "file_path": "sample/service.py", "line_start": 12, "message": "裸 except 会吞掉 KeyboardInterrupt",
             "fixable": True, "fingerprint": "e" * 32},
            {"rule": "PY-BARE-EXCEPT", "rule_kind": "裸 except", "level": "warning",
             "file_path": "sample/service.py", "line_start": 20, "message": "裸 except",
             "fixable": True, "fingerprint": "d" * 32},
            {"rule": "PY-LONG-FUNC", "rule_kind": "函数过长", "level": "info",
             "file_path": "sample/cli.py", "line_start": 3, "message": "单行超过 100 字符",
             "fixable": False, "fingerprint": "c" * 32},
        ],
    })
    conn.close()
    return client
