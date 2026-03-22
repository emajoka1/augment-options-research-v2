CREATE TABLE IF NOT EXISTS options_chains (
 id BIGSERIAL,
 symbol VARCHAR(10) NOT NULL,
 expiration DATE NOT NULL,
 strike NUMERIC(12,2) NOT NULL,
 option_type CHAR(1) NOT NULL,
 bid NUMERIC(12,4), ask NUMERIC(12,4), last NUMERIC(12,4),
 volume INTEGER DEFAULT 0, open_interest INTEGER DEFAULT 0,
 implied_volatility NUMERIC(8,6),
 delta NUMERIC(8,6), gamma NUMERIC(8,6), theta NUMERIC(8,6), vega NUMERIC(8,6),
 underlying_price NUMERIC(12,4),
 snapshot_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 data_source VARCHAR(20) DEFAULT 'polygon',
 PRIMARY KEY (id, snapshot_time)
);
SELECT create_hypertable('options_chains', 'snapshot_time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_chains_symbol ON options_chains (symbol, expiration, snapshot_time DESC);
