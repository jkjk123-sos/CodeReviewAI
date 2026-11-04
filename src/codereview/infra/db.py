# -*- coding: utf-8 -*-
"""连接与建表。

生产用 PostgreSQL 16（data/schema.sql）；本机课程期没有 PG 实例，
开发与单测走 SQLite 等价结构（差异只在三处：UUID 用 TEXT、JSONB 用 TEXT、
时间用 ISO 文本），SQL 方言集中在 infra/repo.py 一处，切库只改这里。
"""
from __future__ import annotations

import os
import sqlite3

DDL_SQLITE = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS repo (
  repo_id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL UNIQUE,
  vcs TEXT NOT NULL DEFAULT 'gitee',
  default_branch TEXT NOT NULL DEFAULT 'main',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS review_run (
  run_id TEXT PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repo(repo_id),
  git_ref TEXT NOT NULL,
  commit_sha TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  schema_version TEXT NOT NULL DEFAULT '2.0',
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  counts TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_run_repo_time ON review_run(repo_id, started_at DESC);
CREATE TABLE IF NOT EXISTS finding (
  finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES review_run(run_id) ON DELETE CASCADE,
  rule TEXT NOT NULL, rule_kind TEXT NOT NULL, level TEXT NOT NULL,
  file_path TEXT NOT NULL, line_start INTEGER NOT NULL, line_end INTEGER,
  message TEXT NOT NULL, suggestion TEXT, fixable INTEGER NOT NULL DEFAULT 0,
  fingerprint TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_finding_run ON finding(run_id, level, rule);
CREATE TABLE IF NOT EXISTS rule_def (
  rule TEXT PRIMARY KEY, lang TEXT NOT NULL, name_zh TEXT NOT NULL,
  default_level TEXT NOT NULL, description TEXT NOT NULL, doc_url TEXT,
  enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS config_snapshot (
  snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL UNIQUE REFERENCES review_run(run_id) ON DELETE CASCADE,
  sources TEXT NOT NULL, payload TEXT NOT NULL, merged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS report_blob (
  run_id TEXT NOT NULL REFERENCES review_run(run_id) ON DELETE CASCADE,
  format TEXT NOT NULL, payload TEXT NOT NULL, bytes INTEGER NOT NULL,
  PRIMARY KEY (run_id, format)
);
CREATE TABLE IF NOT EXISTS audit_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
  actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS stat_daily (
  day TEXT NOT NULL, repo_id INTEGER NOT NULL REFERENCES repo(repo_id),
  runs INTEGER NOT NULL DEFAULT 0, blocking INTEGER NOT NULL DEFAULT 0,
  warning INTEGER NOT NULL DEFAULT 0, info INTEGER NOT NULL DEFAULT 0,
  partial INTEGER NOT NULL DEFAULT 0, avg_ms INTEGER,
  PRIMARY KEY (day, repo_id)
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    db_path = path or os.environ.get("CODEREVIEW_DB", "codereview.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(path: str | None = None) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(DDL_SQLITE)
    conn.commit()
    return conn
