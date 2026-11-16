"""Train-only feature builder. Unknown lots/testers get training global means. No fabricated XY."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from yield_improvement.ml.config import FeaturePolicy, LeakageError, load_feature_policy
from yield_improvement.ml.dataset import PARAM_NAMES
from yield_improvement.yield_analysis.grid_region import grid_bounds, is_grid_border

NUMERIC_BASE = [
    "die_x",
    "die_y",
    "normalized_x",
    "normalized_y",
    "radial_distance",
    "edge_distance",
    "timestamp_epoch",
    "temperature_c",
    "voltage_v",
    "site",
    "tester_fail_rate",
    "probe_fail_rate",
    "relative_position_within_lot",
]
CATEGORICAL_BASE = ["spatial_region", "tester_id", "probe_card_id", "prober_id"]


def _quantile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        return 0.0
    return float(np.quantile(values, q))


@dataclass
class FeatureBuilder:
    policy: FeaturePolicy
    radius_max_: float = 1.0
    x_min_: float = 0.0
    x_span_: float = 1.0
    y_min_: float = 0.0
    y_span_: float = 1.0
    ts_min_: float = 0.0
    edge_q_: float = 0.0
    center_q_: float = 0.0
    global_fail_rate_: float = 0.0
    tester_rate_: dict[str, float] = field(default_factory=dict)
    probe_rate_: dict[str, float] = field(default_factory=dict)
    feature_names_: list[str] = field(default_factory=list)
    numeric_features_: list[str] = field(default_factory=list)
    categorical_features_: list[str] = field(default_factory=list)

    def fit(self, frame: pd.DataFrame, y: pd.Series) -> FeatureBuilder:
        xy = frame[["x", "y"]].dropna()
        if not xy.empty:
            radii = np.hypot(xy["x"].to_numpy(float), xy["y"].to_numpy(float))
            self.radius_max_ = float(max(radii.max(), 1e-9))
            self.x_min_ = float(xy["x"].min())
            self.x_span_ = float(max(xy["x"].max() - self.x_min_, 1e-9))
            self.y_min_ = float(xy["y"].min())
            self.y_span_ = float(max(xy["y"].max() - self.y_min_, 1e-9))
            self.edge_q_ = _quantile(radii, 0.80)
            self.center_q_ = _quantile(radii, 0.20)
        ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if ts.notna().any():
            self.ts_min_ = float(ts.dropna().map(lambda t: t.timestamp()).min())
        self.global_fail_rate_ = float(y.mean()) if len(y) else 0.0
        work = frame.copy()
        work["_y"] = y.to_numpy()
        if "tester_id" in work:
            self.tester_rate_ = work.groupby("tester_id")["_y"].mean().to_dict()
        if "probe_card_id" in work:
            self.probe_rate_ = work.groupby("probe_card_id")["_y"].mean().to_dict()
        sample = self.transform(frame)
        self.feature_names_ = list(sample.columns)
        self.numeric_features_ = [c for c in sample.columns if c in NUMERIC_BASE or c in PARAM_NAMES]
        self.categorical_features_ = [c for c in sample.columns if c in CATEGORICAL_BASE]
        self._validate_derived(sample.columns)
        return self

    def _validate_derived(self, columns) -> None:
        allowed = {c.lower() for c in self.policy.allowed_derived_features}
        denied = {c.lower() for c in self.policy.denied_columns}
        bad = [c for c in columns if c.lower() not in allowed]
        if bad:
            raise LeakageError(f"Derived features not on allowlist: {bad}")
        hits = [c for c in columns if c.lower() in denied]
        if hits:
            raise LeakageError(f"Denied derived features: {hits}")

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        n = len(frame)
        xs = pd.to_numeric(frame.get("x"), errors="coerce") if "x" in frame else pd.Series([np.nan] * n)
        ys = pd.to_numeric(frame.get("y"), errors="coerce") if "y" in frame else pd.Series([np.nan] * n)
        radii = np.hypot(xs.to_numpy(dtype=float), ys.to_numpy(dtype=float))
        region = []
        for r, x, y in zip(radii, xs, ys):
            if pd.isna(x) or pd.isna(y) or np.isnan(r):
                region.append("__missing__")
            elif r >= self.edge_q_:
                region.append("EDGE")
            elif r <= self.center_q_:
                region.append("CENTER")
            else:
                region.append("OTHER")
        ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce") if "timestamp" in frame else pd.Series([pd.NaT] * n)
        ts_vals = []
        for stamp in ts:
            if pd.isna(stamp):
                ts_vals.append(np.nan)
            else:
                ts_vals.append(float(stamp.timestamp()) - self.ts_min_)
        tester = frame["tester_id"].fillna("__missing__").astype(str) if "tester_id" in frame else pd.Series(["__missing__"] * n)
        probe = frame["probe_card_id"].fillna("__missing__").astype(str) if "probe_card_id" in frame else pd.Series(["__missing__"] * n)
        prober = frame["prober_id"].fillna("__missing__").astype(str) if "prober_id" in frame else pd.Series(["__missing__"] * n)
        out = pd.DataFrame(
            {
                "die_x": xs.to_numpy(dtype=float),
                "die_y": ys.to_numpy(dtype=float),
                "normalized_x": (xs.to_numpy(dtype=float) - self.x_min_) / self.x_span_,
                "normalized_y": (ys.to_numpy(dtype=float) - self.y_min_) / self.y_span_,
                "radial_distance": radii,
                "edge_distance": self.radius_max_ - radii,
                "spatial_region": region,
                "timestamp_epoch": ts_vals,
                "temperature_c": pd.to_numeric(frame.get("temperature_c"), errors="coerce") if "temperature_c" in frame else np.nan,
                "voltage_v": pd.to_numeric(frame.get("voltage_v"), errors="coerce") if "voltage_v" in frame else np.nan,
                "site": pd.to_numeric(frame.get("site"), errors="coerce") if "site" in frame else np.nan,
                "tester_id": tester.to_numpy(),
                "probe_card_id": probe.to_numpy(),
                "prober_id": prober.to_numpy(),
                "tester_fail_rate": [self.tester_rate_.get(v, self.global_fail_rate_) for v in tester],
                "probe_fail_rate": [self.probe_rate_.get(v, self.global_fail_rate_) for v in probe],
            }
        )
        for name in PARAM_NAMES:
            if name in frame.columns:
                out[name] = pd.to_numeric(frame[name], errors="coerce")
        # Drop all-null numeric columns so we do not fabricate measurements.
        keep = []
        for col in out.columns:
            if col in CATEGORICAL_BASE:
                keep.append(col)
                continue
            if out[col].notna().any():
                keep.append(col)
        out = out[keep]
        if self.feature_names_:
            for col in self.feature_names_:
                if col not in out.columns:
                    out[col] = "__missing__" if col in CATEGORICAL_BASE else np.nan
            out = out[self.feature_names_]
        self._validate_derived(out.columns)
        return out


def fit_feature_builder(frame: pd.DataFrame, y: pd.Series, policy: FeaturePolicy | None = None) -> FeatureBuilder:
    return FeatureBuilder(policy=policy or load_feature_policy()).fit(frame, y)


class GridBorderFeatureBuilder(FeatureBuilder):
    """Same 16 columns as FeatureBuilder. spatial_region is BORDER or INNER.

    The label comes from yield_analysis.grid_region, using bounds fit on the
    training rows. It does not use distance from the origin.
    """

    def fit(self, frame: pd.DataFrame, y: pd.Series) -> GridBorderFeatureBuilder:
        xy = frame[["x", "y"]].dropna() if "x" in frame.columns and "y" in frame.columns else frame.iloc[0:0]
        points = [(float(x), float(y)) for x, y in zip(xy["x"], xy["y"])] if len(xy) else []
        self.grid_bounds_ = grid_bounds(points) if points else None
        super().fit(frame, y)
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = super().transform(frame)
        bounds = getattr(self, "grid_bounds_", None)
        if bounds is None or "spatial_region" not in out.columns:
            return out
        regions: list[str] = []
        for x, y in zip(out["die_x"].to_numpy(), out["die_y"].to_numpy()):
            if pd.isna(x) or pd.isna(y):
                regions.append("__missing__")
            elif is_grid_border(float(x), float(y), bounds):
                regions.append("BORDER")
            else:
                regions.append("INNER")
        replaced = out.copy()
        replaced["spatial_region"] = regions
        return replaced


def fit_grid_border_feature_builder(
    frame: pd.DataFrame, y: pd.Series, policy: FeaturePolicy | None = None
) -> GridBorderFeatureBuilder:
    return GridBorderFeatureBuilder(policy=policy or load_feature_policy()).fit(frame, y)
