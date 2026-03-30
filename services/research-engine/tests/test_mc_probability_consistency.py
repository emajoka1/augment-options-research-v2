import numpy as np

from ak_system.mc_options.metrics import compute_metrics


def test_compute_metrics_makes_pot_unconditional_and_bounded_by_pop():
    pl = np.array([10.0, -5.0, 2.0, -1.0])
    touch = np.array([1, 1, 1, 0])

    metrics = compute_metrics(pl, touch)

    assert metrics.pop == 0.5
    assert metrics.pot == 0.5
    assert metrics.pot <= metrics.pop


def test_compute_metrics_rejects_shape_mismatch():
    pl = np.array([1.0, -1.0])
    touch = np.array([1])

    try:
        compute_metrics(pl, touch)
    except ValueError as exc:
        assert 'touch_flags must match pl shape' in str(exc)
    else:
        raise AssertionError('expected ValueError')
