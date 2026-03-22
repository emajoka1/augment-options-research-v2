CREATE TABLE IF NOT EXISTS mc_results (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 symbol VARCHAR(10) NOT NULL,
 strategy_type VARCHAR(50),
 config JSONB NOT NULL,
 payload JSONB NOT NULL,
 canonical_inputs_hash VARCHAR(64),
 allow_trade BOOLEAN,
 ev_mean NUMERIC(12,6),
 data_quality_status VARCHAR(50),
 created_at TIMESTAMPTZ DEFAULT NOW()
);
SELECT create_hypertable('mc_results', 'created_at', if_not_exists => TRUE);
