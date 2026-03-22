from __future__ import annotations

import json
import os
from typing import Any

import asyncpg


async def persist_mc_result(payload: dict[str, Any], config: dict[str, Any]) -> str | None:
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        return None

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            '''
            INSERT INTO mc_results (
              symbol, strategy_type, config, payload, canonical_inputs_hash,
              allow_trade, ev_mean, data_quality_status
            ) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, $8)
            RETURNING id
            ''',
            config.get('symbol', 'SPY'),
            config.get('strategy_type'),
            json.dumps(config),
            json.dumps(payload),
            payload.get('canonical_inputs_hash'),
            bool((payload.get('gates') or {}).get('allow_trade')),
            (payload.get('multi_seed_confidence') or {}).get('ev_mean'),
            payload.get('data_quality_status'),
        )
        return str(row['id']) if row else None
    finally:
        await conn.close()
