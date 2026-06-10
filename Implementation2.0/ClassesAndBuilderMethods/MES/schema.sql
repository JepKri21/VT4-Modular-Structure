CREATE TABLE IF NOT EXISTS alarms (
    id           SERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    resource_id  TEXT,
    actor_name   TEXT,
    category     TEXT        NOT NULL,
    severity     TEXT        NOT NULL,
    order_id     TEXT,
    message      TEXT,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at   TIMESTAMPTZ,
    acknowledged BOOLEAN     NOT NULL DEFAULT false
);
ALTER TABLE alarms ADD COLUMN IF NOT EXISTS actor_name TEXT;

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

-- MES order queue. One row per work order accepted by the MES; the
-- dispatcher releases up to `MES_MAX_CONCURRENT` orders at a time by
-- publishing their `payload` to AAUSmartLab/<line>/MES/WorkOrder.
--
-- Status lifecycle:
--   PENDING   queued, not yet handed to a line controller
--   RELEASED  published to MQTT; line is working on it
--   COMPLETED line controller reported a successful finish
--   ABORTED   line controller reported abort (e.g. NO_ALTERNATIVE)
--   CANCELLED cancelled before release (operator action)
--
-- `priority` lower number = higher priority (1 = top). Within the same
-- priority, FIFO by issued_at.
CREATE TABLE IF NOT EXISTS mes_orders (
    id            SERIAL PRIMARY KEY,
    order_id      TEXT        NOT NULL UNIQUE,
    line_id       TEXT,
    product_ref   TEXT,
    priority      INTEGER     NOT NULL DEFAULT 100,
    payload       JSONB       NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'PENDING',
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at   TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    -- Batch grouping. A customer order with N products produces N rows,
    -- all sharing batch_id (the customer-facing orderNumber). batch_index
    -- is 1-based; batch_total tells the UI "X of Y".
    batch_id      TEXT,
    batch_index   INTEGER     NOT NULL DEFAULT 1,
    batch_total   INTEGER     NOT NULL DEFAULT 1,
    -- Dispatcher-level retries. Controller's own OrderRecovery already
    -- retries up to 3 times within one attempt; the dispatcher will
    -- requeue (after a backoff) on ABORTED up to MES_MAX_ATTEMPTS.
    attempt_count INTEGER     NOT NULL DEFAULT 1,
    next_attempt_at TIMESTAMPTZ
);
-- Idempotent migrations for an existing volume.
ALTER TABLE mes_orders ADD COLUMN IF NOT EXISTS batch_id        TEXT;
ALTER TABLE mes_orders ADD COLUMN IF NOT EXISTS batch_index     INTEGER NOT NULL DEFAULT 1;
ALTER TABLE mes_orders ADD COLUMN IF NOT EXISTS batch_total     INTEGER NOT NULL DEFAULT 1;
ALTER TABLE mes_orders ADD COLUMN IF NOT EXISTS attempt_count   INTEGER NOT NULL DEFAULT 1;
ALTER TABLE mes_orders ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_mes_orders_status   ON mes_orders (status);
CREATE INDEX IF NOT EXISTS idx_mes_orders_pending  ON mes_orders (priority, issued_at) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_mes_orders_released ON mes_orders (line_id) WHERE status = 'RELEASED';
CREATE INDEX IF NOT EXISTS idx_mes_orders_batch    ON mes_orders (batch_id);


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


-- =========================================================================
-- MRP (Material Requirements Planning) — MRP-1 data foundations
-- =========================================================================

-- Materials catalog. Auto-seeded by the bridge the first time a component
-- type is observed in any station's InventoryLevel. Defaults can be edited
-- via /api/mrp/materials. The PK is the *type* IRI (no instance UUID).
CREATE TABLE IF NOT EXISTS mrp_materials (
    component_type_iri TEXT        PRIMARY KEY,
    name               TEXT        NOT NULL,
    category           TEXT,
    lead_time_days     INTEGER     NOT NULL DEFAULT 7,
    reorder_strategy   TEXT        NOT NULL DEFAULT 'JIT',
    reorder_point      INTEGER     NOT NULL DEFAULT 5,
    reorder_quantity   INTEGER     NOT NULL DEFAULT 10,
    unit_cost          NUMERIC(12, 2) NOT NULL DEFAULT 1.00,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Allowed strategies are validated in app code, not via CHECK, to keep
-- adding new ones (EOQ, FOQ) cheap.

-- Per-station on-hand counts by component TYPE. Bridge wipes the rows
-- for a station's resource_id on each InventoryLevel and re-inserts —
-- the snapshot is authoritative.
CREATE TABLE IF NOT EXISTS mrp_inventory (
    resource_id        TEXT        NOT NULL,
    component_type_iri TEXT        NOT NULL,
    on_hand            INTEGER     NOT NULL DEFAULT 0,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource_id, component_type_iri)
);
CREATE INDEX IF NOT EXISTS idx_mrp_inventory_type
    ON mrp_inventory (component_type_iri);

-- Purchase orders proposed by the MRP run (MRP-2/3 will populate this).
-- Status lifecycle: PROPOSED -> APPROVED -> RECEIVED, or CANCELLED.
CREATE TABLE IF NOT EXISTS mrp_purchase_orders (
    id                 SERIAL      PRIMARY KEY,
    component_type_iri TEXT        NOT NULL,
    quantity           INTEGER     NOT NULL,
    strategy           TEXT,
    status             TEXT        NOT NULL DEFAULT 'PROPOSED',
    unit_cost          NUMERIC(12, 2),
    total_cost         NUMERIC(12, 2)
        GENERATED ALWAYS AS (unit_cost * quantity) STORED,
    needed_by          TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at        TIMESTAMPTZ,
    received_at        TIMESTAMPTZ,
    deliver_to         TEXT,
    notes              TEXT
);
CREATE INDEX IF NOT EXISTS idx_mrp_po_status     ON mrp_purchase_orders (status);
CREATE INDEX IF NOT EXISTS idx_mrp_po_type       ON mrp_purchase_orders (component_type_iri);

-- Classify materials: RAW (we buy / source), INTERMEDIATE (we produce
-- on the line; appears as a BOM child for finished goods), FINISHED
-- (output of MPS, not an MRP material). Backfilled from the IRI shape
-- in a one-time migration below.
ALTER TABLE mrp_materials ADD COLUMN IF NOT EXISTS kind TEXT;
UPDATE mrp_materials
SET kind = CASE
    WHEN component_type_iri LIKE '%/Shells/Product/%'   THEN 'FINISHED'
    WHEN component_type_iri LIKE '%/Shells/Assembly/%'  THEN 'INTERMEDIATE'
    ELSE 'RAW'
END
WHERE kind IS NULL;
ALTER TABLE mrp_materials ALTER COLUMN kind SET DEFAULT 'RAW';

-- Bill of materials. parent → child means "one parent unit requires
-- `quantity_per_unit` child units." Used by the MRP run to explode a
-- finished-product target into gross material requirements.
CREATE TABLE IF NOT EXISTS mrp_bom (
    id                 SERIAL          PRIMARY KEY,
    parent_type_iri    TEXT            NOT NULL,
    child_type_iri     TEXT            NOT NULL,
    quantity_per_unit  NUMERIC(10, 4)  NOT NULL DEFAULT 1,
    notes              TEXT,
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (parent_type_iri, child_type_iri)
);
CREATE INDEX IF NOT EXISTS idx_mrp_bom_parent ON mrp_bom (parent_type_iri);
CREATE INDEX IF NOT EXISTS idx_mrp_bom_child  ON mrp_bom (child_type_iri);

-- Master Production Schedule: weekly targets per finished product. The
-- MRP run subtracts gross requirements from on-hand + open POs to net
-- out new POs.
CREATE TABLE IF NOT EXISTS mrp_mps_entries (
    id                          SERIAL      PRIMARY KEY,
    week_start                  DATE        NOT NULL,
    finished_product_type_iri   TEXT        NOT NULL,
    quantity_target             INTEGER     NOT NULL DEFAULT 0,
    notes                       TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (week_start, finished_product_type_iri)
);
CREATE INDEX IF NOT EXISTS idx_mrp_mps_week ON mrp_mps_entries (week_start);
