-- =====================================================================
-- Feedback Pipeline schema
-- Run this once before activating the n8n workflows.
-- =====================================================================

CREATE TABLE IF NOT EXISTS feedbacks (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL,
    raw_feedback TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_feedbacks_unprocessed ON feedbacks (processed) WHERE processed = FALSE;

CREATE TABLE IF NOT EXISTS feedback_classifications (
    id BIGSERIAL PRIMARY KEY,
    feedback_id UUID NOT NULL REFERENCES feedbacks(feedback_id),
    course_id UUID NOT NULL,
    actionable BOOLEAN,
    summary TEXT,
    llm_model TEXT,
    classification_confidence FLOAT,
    review_required BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Main fact table: one row per LABEL, not per feedback.
CREATE TABLE IF NOT EXISTS feedback_labels (
    id BIGSERIAL PRIMARY KEY,
    feedback_id UUID NOT NULL REFERENCES feedbacks(feedback_id),
    course_id UUID NOT NULL,
    label VARCHAR(100),
    sentiment VARCHAR(20),
    severity VARCHAR(20),
    confidence FLOAT,
    owner_role VARCHAR(50),
    actionable BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedback_labels_label ON feedback_labels (label);
CREATE INDEX IF NOT EXISTS idx_feedback_labels_created_at ON feedback_labels (created_at);

CREATE TABLE IF NOT EXISTS review_queue (
    id BIGSERIAL PRIMARY KEY,
    feedback_id UUID,
    raw_feedback TEXT,
    llm_response JSONB,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_clusters (
    id BIGSERIAL PRIMARY KEY,
    feedback_id UUID,
    cluster_id VARCHAR(100),
    topic_name TEXT,
    probability FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedback_clusters_created_at ON feedback_clusters (created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_clusters_cluster_id ON feedback_clusters (cluster_id);

CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_date DATE,
    role VARCHAR(50),
    kpi_name VARCHAR(100),
    value FLOAT,
    threshold FLOAT,
    status VARCHAR(20)
);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshots_date ON kpi_snapshots (snapshot_date);

-- Referenced by Workflow 4 (Alert Engine) and Workflow 5 (Trend Detection)
-- but not defined in the original design doc -- added here so both workflows run as-is.
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    role VARCHAR(50),
    severity VARCHAR(20),
    message TEXT,
    kpi_snapshot_id BIGINT REFERENCES kpi_snapshots(id), -- set for KPI-threshold alerts, NULL for trend/emerging-issue alerts
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_kpi_snapshot ON alerts (kpi_snapshot_id);

CREATE TABLE IF NOT EXISTS testimonials (
    id             BIGSERIAL PRIMARY KEY,
    feedback_id    UUID NOT NULL REFERENCES feedbacks(feedback_id),
    course_id      UUID NOT NULL,
    quote          TEXT NOT NULL,
    author_name    VARCHAR(150),
    sentiment      VARCHAR(20) NOT NULL DEFAULT 'Positive',
    confidence     FLOAT,
    is_approved    BOOLEAN NOT NULL DEFAULT FALSE,   -- human review gate before publishing
    source         VARCHAR(50) DEFAULT 'feedback_labels',
    created_at     TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_testimonials_feedback_id UNIQUE (feedback_id)
);
