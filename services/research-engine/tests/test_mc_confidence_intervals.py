from types import SimpleNamespace

import numpy as np
import scripts.spy_free_brief as sfb


def test_confidence_interval_formula_sanity():
    sims = np.array([0.1, 0.2, 0.0, 0.15, 0.05])
    n = len(sims)
    z = 1.96
    ev = float(np.mean(sims))
    ev_se = float(np.std(sims) / np.sqrt(n))
    ci_low = ev - z * ev_se
    ci_high = ev + z * ev_se
    assert ci_low < ev < ci_high


def test_pop_confidence_interval_sanity():
    pop = 0.6
    n = 500
    pop_se = np.sqrt(pop * (1 - pop) / n)
    ci_low = max(0.0, pop - 1.96 * pop_se)
    ci_high = min(1.0, pop + 1.96 * pop_se)
    assert 0.0 <= ci_low <= pop <= ci_high <= 1.0


def test_extract_confidence_intervals_fallback_from_summary_stats():
    out = sfb.extract_confidence_intervals({'n_total_paths': 500, 'ev_mean': 0.06, 'ev_std': 0.04, 'pop_mean': 0.55})
    assert out['sampleSize'] == 500
    assert out['ev']['ci_low'] < out['ev']['value'] < out['ev']['ci_high']
    assert 0.0 <= out['pop']['ci_low'] <= out['pop']['value'] <= out['pop']['ci_high'] <= 1.0
