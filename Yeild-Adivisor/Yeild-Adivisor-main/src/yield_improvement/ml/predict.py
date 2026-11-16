"""Apply a trained pipeline. Does not refit preprocessing on the scored population."""

from __future__ import annotations

import numpy as np
import pandas as pd

from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.contracts import MLPrediction
from yield_improvement.ml.features import FeatureBuilder
from yield_improvement.ml.train import TrainedBundle


def predict_frame(
    bundle: TrainedBundle,
    frame: pd.DataFrame,
    *,
    model_version: str,
    feature_set_version: str,
    calibration_version: str,
) -> list[MLPrediction]:
    x = bundle.builder.transform(frame)
    for col in bundle.feature_names:
        if col not in x.columns:
            x[col] = np.nan
    x = x[bundle.feature_names]
    raw = np.clip(bundle.pipeline.predict_proba(x)[:, 1], 0.0, 1.0)
    cal = bundle.calibrator.transform(raw)
    rows: list[MLPrediction] = []
    for i, rec in enumerate(frame.to_dict(orient="records")):
        p = float(cal[i]) if bundle.calibrator.fitted else float(raw[i])
        rows.append(
            MLPrediction(
                die_id=str(rec["die_id"]),
                lot_id=str(rec["lot_id"]),
                wafer_id=str(rec["wafer_id"]),
                predicted_probability=p,
                raw_probability=float(raw[i]),
                calibrated_probability=float(cal[i]) if bundle.calibrator.fitted else None,
                predicted_class=1 if p >= 0.5 else 0,
                model_version=model_version,
                feature_set_version=feature_set_version,
                calibration_version=calibration_version,
            )
        )
    return rows
