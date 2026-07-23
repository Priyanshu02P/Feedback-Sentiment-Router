-- Runs automatically once, on first container start, because it's mounted
-- into /docker-entrypoint-initdb.d.
--
-- The n8n workflows write raw feedback + classification labels into this
-- database, and bertopic_service/main.py reads from `feedbacks` /
-- `feedback_labels` and writes into `feedback_clusters`. It's kept separate
-- from n8n's own "n8n" database (workflow/execution data) on purpose.

CREATE DATABASE feedback;

\connect feedback

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS feedbacks (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_feedback TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID NOT NULL REFERENCES feedbacks(feedback_id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    severity TEXT NOT NULL,
    actionable BOOLEAN NOT NULL,
    confidence NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_labels_feedback_id ON feedback_labels (feedback_id);
CREATE INDEX IF NOT EXISTS idx_feedback_labels_filter
    ON feedback_labels (sentiment, severity, actionable, created_at);

CREATE TABLE IF NOT EXISTS feedback_clusters (
    id UUID PRIMARY KEY,
    feedback_id UUID NOT NULL REFERENCES feedbacks(feedback_id) ON DELETE CASCADE,
    cluster_id TEXT NOT NULL,
    topic_name TEXT,
    probability DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_clusters_feedback_id ON feedback_clusters (feedback_id);
