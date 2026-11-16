"""Calibration is optional and never fitted on a declared test fold in isolation."""

from __future__ import annotations

import numpy as np

from yield_improvement.ml.calibration import ProbabilityCalibrator
from sklearn.metrics import brier_score_loss


def test_calibrator_clips_and_is_noop_when_unfitted():
    cal = ProbabilityCalibrator()
    raw = np.array([0.1, 0.9, 0.4])
    assert np.allclose(cal.transform(raw), raw)


def test_isotonic_fit_on_train_only():
    rng = np.random.RandomState(0)
    raw_train = rng.uniform(0, 1, size=80)
    y_train = (raw_train > 0.55).astype(int)
    raw_test = rng.uniform(0, 1, size=20)
    y_test = (raw_test > 0.55).astype(int)
    cal = ProbabilityCalibrator().fit(raw_train, y_train)
    assert cal.fitted is True
    pred = cal.transform(raw_test)
    assert pred.min() >= 0.0 and pred.max() <= 1.0
    # Test labels were not passed to fit.
    assert brier_score_loss(y_test, pred) >= 0.0


def test_feature_importance_is_predictive_not_causal():
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    from yield_improvement.ml.explain import permutation_ranks

    rng = np.random.RandomState(7)
    x = pd.DataFrame({"a": rng.normal(size=40), "b": rng.normal(size=40)})
    y = (x["a"] > 0).astype(int).to_numpy()
    pipe = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(random_state=7))])
    pipe.fit(x, y)
    ranks = permutation_ranks(pipe, x, y, seed=7)
    assert ranks[0]["feature"] == "a"
    assert ranks[0]["kind"] == "predictive_permutation_importance"
    assert "not a causal" in ranks[0]["note"].lower()
