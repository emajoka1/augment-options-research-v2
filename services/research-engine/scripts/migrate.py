from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'migrations'


async def main() -> None:
    dsn = __import__('os').environ.get('DATABASE_URL')
    if not dsn:
        raise SystemExit('DATABASE_URL is required')

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())')
        applied = {row['version'] for row in await conn.fetch('SELECT version FROM schema_migrations')}
        for path in sorted(MIGRATIONS.glob('*.sql')):
            if path.name in applied:
                continue
            sql = path.read_text(encoding='utf-8')
            await conn.execute(sql)
            await conn.execute('INSERT INTO schema_migrations(version) VALUES($1)', path.name)
            print(f'applied {path.name}')
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
