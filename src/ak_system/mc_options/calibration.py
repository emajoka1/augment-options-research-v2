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


def defaults_from_market(
    spot: float, iv_atm: float = 0.25
) -> tuple[GBMParams, JumpDiffusionParams, HestonParams, IVDynamicsParams]:
    gbm = GBMParams(mu=0.03, sigma=max(0.05, min(1.0, iv_atm)))
    jd = JumpDiffusionParams(mu=0.03, sigma=gbm.sigma, jump_lambda=0.25, jump_mu=-0.06, jump_sigma=0.20)
    heston = HestonParams(mu=0.03, v0=max(1e-6, iv_atm**2), theta=max(1e-6, iv_atm**2))
    iv = IVDynamicsParams(iv_atm=iv_atm, theta_iv=iv_atm)
    return gbm, jd, heston, iv


def fit_iv_params_from_snapshot(spot: float, strikes: np.ndarray, ivs: np.ndarray) -> IVDynamicsParams:
    fit = fit_surface_from_snapshot(spot=spot, strikes=strikes, ivs=ivs)
    return IVDynamicsParams(iv_atm=fit["iv_atm"], skew=fit["skew"], curv=fit["curv"], theta_iv=fit["iv_atm"])


def parse_chain_snapshot(snapshot_file: str | Path) -> ChainSnapshot:
    """Parse chain snapshot from JSON or CSV.

    JSON formats supported:
      {"spot": 689.8, "chain": [{"strike": 685, "iv": 0.24}, ...]}
      {"spot": 689.8, "strikes": [...], "ivs": [...]} 

    CSV format: columns strike,iv (spot can be in first comment line: # spot=689.8)
    """
    p = Path(snapshot_file)
    if not p.exists():
        raise FileNotFoundError(f"Snapshot file not found: {p}")

    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        spot = float(data["spot"])
        if "chain" in data:
            strikes = np.array([float(x["strike"]) for x in data["chain"]], dtype=float)
            ivs = np.array([float(x["iv"]) for x in data["chain"]], dtype=float)
        else:
            strikes = np.array(data["strikes"], dtype=float)
            ivs = np.array(data["ivs"], dtype=float)
        return ChainSnapshot(spot=spot, strikes=strikes, ivs=ivs)

    if p.suffix.lower() == ".csv":
        lines = p.read_text(encoding="utf-8").splitlines()
        spot = None
        rows = []
        for ln in lines:
            if ln.strip().startswith("#") and "spot=" in ln:
                try:
                    spot = float(ln.split("spot=")[1].strip())
                except Exception:
                    pass
            elif ln.strip() and not ln.strip().startswith("#"):
                rows.append(ln)
        reader = csv.DictReader(rows)
        strikes, ivs = [], []
        for r in reader:
            strikes.append(float(r["strike"]))
            ivs.append(float(r["iv"]))
        if spot is None:
            raise ValueError("CSV snapshot missing '# spot=<value>' comment line")
        return ChainSnapshot(spot=spot, strikes=np.array(strikes, dtype=float), ivs=np.array(ivs, dtype=float))

    raise ValueError("Unsupported snapshot format. Use .json or .csv")
