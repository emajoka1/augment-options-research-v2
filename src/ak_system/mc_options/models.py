from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class GBMParams:
    mu: float = 0.03
    sigma: float = 0.2


@dataclass
class JumpDiffusionParams:
    mu: float = 0.03
    sigma: float = 0.2
    jump_lambda: float = 0.2
    jump_mu: float = -0.08
    jump_sigma: float = 0.20


def simulate_gbm_paths(
    S0: float,
    n_paths: int,
    n_steps: int,
    dt: float,
    params: GBMParams,
    seed: int = 42,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    z = rng.normal(size=(n_paths, n_steps))
    drift = (params.mu - 0.5 * params.sigma**2) * dt
    diff = params.sigma * np.sqrt(dt) * z
    log_rets = drift + diff

    paths = np.empty((n_paths, n_steps + 1), dtype=float)
    paths[:, 0] = S0
    paths[:, 1:] = S0 * np.exp(np.cumsum(log_rets, axis=1))
    return paths


def simulate_jump_diffusion_paths(
    S0: float,
    n_paths: int,
    n_steps: int,
    dt: float,
    params: JumpDiffusionParams,
    seed: int = 42,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    z = rng.normal(size=(n_paths, n_steps))
    n_jumps = rng.poisson(params.jump_lambda * dt, size=(n_paths, n_steps))

    jump_component = np.zeros((n_paths, n_steps), dtype=float)
    active = n_jumps > 0
    if np.any(active):
        jump_sizes = rng.lognormal(
            mean=params.jump_mu,
            sigma=params.jump_sigma,
            size=(n_paths, n_steps),
        ) - 1.0
        jump_component[active] = np.log1p(jump_sizes[active]) * n_jumps[active]

    k = np.exp(params.jump_mu + 0.5 * params.jump_sigma**2) - 1.0
    drift = (params.mu - 0.5 * params.sigma**2 - params.jump_lambda * k) * dt
    diff = params.sigma * np.sqrt(dt) * z
    log_rets = drift + diff + jump_component

    paths = np.empty((n_paths, n_steps + 1), dtype=float)
    paths[:, 0] = S0
    paths[:, 1:] = S0 * np.exp(np.cumsum(log_rets, axis=1))
    return paths
