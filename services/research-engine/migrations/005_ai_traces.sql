CREATE TABLE IF NOT EXISTS ai_traces (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID REFERENCES users(id),
 query_text TEXT,
 query_classification VARCHAR(50),
 tools_called JSONB,
 model VARCHAR(50),
 tokens_used INTEGER,
 latency_ms INTEGER,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SELECT create_hypertable('ai_traces', 'created_at', if_not_exists => TRUE);
