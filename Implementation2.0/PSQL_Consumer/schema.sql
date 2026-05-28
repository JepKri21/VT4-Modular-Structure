CREATE TABLE IF NOT EXISTS alarms (
    id           SERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    resource_id  TEXT,
    category     TEXT        NOT NULL,
    severity     TEXT        NOT NULL,
    order_id     TEXT,
    message      TEXT,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at   TIMESTAMPTZ,
    acknowledged BOOLEAN     NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_alarms_triggered_at ON alarms(triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alarms_active ON alarms(cleared_at) WHERE cleared_at IS NULL;


-- =========================================================================
-- PERFORMANCE METRICS
-- =========================================================================

-- One row per PackML state transition reported by a station. Stored raw;
-- OEE availability is computed in the API layer (so the formula can evolve
-- without a re-ingest).
CREATE TABLE IF NOT EXISTS state_transitions (
    id          SERIAL PRIMARY KEY,
    line_id     TEXT,
    resource_id TEXT        NOT NULL,
    actor_name  TEXT,
    state       TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL
);
ALTER TABLE state_transitions ADD COLUMN IF NOT EXISTS line_id TEXT;
CREATE INDEX IF NOT EXISTS idx_state_resource_ts
    ON state_transitions (resource_id, actor_name, ts);

-- One row per JobResultMessage. Performance and Quality components of OEE
-- come from aggregates over this table.
CREATE TABLE IF NOT EXISTS job_results (
    id                    SERIAL PRIMARY KEY,
    line_id               TEXT,
    order_id              TEXT,
    job_id                TEXT,
    resource_id           TEXT        NOT NULL,
    actor_name            TEXT,
    skill                 TEXT,
    ideal_cycle_time_ms   INTEGER,
    actual_cycle_time_ms  INTEGER,
    result                TEXT,
    quality               TEXT,
    completed_at          TIMESTAMPTZ NOT NULL
);
ALTER TABLE job_results ADD COLUMN IF NOT EXISTS line_id TEXT;
CREATE INDEX IF NOT EXISTS idx_job_resource_completed
    ON job_results (resource_id, actor_name, completed_at);
CREATE INDEX IF NOT EXISTS idx_job_line_completed
    ON job_results (line_id, completed_at);

-- One row per order leaving the scheduler (success or abort).
CREATE TABLE IF NOT EXISTS order_completions (
    id            SERIAL PRIMARY KEY,
    line_id       TEXT,
    order_id      TEXT        NOT NULL,
    product_ref   TEXT,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ NOT NULL,
    status        TEXT        NOT NULL,
    attempt_count INTEGER     NOT NULL DEFAULT 1
);
ALTER TABLE order_completions ADD COLUMN IF NOT EXISTS line_id TEXT;
CREATE INDEX IF NOT EXISTS idx_orders_completed_ts
    ON order_completions (completed_at);
