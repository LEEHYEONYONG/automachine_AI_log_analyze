-- Runs here only when the db volume is first created.
-- ground_truth/ is deliberately not stored: it is for eval/ only.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE runs (
    run_id       text PRIMARY KEY,
    machine_id   text NOT NULL,
    start_time   timestamp(3) NOT NULL,
    end_time     timestamp(3),
    machine_info jsonb NOT NULL,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alarm_codes (
    code     text PRIMARY KEY,
    unit     text NOT NULL,
    text     text NOT NULL,
    on_reset text
);

-- event.log: "<ts> <LEVEL> <UNIT> <message key=value ...>"
CREATE TABLE events (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id  text NOT NULL REFERENCES runs ON DELETE CASCADE,
    ts      timestamp(3) NOT NULL,
    level   text NOT NULL,
    unit    text NOT NULL,
    message text NOT NULL,
    attrs   jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX events_run_ts ON events (run_id, ts);
CREATE INDEX events_run_unit_ts ON events (run_id, unit, ts);

-- alarm.log SET/CLEAR pairs as one row
CREATE TABLE alarms (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id   text NOT NULL REFERENCES runs ON DELETE CASCADE,
    code     text NOT NULL,
    unit     text NOT NULL,
    set_ts   timestamp(3) NOT NULL,
    clear_ts timestamp(3),
    message  text NOT NULL,
    detail   text,
    attrs    jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX alarms_run_set ON alarms (run_id, set_ts);

-- production.csv
CREATE TABLE production (
    run_id            text NOT NULL REFERENCES runs ON DELETE CASCADE,
    wp_id             text NOT NULL,
    lot_id            text NOT NULL,
    recipe            text NOT NULL,
    start_time        timestamp(3) NOT NULL,
    end_time          timestamp(3),
    cycle_s           real,
    align_dx_mm       real,
    align_dy_mm       real,
    align_score       real,
    fixture_vac_kpa   real,
    vac_retries       integer,
    disp_pressure_kpa real,
    disp_temp_c       real,
    nozzle_height_mm  real,
    bead_width_mm     real,
    bead_offset_mm    real,
    judge             text,
    ng_reason         text,
    PRIMARY KEY (run_id, wp_id)
);
CREATE INDEX production_run_end ON production (run_id, end_time);

-- sensor_trend.csv (1 s)
CREATE TABLE sensor_trend (
    run_id            text NOT NULL REFERENCES runs ON DELETE CASCADE,
    ts                timestamp(3) NOT NULL,
    mode              text NOT NULL,
    fixture_vac_kpa   real,
    disp_pressure_kpa real,
    disp_valve_open   smallint,
    disp_temp_c       real,
    syringe_level_pct real,
    PRIMARY KEY (run_id, ts)
);

-- io_trace.csv stays in files for now (~300k rows per 8 h).

-- Manual / domain-note chunks for RAG (bge-m3, 1024 dims). Filled in step 3.
CREATE TABLE manual_chunks (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source     text NOT NULL,
    section    text,
    content    text NOT NULL,
    embedding  vector(1024),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX manual_chunks_embedding ON manual_chunks USING hnsw (embedding vector_cosine_ops);

-- One row per analysis of an alarm (rule / anomaly / classifier / agent).
CREATE TABLE analysis_results (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          text NOT NULL REFERENCES runs ON DELETE CASCADE,
    alarm_id        bigint REFERENCES alarms ON DELETE CASCADE,
    method          text NOT NULL,
    predicted_cause text,
    confidence      real,
    evidence        jsonb NOT NULL DEFAULT '{}',
    report          text,
    model           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analysis_results_run ON analysis_results (run_id, created_at);
