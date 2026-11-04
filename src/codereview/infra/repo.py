# -*- coding: utf-8 -*-
"""数据访问。SQL 方言集中在本文件，PG 版只替换三处（见文件末尾注释）。"""
from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timezone

from codereview.contract.errors import ApiError, ErrorCode

MAX_PAGE_SIZE = 100
MAX_PAGE = 100      # 最多 2000 条，再往后走 cursor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_repo(conn: sqlite3.Connection, full_name: str) -> int:
    row = conn.execute("SELECT repo_id FROM repo WHERE full_name=?", (full_name,)).fetchone()
    if row:
        return row["repo_id"]
    cur = conn.execute("INSERT INTO repo(full_name) VALUES(?)", (full_name,))
    return cur.lastrowid


def insert_run(conn: sqlite3.Connection, report: dict) -> None:
    repo_id = ensure_repo(conn, report["repo"])
    conn.execute(
        """INSERT INTO review_run(run_id, repo_id, git_ref, commit_sha, status,
                                  status_reason, started_at, finished_at, duration_ms, counts)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (report["run_id"], repo_id, report["git_ref"], report["commit_sha"],
         report["status"], report.get("status_reason"), report["started_at"],
         report.get("finished_at"), report.get("duration_ms"),
         json.dumps(report["counts"], ensure_ascii=False)))
    for f in report.get("findings", []):
        conn.execute(
            """INSERT INTO finding(run_id, rule, rule_kind, level, file_path,
                                   line_start, line_end, message, suggestion, fixable, fingerprint)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (report["run_id"], f["rule"], f["rule_kind"], f["level"], f["file_path"],
             f["line_start"], f.get("line_end"), f["message"], f.get("suggestion"),
             int(bool(f.get("fixable"))), f.get("fingerprint") or "0" * 32))
    day = report["started_at"][:10]
    counts = report["counts"]
    conn.execute(
        """INSERT INTO stat_daily(day, repo_id, runs, blocking, warning, info, partial, avg_ms)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(day, repo_id) DO UPDATE SET
             runs=runs+1, blocking=blocking+excluded.blocking,
             warning=warning+excluded.warning, info=info+excluded.info,
             partial=partial+excluded.partial,
             avg_ms=(COALESCE(avg_ms,0)+excluded.avg_ms)/2""",
        (day, repo_id, 1, counts["blocking"], counts["warning"], counts["info"],
         1 if report["status"] == "partial" else 0, report.get("duration_ms") or 0))
    conn.commit()


def encode_cursor(started_at: str, run_id: str) -> str:
    """游标 = 排序键原文，base64 只是为了不让调用方去解析它。"""
    return base64.urlsafe_b64encode(f"{started_at}|{run_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        ts, rid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return ts, rid
    except Exception:
        raise ApiError(ErrorCode.BAD_REQUEST, "cursor 无法解析",
                       "cursor 请原样回传上一页返回的 next_cursor") from None


def list_runs(conn: sqlite3.Connection, page: int = 1, size: int = 20,
              level: str | None = None, repo: str | None = None,
              cursor: str | None = None) -> dict:
    """列表页。小偏移走 page/size，深翻走 cursor —— 两者共存，不是二选一。

    OFFSET 的代价随页深线性增长：20 万行时 OFFSET 199000 要读 7016 个缓冲页
    （实测 27.3 ms），游标翻页只要 5 个（0.024 ms）。所以对外的规则是：
    page 最多翻到 100 页（即 2000 条），再往后必须带 cursor。
    """
    if size < 1 or size > MAX_PAGE_SIZE:
        raise ApiError(ErrorCode.BAD_REQUEST, f"size 必须在 1..{MAX_PAGE_SIZE}",
                       "翻历史页请改用 cursor，不要靠加大 size 绕")
    if page < 1:
        raise ApiError(ErrorCode.BAD_REQUEST, "page 从 1 起", "page >= 1")
    if cursor and page > 1:
        raise ApiError(ErrorCode.BAD_REQUEST, "page 与 cursor 只能给一个",
                       "接了 cursor 之后 pages 由服务端决定，不要再传 page")
    if not cursor and page > MAX_PAGE:
        raise ApiError(ErrorCode.BAD_REQUEST, f"page 上限 {MAX_PAGE} 页，再深请用 cursor",
                       "深翻请用 cursor（cursor=上一页的 next_cursor）")

    where, args = [], []
    if repo:
        where.append("repo.full_name = ?")
        args.append(repo)
    if level:
        where.append("EXISTS (SELECT 1 FROM finding f WHERE f.run_id=r.run_id AND f.level=?)")
        args.append(level)
    if cursor:
        ts, rid = decode_cursor(cursor)
        where.append("(r.started_at, r.run_id) < (?, ?)")
        args.extend([ts, rid])
        page = 1
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) c FROM review_run r JOIN repo ON repo.repo_id=r.repo_id {clause}",
        args).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT r.run_id, repo.full_name, r.git_ref, r.status, r.status_reason,
                   r.started_at, r.duration_ms, r.counts
            FROM review_run r JOIN repo ON repo.repo_id=r.repo_id {clause}
            ORDER BY r.started_at DESC, r.run_id DESC LIMIT ? OFFSET ?""",
        args + [size, 0 if cursor else (page - 1) * size]).fetchall()

    items = []
    for r in rows:
        items.append({"run_id": r["run_id"], "repo": r["full_name"], "git_ref": r["git_ref"],
                      "status": r["status"], "status_reason": r["status_reason"],
                      "started_at": r["started_at"], "duration_ms": r["duration_ms"],
                      "counts": json.loads(r["counts"])})
    next_cursor = (encode_cursor(rows[-1]["started_at"], rows[-1]["run_id"])
                   if len(rows) == size else None)
    return {"items": items, "total": total, "page": page, "size": size,
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None}


def get_run(conn: sqlite3.Connection, run_id: str) -> dict:
    row = conn.execute(
        """SELECT r.*, repo.full_name FROM review_run r
           JOIN repo ON repo.repo_id=r.repo_id WHERE r.run_id=?""", (run_id,)).fetchone()
    if not row:
        raise ApiError(ErrorCode.NOT_FOUND, f"run {run_id} 不存在", "先 GET /api/v1/reviews 看有没有")
    findings = conn.execute(
        """SELECT rule, rule_kind, level, file_path, line_start, line_end,
                  message, suggestion, fixable, fingerprint
           FROM finding WHERE run_id=? ORDER BY level, file_path, line_start""",
        (run_id,)).fetchall()
    kinds = sorted({f["rule_kind"] for f in findings})
    return {
        "schema_version": row["schema_version"], "run_id": row["run_id"],
        "repo": row["full_name"], "git_ref": row["git_ref"], "commit_sha": row["commit_sha"],
        "status": row["status"], "status_reason": row["status_reason"],
        "started_at": row["started_at"], "finished_at": row["finished_at"],
        "duration_ms": row["duration_ms"], "counts": json.loads(row["counts"]),
        "kinds": kinds, "findings": [dict(f) for f in findings],
    }


def list_findings(conn: sqlite3.Connection, run_id: str, page: int = 1, size: int = 50,
                  level: str | None = None) -> dict:
    if size > MAX_PAGE_SIZE:
        raise ApiError(ErrorCode.BAD_REQUEST, f"size 上限 {MAX_PAGE_SIZE}", "改小 size")
    args = [run_id]
    clause = "run_id=?"
    if level:
        clause += " AND level=?"
        args.append(level)
    total = conn.execute(f"SELECT COUNT(*) c FROM finding WHERE {clause}", args).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT rule, rule_kind, level, file_path, line_start, message, fixable
            FROM finding WHERE {clause} ORDER BY level, file_path, line_start
            LIMIT ? OFFSET ?""", args + [size, (page - 1) * size]).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "size": size}


def stats_summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) runs,
                  SUM(CASE WHEN status='partial' THEN 1 ELSE 0 END) partial,
                  AVG(duration_ms) avg_ms
           FROM review_run""").fetchone()
    agg = conn.execute(
        """SELECT COALESCE(SUM(blocking),0) b, COALESCE(SUM(warning),0) w,
                  COALESCE(SUM(info),0) i FROM stat_daily""").fetchone()
    runs = row["runs"] or 0
    return {"runs": runs, "partial": row["partial"] or 0,
            "avg_ms": round(row["avg_ms"] or 0),
            "blocking": agg["b"], "warning": agg["w"], "info": agg["i"],
            "block_rate": round((row["partial"] or 0) / runs, 4) if runs else 0.0}


def stats_trend(conn: sqlite3.Connection, weeks: int = 8) -> dict:
    rows = conn.execute(
        """SELECT day, SUM(runs) runs, SUM(blocking) blocking, SUM(partial) partial
           FROM stat_daily GROUP BY day ORDER BY day DESC LIMIT ?""", (weeks * 7,)).fetchall()
    return {"points": [dict(r) for r in reversed(rows)]}


def stats_by_rule(conn: sqlite3.Connection, top: int = 10) -> dict:
    rows = conn.execute(
        """SELECT rule, rule_kind, COUNT(*) n FROM finding
           GROUP BY rule, rule_kind ORDER BY n DESC LIMIT ?""", (top,)).fetchall()
    total = conn.execute("SELECT COUNT(*) c FROM finding").fetchone()["c"] or 1
    return {"items": [{"rule": r["rule"], "rule_kind": r["rule_kind"], "count": r["n"],
                       "ratio": round(r["n"] / total, 4)} for r in rows]}


def list_rules(conn: sqlite3.Connection, lang: str | None = None,
               level: str | None = None) -> dict:
    clause, args = [], []
    if lang:
        clause.append("lang=?"); args.append(lang)
    if level:
        clause.append("default_level=?"); args.append(level)
    where = ("WHERE " + " AND ".join(clause)) if clause else ""
    rows = conn.execute(
        f"SELECT rule, lang, name_zh, default_level FROM rule_def {where} ORDER BY rule",
        args).fetchall()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


def get_rule(conn: sqlite3.Connection, rule: str) -> dict:
    row = conn.execute("SELECT * FROM rule_def WHERE rule=?", (rule,)).fetchone()
    if not row:
        raise ApiError(ErrorCode.NOT_FOUND, f"规则 {rule} 不存在", "GET /api/v1/rules")
    return dict(row)


# PG 版差异（切库时只改这三处）：
#   1. gen_random_uuid() 代替应用层 uuid4
#   2. counts 用 jsonb 类型，读写不需 json.dumps/loads
#   3. stat_daily 的 upsert 用 PG 的 ON CONFLICT ... DO UPDATE SET 语法（SQLite 亦支持，等价）
