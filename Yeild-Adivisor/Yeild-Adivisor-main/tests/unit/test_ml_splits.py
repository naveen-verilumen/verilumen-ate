"""Lot-aware splits never leak a lot into both train and test."""

from __future__ import annotations

import numpy as np

from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.split import make_splits


def test_no_lot_overlap():
    cfg = load_ml_config()
    groups = np.array(["L1"] * 5 + ["L2"] * 5 + ["L3"] * 5)
    strategy, splits = make_splits(groups, cfg)
    assert "lot" in strategy
    for train_idx, test_idx in splits:
        assert set(groups[train_idx]).isdisjoint(set(groups[test_idx]))
        assert len(train_idx) and len(test_idx)


def test_lolo_holds_out_each_lot():
    cfg = load_ml_config()
    groups = np.array(["A"] * 4 + ["B"] * 4 + ["C"] * 4)
    strategy, splits = make_splits(groups, cfg)
    assert strategy == "leave_one_lot_out"
    held = [set(groups[test]) for _, test in splits]
    assert set().union(*held) == {"A", "B", "C"}


def test_deterministic_oof_with_fixed_seed():
    import pandas as pd

    from yield_improvement.ml.config import load_ml_config
    from yield_improvement.ml.dataset import MLDataset
    from yield_improvement.ml.train import select_and_train

    rng = np.random.RandomState(7)
    n = 36
    lots = np.array(["A"] * 12 + ["B"] * 12 + ["C"] * 12)
    frame = pd.DataFrame(
        {
            "x": rng.uniform(-1, 1, n),
            "y": rng.uniform(-1, 1, n),
            "timestamp": ["2026-03-01T08:00:00Z"] * n,
            "tester_id": ["T01"] * n,
            "probe_card_id": ["PC-1"] * n,
            "prober_id": ["PRB-1"] * n,
            "temperature_c": rng.normal(25, 5, n),
            "voltage_v": [0.8] * n,
            "site": [0] * n,
            "lot_id": lots,
            "wafer_id": ["W"] * n,
            "die_id": [f"D{i}" for i in range(n)],
            "attempt_id": [f"E{i}" for i in range(n)],
        }
    )
    y = pd.Series((frame["x"] > 0.2).astype(int))
    data = MLDataset(frame=frame, y=y, groups=pd.Series(lots), analysis_id="det")
    cfg = load_ml_config()
    a = select_and_train(data, cfg)
    b = select_and_train(data, cfg)
    assert a.model_name == b.model_name
    assert np.allclose(a.oof_raw, b.oof_raw, atol=1e-10)
