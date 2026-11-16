"""Isotonic calibration fitted on training lots only. Never on the held-out lot."""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression

from yield_improvement.ml.contracts import MLCalibration


class ProbabilityCalibrator:
    def __init__(self) -> None:
        self.iso: IsotonicRegression | None = None
        self.fitted = False

    def fit(self, raw: np.ndarray, y: np.ndarray) -> ProbabilityCalibrator:
        if len(np.unique(y)) < 2 or raw.size < 10:
            return self
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.iso.fit(raw, y)
        self.fitted = True
        return self

    def transform(self, raw: np.ndarray) -> np.ndarray:
        if not self.fitted or self.iso is None:
            return raw
        return np.clip(self.iso.predict(raw), 0.0, 1.0)


def calibration_record(method: str, fitted: bool, brier_raw: float | None, brier_cal: float | None) -> MLCalibration:
    note = (
        "Calibration mapped using training/validation lots only. "
        "Held-out lots are never used to fit the calibrator."
        if fitted
        else "Calibrator not fitted (insufficient class diversity or lots). raw_probability is used."
    )
    return MLCalibration(
        method=method,
        fitted=fitted,
        brier_raw=brier_raw,
        brier_calibrated=brier_cal,
        note=note,
    )
