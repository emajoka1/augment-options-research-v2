from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np

from ak_system.mc_options.calibration import ChainSnapshot


@dataclass
class PolygonAdapter:
    api_key: str
    base_url: str = 'https://api.polygon.io'

    async def get_options_chain(self, symbol: str, expiration_date: str | None = None) -> ChainSnapshot:
        contracts = await self._get_reference_contracts(symbol, expiration_date=expiration_date)
        snapshot = await self._get_snapshot(symbol)
        quote = await self.get_quote(symbol)

        results = snapshot.get('results', []) if isinstance(snapshot, dict) else []
        strikes: list[float] = []
        ivs: list[float] = []
        expiries_days: list[float] = []
        by_ticker = {item.get('details', {}).get('ticker') or item.get('ticker'): item for item in results}

        for contract in contracts:
            ticker = contract.get('ticker') or contract.get('details', {}).get('ticker')
            snap_item = by_ticker.get(ticker, {})
            details = contract.get('details', contract)
            strike = details.get('strike_price')
            expiry = details.get('expiration_date')
            iv = snap_item.get('implied_volatility')
            if strike is None or expiry is None or iv in (None, 0):
                continue
            strikes.append(float(strike))
            ivs.append(float(iv))
            expiry_dt = datetime.fromisoformat(str(expiry)).replace(tzinfo=timezone.utc)
            expiries_days.append(max(0.0, (expiry_dt - datetime.now(timezone.utc)).total_seconds() / 86400.0))

        returns = await self.get_returns(symbol, days=30)
        return ChainSnapshot(
            spot=float(quote.get('price', 0.0)),
            strikes=np.array(strikes, dtype=float),
            ivs=np.array(ivs, dtype=float),
            expiries_days=np.array(expiries_days, dtype=float) if expiries_days else None,
            returns=returns if returns.size else None,
        )

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        payload = await self._get_json(f'/v2/last/trade/{symbol}', params={})
        results = payload.get('results') or {}
        return {'symbol': symbol, 'price': float(results.get('p', 0.0)), 'timestamp': results.get('t')}

    async def get_ohlcv(self, symbol: str, from_date: str, to_date: str) -> list[dict[str, Any]]:
        payload = await self._get_json(f'/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}', params={'adjusted': 'true', 'sort': 'asc', 'limit': '5000'})
        return payload.get('results', []) or []

    async def get_returns(self, symbol: str, days: int = 30) -> np.ndarray:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(days * 3, 45))
        candles = await self.get_ohlcv(symbol, start.isoformat(), end.isoformat())
        closes = np.array([float(c['c']) for c in candles if c.get('c') is not None], dtype=float)
        if closes.size < 2:
            return np.array([], dtype=float)
        returns = np.diff(np.log(closes))
        return returns[-days:]

    async def _get_reference_contracts(self, symbol: str, expiration_date: str | None = None) -> list[dict[str, Any]]:
        params = {'underlying_ticker': symbol, 'limit': '250', 'expired': 'false'}
        if expiration_date:
            params['expiration_date'] = expiration_date
        payload = await self._get_json('/v3/reference/options/contracts', params=params)
        return payload.get('results', []) or []

    async def _get_snapshot(self, symbol: str) -> dict[str, Any]:
        return await self._get_json(f'/v3/snapshot/options/{symbol}', params={})

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        qp = dict(params)
        qp['apiKey'] = self.api_key
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            response = await client.get(path, params=qp)
            response.raise_for_status()
            return response.json()
