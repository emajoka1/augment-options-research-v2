from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ak_system.mc_options.engine import MCEngineConfig


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class ChainResponse(BaseModel):
    symbol: str
    spot: float
    strikes: list[float]
    ivs: list[float]
    expiry_days: list[float] | None = None
    returns: list[float] | None = None
    source: str
    todo: str | None = None


class GreeksResponse(BaseModel):
    price: float
    delta: float
    gamma: float
    vega: float
    theta_daily: float


class StrategyLegRequest(BaseModel):
    side: Literal['long', 'short']
    option_type: Literal['call', 'put']
    strike: float
    qty: int = 1
    expiry_years: float | None = None


class StrategyAnalyzeRequest(BaseModel):
    legs: list[StrategyLegRequest]
    spot: float
    r: float = 0.03
    q: float = 0.0


class StrategyAnalyzeResponse(BaseModel):
    entry_value: float
    breakevens: list[float] | None = None
    max_profit: float
    max_loss: float
    greeks_aggregate: dict[str, float]


class VolSurfaceResponse(BaseModel):
    symbol: str
    iv_atm: float
    skew: float
    curv: float
    strikes: list[float]
    ivs: list[float]
    fitted_ivs: list[float]


class RiskEstimateResponse(BaseModel):
    version: str
    structure_type: str
    max_loss: float
    risk_cap: float
    feasible_under_cap: bool


class MCRunResponse(BaseModel):
    generated_at: str | None = None
    config_hash: str | None = None
    status: str
    canonical_inputs_hash: str | None = None
    data_quality_status: str | None = None
    assumptions: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    multi_seed_confidence: dict[str, Any] | None = None
    edge_attribution: dict[str, Any] | None = None
    gates: dict[str, Any] | None = None
    db_result_id: str | None = None


class BriefResponse(BaseModel):
    TRADE_BRIEF: dict[str, Any] | None = Field(default=None, alias='TRADE BRIEF')
    brief_meta: dict[str, Any] | None = None

    model_config = {'populate_by_name': True}
