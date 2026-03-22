from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import asyncpg

from ak_system.adapters.polygon_adapter import PolygonAdapter

UNIVERSE = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD']


async def persist_symbol(conn: asyncpg.Connection, adapter: PolygonAdapter, symbol: str) -> None:
    chain = await adapter.get_options_chain(symbol)
    expiries = chain.expiries_days if chain.expiries_days is not None else [0.0] * len(chain.strikes)
    snapshot_time = datetime.now(timezone.utc)
    for strike, iv, expiry_days in zip(chain.strikes, chain.ivs, expiries):
        expiration = (snapshot_time.date()).isoformat()
        await conn.execute(
            '''
            INSERT INTO options_chains (
              symbol, expiration, strike, option_type, implied_volatility,
              underlying_price, snapshot_time, data_source
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ''',
            symbol,
            expiration,
            float(strike),
            'C',
            float(iv),
            float(chain.spot),
            snapshot_time,
            'polygon',
        )


async def main() -> None:
    dsn = os.environ.get('DATABASE_URL')
    api_key = os.environ.get('POLYGON_API_KEY')
    if not dsn or not api_key:
        raise SystemExit('DATABASE_URL and POLYGON_API_KEY are required')
    conn = await asyncpg.connect(dsn)
    adapter = PolygonAdapter(api_key)
    try:
        for symbol in UNIVERSE:
            await persist_symbol(conn, adapter, symbol)
            print(f'ingested {symbol}')
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
