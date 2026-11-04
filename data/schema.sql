-- ============================================================
--  03-schema.sql   C 线报告库（PostgreSQL 16）
--  8 张表：repo / review_run / finding / rule_def /
--          config_snapshot / report_blob / audit_log / stat_daily
--  约定：snake_case；时间一律 timestamptz；枚举用 CHECK 不用 ENUM
--        （枚举加值要 ALTER TYPE，跨版本迁移麻烦）
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------- 1 repo
CREATE TABLE repo (
    repo_id        BIGSERIAL PRIMARY KEY,
    full_name      TEXT        NOT NULL UNIQUE,        -- cs24107/CodeReviewAI
    vcs            TEXT        NOT NULL DEFAULT 'gitee',
    default_branch TEXT        NOT NULL DEFAULT 'main',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------- 2 review_run
CREATE TABLE review_run (
    run_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id        BIGINT      NOT NULL REFERENCES repo (repo_id) ON DELETE CASCADE,
    git_ref        TEXT        NOT NULL,
    commit_sha     CHAR(40)    NOT NULL,
    status         TEXT        NOT NULL
                   CHECK (status IN ('queued','parsing','judging','rendering',
                                     'persisting','done','partial','failed')),
    status_reason  TEXT        CHECK (status_reason IN ('parse_failed',
                                     'engine_timeout','db_unavailable')),
    schema_version TEXT        NOT NULL DEFAULT '2.0',
    started_at     TIMESTAMPTZ NOT NULL,
    finished_at    TIMESTAMPTZ,
    duration_ms    INTEGER     CHECK (duration_ms IS NULL OR duration_ms >= 0),
    counts         JSONB       NOT NULL DEFAULT '{}'::jsonb,   -- {blocking,warning,info,total}
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- partial 必须说明原因：这是实验二 V-03 那条校验的库级落实
    CONSTRAINT run_partial_needs_reason
        CHECK (status <> 'partial' OR status_reason IS NOT NULL),
    CONSTRAINT run_finished_after_start
        CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT run_sha_len CHECK (length(commit_sha) = 40)
);

CREATE INDEX idx_run_repo_time ON review_run (repo_id, started_at DESC);
-- 时间线索引：列表页与游标翻页都靠它。带上 run_id 是为了让 (started_at, run_id)
-- 的行值比较能走索引，同名时间戳也不会错序（游标的稳定性靠这一条）
CREATE INDEX idx_run_timeline ON review_run (started_at DESC, run_id DESC);
CREATE INDEX idx_run_open ON review_run (status) WHERE status <> 'done';
CREATE INDEX idx_run_counts_gin ON review_run USING gin (counts jsonb_path_ops);

-- ------------------------------------------------------------- 3 finding
CREATE TABLE finding (
    finding_id  BIGSERIAL   PRIMARY KEY,
    run_id      UUID        NOT NULL REFERENCES review_run (run_id) ON DELETE CASCADE,
    rule        TEXT        NOT NULL,
    rule_kind   TEXT        NOT NULL,
    level       TEXT        NOT NULL CHECK (level IN ('blocking','warning','info')),
    file_path   TEXT        NOT NULL,
    line_start  INTEGER     NOT NULL CHECK (line_start > 0),
    line_end    INTEGER,
    message     TEXT        NOT NULL CHECK (length(message) BETWEEN 1 AND 500),
    suggestion  TEXT,
    fixable     BOOLEAN     NOT NULL DEFAULT false,
    fingerprint CHAR(32)    NOT NULL,
    CONSTRAINT finding_line_order CHECK (line_end IS NULL OR line_end >= line_start)
);

CREATE INDEX idx_finding_run  ON finding (run_id, level, rule);
CREATE INDEX idx_finding_fp   ON finding (fingerprint);
CREATE INDEX idx_finding_path ON finding (run_id, file_path);

-- ------------------------------------------------------------ 4 rule_def
CREATE TABLE rule_def (
    rule          TEXT    PRIMARY KEY,
    lang          TEXT    NOT NULL,
    name_zh       TEXT    NOT NULL,
    default_level TEXT    NOT NULL CHECK (default_level IN ('blocking','warning','info')),
    description   TEXT    NOT NULL,
    doc_url       TEXT,
    enabled       BOOLEAN NOT NULL DEFAULT true
);

-- ----------------------------------------------------- 5 config_snapshot
CREATE TABLE config_snapshot (
    snapshot_id BIGSERIAL   PRIMARY KEY,
    run_id      UUID        NOT NULL UNIQUE REFERENCES review_run (run_id) ON DELETE CASCADE,
    sources     JSONB       NOT NULL,     -- ["default","repo:.codereview.toml","cli:--fail-on"]
    payload     JSONB       NOT NULL,     -- 三级合并后的最终配置
    merged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------- 6 report_blob
CREATE TABLE report_blob (
    run_id  UUID    NOT NULL REFERENCES review_run (run_id) ON DELETE CASCADE,
    format  TEXT    NOT NULL CHECK (format IN ('json','sarif','text')),
    payload JSONB   NOT NULL,
    bytes   INTEGER NOT NULL CHECK (bytes > 0),
    PRIMARY KEY (run_id, format)
);

-- ---------------------------------------------------------- 7 audit_log
-- 按月 RANGE 分区：课程期一月一万行，放任增长两年后单表 25 万行虽不致命，
-- 但归档与删除会变成大事务；分区后 detach 一个分区就是归档。
CREATE TABLE audit_log (
    log_id      BIGSERIAL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor       TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    target      TEXT,
    detail      JSONB,
    PRIMARY KEY (log_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE audit_log_2026m11 PARTITION OF audit_log
    FOR VALUES FROM ('2026-11-01+08') TO ('2026-12-01+08');
CREATE TABLE audit_log_2026m12 PARTITION OF audit_log
    FOR VALUES FROM ('2026-12-01+08') TO ('2027-01-01+08');
CREATE INDEX idx_audit_actor_time ON audit_log (actor, occurred_at DESC);

-- --------------------------------------------------------- 8 stat_daily
-- 趋势页的预聚合表：写时更新（run 落库后 upsert 一行），
-- 读时不再扫 review_run。属"派生冗余"，与 review_run 的一致性由
-- 事务内 upsert + 每日对账脚本保证。
CREATE TABLE stat_daily (
    day      DATE    NOT NULL,
    repo_id  BIGINT  NOT NULL REFERENCES repo (repo_id) ON DELETE CASCADE,
    runs     INTEGER NOT NULL DEFAULT 0 CHECK (runs >= 0),
    blocking INTEGER NOT NULL DEFAULT 0 CHECK (blocking >= 0),
    warning  INTEGER NOT NULL DEFAULT 0 CHECK (warning >= 0),
    info     INTEGER NOT NULL DEFAULT 0 CHECK (info >= 0),
    partial  INTEGER NOT NULL DEFAULT 0 CHECK (partial >= 0),
    avg_ms   INTEGER,
    PRIMARY KEY (day, repo_id)
);

-- ------------------------------------------------------------- 视图
CREATE VIEW v_run_summary AS
SELECT r.run_id, r.repo_id, r.git_ref, r.status, r.status_reason,
       r.started_at, r.duration_ms,
       (r.counts ->> 'blocking')::int AS blocking,
       (r.counts ->> 'warning')::int  AS warning,
       (r.counts ->> 'info')::int     AS info,
       count(f.finding_id)            AS finding_rows
FROM review_run r
LEFT JOIN finding f ON f.run_id = r.run_id
GROUP BY r.run_id;

-- ------------------------------------------------------- 归档约定
-- 每月 1 日 02:00：把 12 个月以前的分区 DETACH 后转存为
--   audit_log_yyyymm_archive，再 COPY 到对象存储；库内只留 12 个月。
-- 课程期不触发，实验五压测时按 24 个月模拟一次。
