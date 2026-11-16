"""Feature variants for controlled experiments. Default yi_ml_v2 columns stay unchanged."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from yield_improvement.ml.config import FeaturePolicy, load_feature_policy
from yield_improvement.ml.features import FeatureBuilder
from yield_improvement.yield_analysis.grid_region import grid_bounds, is_grid_border


def lot_relative_position(frame: pd.DataFrame) -> pd.Series:
    """Position of each row inside its lot, from timestamps only.

    Earliest timestamp in the lot is 0 and the latest is 1. Labels are not used.
    Each lot is scaled by its own timestamps, including when the frame holds several lots.
    """
    if "lot_id" not in frame.columns or "timestamp" not in frame.columns:
        return pd.Series([float("nan")] * len(frame), index=frame.index)
    stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    position = pd.Series(float("nan"), index=frame.index, dtype=float)
    for _, index in frame.groupby(frame["lot_id"].astype(str), sort=False).groups.items():
        values = stamps.loc[index]
        if values.notna().sum() == 0:
            continue
        start = values.min()
        stop = values.max()
        span = (stop - start).total_seconds()
        if span is None or span <= 0:
            position.loc[index] = 0.0
        else:
            position.loc[index] = (values - start).dt.total_seconds() / span
    return position


@dataclass
class ExperimentFeatureBuilder(FeatureBuilder):
    """16-column builder plus optional grid border and lot-relative time."""

    use_grid_border: bool = False
    use_relative_time: bool = False

    def fit(self, frame: pd.DataFrame, y: pd.Series) -> ExperimentFeatureBuilder:
        if self.use_grid_border and "x" in frame.columns and "y" in frame.columns:
            xy = frame[["x", "y"]].dropna()
            points = [(float(x), float(y_value)) for x, y_value in zip(xy["x"], xy["y"])]
            self.grid_bounds_ = grid_bounds(points) if points else None
        else:
            self.grid_bounds_ = None
        super().fit(frame, y)
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = super().transform(frame)
        bounds = getattr(self, "grid_bounds_", None)
        if self.use_grid_border and bounds is not None and "spatial_region" in out.columns:
            regions: list[str] = []
            for x, y_value in zip(out["die_x"].to_numpy(), out["die_y"].to_numpy()):
                if pd.isna(x) or pd.isna(y_value):
                    regions.append("__missing__")
                elif is_grid_border(float(x), float(y_value), bounds):
                    regions.append("BORDER")
                else:
                    regions.append("INNER")
            out = out.copy()
            out["spatial_region"] = regions
        if self.use_relative_time:
            out = out.copy()
            out["relative_position_within_lot"] = lot_relative_position(frame).to_numpy()
            if self.feature_names_ and "relative_position_within_lot" not in self.feature_names_:
                self.feature_names_.append("relative_position_within_lot")
            if self.feature_names_:
                for column in self.feature_names_:
                    if column not in out.columns:
                        out[column] = "__missing__" if column == "spatial_region" else float("nan")
                out = out[self.feature_names_]
        self._validate_derived(out.columns)
        return out


def fit_experiment_builder(
    frame: pd.DataFrame,
    y: pd.Series,
    *,
    grid_border: bool = False,
    relative_time: bool = False,
    policy: FeaturePolicy | None = None,
) -> ExperimentFeatureBuilder:
    return ExperimentFeatureBuilder(
        policy=policy or load_feature_policy(),
        use_grid_border=grid_border,
        use_relative_time=relative_time,
    ).fit(frame, y)
