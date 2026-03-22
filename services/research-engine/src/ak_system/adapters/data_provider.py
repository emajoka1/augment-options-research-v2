from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import numpy as np

from ak_system.mc_options.calibration import ChainSnapshot, parse_chain_snapshot


class DataProvider(Protocol):
    async def get_chain(self, symbol: str, expiration_date: str | None = None) -> ChainSnapshot: ...
    async def get_quote(self, symbol: str) -> dict[str, Any]: ...
    async def get_returns(self, symbol: str, days: int = 30) -> np.ndarray: ...


@dataclass
class PolygonProvider:
    api_key: str

    async def get_chain(self, symbol: str, expiration_date: str | None = None) -> ChainSnapshot:
        from ak_system.adapters.polygon_adapter import PolygonAdapter

        return await PolygonAdapter(self.api_key).get_options_chain(symbol, expiration_date=expiration_date)

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        from ak_system.adapters.polygon_adapter import PolygonAdapter

        return await PolygonAdapter(self.api_key).get_quote(symbol)

    async def get_returns(self, symbol: str, days: int = 30) -> np.ndarray:
        from ak_system.adapters.polygon_adapter import PolygonAdapter

        return await PolygonAdapter(self.api_key).get_returns(symbol, days=days)


@dataclass
class SnapshotFileProvider:
    snapshot_path: str | Path

    async def get_chain(self, symbol: str, expiration_date: str | None = None) -> ChainSnapshot:
        return parse_chain_snapshot(self.snapshot_path)

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        snap = parse_chain_snapshot(self.snapshot_path)
        return {"symbol": symbol, "price": snap.spot, "source": "snapshot_file"}

    async def get_returns(self, symbol: str, days: int = 30) -> np.ndarray:
        snap = parse_chain_snapshot(self.snapshot_path)
        if snap.returns is None:
            return np.array([], dtype=float)
        return snap.returns[-days:]


@dataclass
class TastyTradeProvider:
    snapshot_path: str | Path

    async def get_chain(self, symbol: str, expiration_date: str | None = None) -> ChainSnapshot:
        return parse_chain_snapshot(self.snapshot_path)

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        snap = parse_chain_snapshot(self.snapshot_path)
        return {"symbol": symbol, "price": snap.spot, "source": "tastytrade_legacy_snapshot"}

    async def get_returns(self, symbol: str, days: int = 30) -> np.ndarray:
        snap = parse_chain_snapshot(self.snapshot_path)
        if snap.returns is None:
            return np.array([], dtype=float)
        return snap.returns[-days:]


@dataclass
class CBOEFreeProvider:
    snapshot_path: str | Path

    async def get_chain(self, symbol: str, expiration_date: str | None = None) -> ChainSnapshot:
        return parse_chain_snapshot(self.snapshot_path)

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        snap = parse_chain_snapshot(self.snapshot_path)
        return {"symbol": symbol, "price": snap.spot, "source": "cboe_free_snapshot"}

    async def get_returns(self, symbol: str, days: int = 30) -> np.ndarray:
        snap = parse_chain_snapshot(self.snapshot_path)
        if snap.returns is None:
            return np.array([], dtype=float)
        return snap.returns[-days:]
