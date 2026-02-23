from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .iv_dynamics import IVDynamicsParams, fit_surface_from_snapshot
from .models import GBMParams, HestonParams, JumpDiffusionParams


@dataclass
class MarketInputs:
    spot: float
    r: float = 0.03
    q: float = 0.0


@dataclass
class ChainSnapshot:
    spot: float
    strikes: np.ndarray
    ivs: np.ndarray
    expiries_days: np.ndarray | None = None
    returns: np.ndarray | None = None


@dataclass
class CalibratedPack:
    gbm: GBMParams
    jump: JumpDiffusionParams
    heston: HestonParams
    iv: IVDynamicsParams
    rv10: float | None
    rv20: float | None


def defaults_from_market(
    spot: float, iv_atm: float = 0.25
) -> tuple[GBMParams, JumpDiffusionParams, HestonParams, IVDynamicsParams]:
    gbm = GBMParams(mu=0.03, sigma=max(0.05, min(1.0, iv_atm)))
    jd = JumpDiffusionParams(mu=0.03, sigma=gbm.sigma, jump_lambda=0.25, jump_mu=-0.06, jump_sigma=0.20)
    heston = HestonParams(mu=0.03, v0=max(1e-6, iv_atm**2), theta=max(1e-6, iv_atm**2))
    iv = IVDynamicsParams(iv_atm=iv_atm, theta_iv=iv_atm)
    return gbm, jd, heston, iv


def fit_iv_params_from_snapshot(spot: float, strikes: np.ndarray, ivs: np.ndarray, expiries_days: np.ndarray | None = None) -> IVDynamicsParams:
    fit = fit_surface_from_snapshot(spot=spot, strikes=strikes, ivs=ivs)
    iv = IVDynamicsParams(iv_atm=fit["iv_atm"], skew=fit["skew"], curv=fit["curv"], theta_iv=fit["iv_atm"])

    if expiries_days is not None and len(expiries_days) == len(ivs) and len(expiries_days) > 3:
        x = np.sqrt(np.maximum(expiries_days, 1e-6) / 365.0)
        A = np.vstack([np.ones_like(x), x]).T
        beta, *_ = np.linalg.lstsq(A, ivs, rcond=None)
        iv.iv_atm = float(beta[0])
        iv.theta_iv = float(beta[0])
        iv.term = float(beta[1])
    return iv


def calibrate_jump_from_returns(returns: np.ndarray, dt: float = 1 / 252) -> JumpDiffusionParams:
    if returns.size < 20:
        return JumpDiffusionParams()

    sigma = float(np.std(returns) / np.sqrt(max(dt, 1e-10)))
    threshold = 2.0 * np.std(returns)
    jumps = returns[np.abs(returns) > threshold]
    lam = float(len(jumps) / (len(returns) * max(dt, 1e-10)))
    if jumps.size == 0:
        mu_j, sig_j = -0.05, 0.20
    else:
        mu_j = float(np.mean(jumps))
        sig_j = float(np.std(jumps) + 1e-6)

    return JumpDiffusionParams(mu=0.03, sigma=max(0.05, sigma), jump_lambda=max(0.01, lam), jump_mu=mu_j, jump_sigma=max(0.01, sig_j))


def realized_vol(returns: np.ndarray, window: int, dt: float = 1 / 252) -> float | None:
    if returns.size < window:
        return None
    x = returns[-window:]
    return float(np.std(x) / np.sqrt(max(dt, 1e-10)))


def calibrate_from_snapshot(snapshot: ChainSnapshot, dt: float = 1 / 252) -> CalibratedPack:
    iv = fit_iv_params_from_snapshot(snapshot.spot, snapshot.strikes, snapshot.ivs, snapshot.expiries_days)
    gbm, jd_default, heston, _ = defaults_from_market(snapshot.spot, iv_atm=iv.iv_atm)

    rets = snapshot.returns if snapshot.returns is not None else np.array([])
    jd = calibrate_jump_from_returns(rets, dt=dt) if rets.size else jd_default
    rv10 = realized_vol(rets, 10, dt) if rets.size else None
    rv20 = realized_vol(rets, 20, dt) if rets.size else None

    heston.v0 = max(1e-8, iv.iv_atm**2)
    heston.theta = max(1e-8, (rv20 if rv20 is not None else iv.iv_atm) ** 2)

    return CalibratedPack(gbm=gbm, jump=jd, heston=heston, iv=iv, rv10=rv10, rv20=rv20)


def parse_chain_snapshot(snapshot_file: str | Path) -> ChainSnapshot:
    p = Path(snapshot_file)
    if not p.exists():
        raise FileNotFoundError(f"Snapshot file not found: {p}")

    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        spot = float(data["spot"])
        rets = np.array(data.get("returns", []), dtype=float) if "returns" in data else None
        if "chain" in data:
            strikes = np.array([float(x["strike"]) for x in data["chain"]], dtype=float)
            ivs = np.array([float(x["iv"]) for x in data["chain"]], dtype=float)
            if all("expiry_days" in x for x in data["chain"]):
                exp = np.array([float(x["expiry_days"]) for x in data["chain"]], dtype=float)
            else:
                exp = None
        else:
            strikes = np.array(data["strikes"], dtype=float)
            ivs = np.array(data["ivs"], dtype=float)
            exp = np.array(data["expiries_days"], dtype=float) if "expiries_days" in data else None
        return ChainSnapshot(spot=spot, strikes=strikes, ivs=ivs, expiries_days=exp, returns=rets)

    if p.suffix.lower() == ".csv":
        lines = p.read_text(encoding="utf-8").splitlines()
        spot = None
        rets = None
        rows = []
        for ln in lines:
            if ln.strip().startswith("#") and "spot=" in ln:
                try:
                    spot = float(ln.split("spot=")[1].strip())
                except Exception:
                    pass
            elif ln.strip().startswith("#") and "returns=" in ln:
                try:
                    vals = ln.split("returns=")[1].strip().split(";")
                    rets = np.array([float(v) for v in vals if v], dtype=float)
                except Exception:
                    rets = None
            elif ln.strip() and not ln.strip().startswith("#"):
                rows.append(ln)
        reader = csv.DictReader(rows)
        strikes, ivs, exp = [], [], []
        has_exp = False
        for r in reader:
            strikes.append(float(r["strike"]))
            ivs.append(float(r["iv"]))
            if "expiry_days" in r and r["expiry_days"] not in (None, ""):
                has_exp = True
                exp.append(float(r["expiry_days"]))
        if spot is None:
            raise ValueError("CSV snapshot missing '# spot=<value>' comment line")
        exp_arr = np.array(exp, dtype=float) if has_exp else None
        return ChainSnapshot(spot=spot, strikes=np.array(strikes, dtype=float), ivs=np.array(ivs, dtype=float), expiries_days=exp_arr, returns=rets)

    raise ValueError("Unsupported snapshot format. Use .json or .csv")
