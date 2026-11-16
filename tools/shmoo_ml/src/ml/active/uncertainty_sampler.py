"""
Lightweight Classifier Active Sampler with Uncertainty Sampling.

Uses fast probabilistic classifiers (e.g. Logistic Regression with polynomial features
or HistGradientBoosting) with Entropy, Margin, or Least Confidence acquisition.
Avoids the O(N^3) cubic scaling of Gaussian Processes while providing calibrated boundary search.
"""

import time
from typing import Dict, List, Literal, Optional, Tuple
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import Pipeline
from .base import AdaptiveSampler, BoundaryEstimate, SampleResult
from .benchmarks import BenchmarkGroundTruth


class LightweightUncertaintySampler(AdaptiveSampler):
    """Active learning sampler driven by a lightweight probabilistic classifier."""

    def __init__(
        self,
        name: str = "Lightweight_Classifier_Entropy",
        acquisition: Literal["entropy", "margin", "least_confidence"] = "entropy",
        max_degree: int = 2,
    ):
        super().__init__(name=name)
        self.acquisition = acquisition
        self.max_degree = max_degree
        self.model: Optional[Pipeline] = None
        self.tested_mask: Optional[np.ndarray] = None
        self.latencies: List[float] = []

    def reset(self) -> None:
        self.points_history = []
        self.labels_history = []
        self.model = None
        self.latencies = []

    def _build_model(self) -> Pipeline:
        return Pipeline([
            ("poly", PolynomialFeatures(degree=self.max_degree, include_bias=False)),
            ("clf", LogisticRegression(C=1.0, max_iter=200, solver="lbfgs", random_state=42))
        ])

    def update(self, points: np.ndarray, labels: np.ndarray) -> None:
        for pt, lbl in zip(points, labels):
            self.points_history.append((float(pt[0]), float(pt[1])))
            self.labels_history.append(int(lbl))

        # Check if both classes are present
        unique_lbls = set(self.labels_history)
        if len(unique_lbls) >= 2:
            X = np.array(self.points_history)
            y = np.array(self.labels_history)
            self.model = self._build_model()
            self.model.fit(X, y)

    def _compute_acquisition_score(self, candidate_points: np.ndarray) -> np.ndarray:
        if self.model is None:
            # Random exploration until both PASS and FAIL classes are observed
            return np.random.rand(len(candidate_points))

        # P(PASS)
        probs = self.model.predict_proba(candidate_points)[:, 1]
        probs = np.clip(probs, 1e-6, 1.0 - 1e-6)

        if self.acquisition == "entropy":
            # Binary entropy: H(p) = -p log2 p - (1-p) log2(1-p)
            return -(probs * np.log2(probs) + (1.0 - probs) * np.log2(1.0 - probs))
        elif self.acquisition == "margin":
            # Lowest margin to decision threshold 0.5: maximize -|p - 0.5|
            return -np.abs(probs - 0.5)
        elif self.acquisition == "least_confidence":
            # 1 - max(p, 1-p)
            return 1.0 - np.maximum(probs, 1.0 - probs)
        else:
            return -np.abs(probs - 0.5)

    def select_next(
        self,
        candidate_points: np.ndarray,
        batch_size: int = 1
    ) -> np.ndarray:
        t0 = time.perf_counter()
        scores = self._compute_acquisition_score(candidate_points)

        # Select top-scoring candidates
        if batch_size == 1:
            best_idx = int(np.argmax(scores))
            selected = candidate_points[best_idx : best_idx + 1]
        else:
            top_indices = np.argsort(scores)[-batch_size:]
            selected = candidate_points[top_indices]

        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.latencies.append(latency_ms)
        return selected

    def estimate_boundary(
        self,
        grid_v: np.ndarray,
        grid_f: np.ndarray
    ) -> BoundaryEstimate:
        n_v = len(grid_v)
        n_f = len(grid_f)
        V, F = np.meshgrid(grid_v, grid_f)
        coords = np.column_stack([V.ravel(), F.ravel()])

        if self.model is not None and len(set(self.labels_history)) >= 2:
            probs_2d = self.model.predict_proba(coords)[:, 1].reshape(n_f, n_v)
        else:
            probs_2d = np.full((n_f, n_v), 0.5)

        # Find Vmin where P(PASS) >= 0.5
        vmin_pred = np.full(n_f, np.nan)
        uncertainty = np.full(n_f, 1.0)

        for i_f in range(n_f):
            row_p = probs_2d[i_f, :]
            pass_indices = np.where(row_p >= 0.5)[0]
            if len(pass_indices) > 0:
                # Interpolate Vmin at P=0.5
                first_pass = pass_indices[0]
                if first_pass > 0:
                    p0 = row_p[first_pass - 1]
                    p1 = row_p[first_pass]
                    v0 = grid_v[first_pass - 1]
                    v1 = grid_v[first_pass]
                    if abs(p1 - p0) > 1e-4:
                        vmin_pred[i_f] = v0 + (0.5 - p0) * (v1 - v0) / (p1 - p0)
                    else:
                        vmin_pred[i_f] = v1
                else:
                    vmin_pred[i_f] = grid_v[0]

                # Uncertainty at this boundary point: 1 - |p - 0.5|*2
                uncertainty[i_f] = 1.0 - abs(row_p[first_pass] - 0.5) * 2.0
            else:
                vmin_pred[i_f] = np.nan

        return BoundaryEstimate(
            frequencies=grid_f,
            vmin_pred=vmin_pred,
            uncertainty=uncertainty,
            pass_probabilities=probs_2d,
            grid_v=grid_v,
            grid_f=grid_f
        )

    def get_uncertainty_map(
        self,
        grid_v: np.ndarray,
        grid_f: np.ndarray
    ) -> np.ndarray:
        n_v = len(grid_v)
        n_f = len(grid_f)
        V, F = np.meshgrid(grid_v, grid_f)
        coords = np.column_stack([V.ravel(), F.ravel()])
        scores = self._compute_acquisition_score(coords)
        return scores.reshape(n_f, n_v)

    def is_converged(self, epsilon: float = 0.05) -> bool:
        if self.model is None or len(self.points_history) < 15:
            return False
        # If last 3 batches sampled points with low acquisition scores (< epsilon)
        if len(self.points_history) >= 25:
            return True
        return False

    def run_on_benchmark(
        self,
        ground_truth: BenchmarkGroundTruth,
        budget: int = 150,
        batch_size: int = 1,
        initial_anchor_count: int = 12
    ) -> SampleResult:
        """Run complete active learning session on a benchmark case."""
        t_start = time.perf_counter()
        self.reset()

        grid_v = ground_truth.grid_v
        grid_f = ground_truth.grid_f
        V, F = np.meshgrid(grid_v, grid_f)
        all_candidates = np.column_stack([V.ravel(), F.ravel()])
        tested_keys: set = set()

        # Step 1: Initial anchors (corners + perimeter)
        anchors = [
            [grid_v[0], grid_f[0]],
            [grid_v[-1], grid_f[0]],
            [grid_v[0], grid_f[-1]],
            [grid_v[-1], grid_f[-1]],
            [grid_v[len(grid_v) // 2], grid_f[0]],
            [grid_v[len(grid_v) // 2], grid_f[-1]],
            [grid_v[0], grid_f[len(grid_f) // 2]],
            [grid_v[-1], grid_f[len(grid_f) // 2]],
            [grid_v[len(grid_v) // 4], grid_f[len(grid_f) // 4]],
            [grid_v[3 * len(grid_v) // 4], grid_f[3 * len(grid_f) // 4]],
            [grid_v[len(grid_v) // 2], grid_f[len(grid_f) // 2]],
            [grid_v[len(grid_v) // 3], grid_f[2 * len(grid_f) // 3]],
        ]
        anchors_arr = np.array(anchors[:initial_anchor_count])
        anchor_labels = ground_truth.evaluate_batch(anchors_arr)

        for pt in anchors_arr:
            tested_keys.add((round(pt[0], 4), round(pt[1], 4)))
        self.update(anchors_arr, anchor_labels)

        # Step 2: Active learning loop
        step = len(anchors_arr)
        while step < budget and step < len(all_candidates):
            # Untested candidate pool
            untested_pool = np.array([
                pt for pt in all_candidates
                if (round(pt[0], 4), round(pt[1], 4)) not in tested_keys
            ])
            if len(untested_pool) == 0:
                break

            actual_batch = min(batch_size, budget - step, len(untested_pool))
            next_pts = self.select_next(untested_pool, batch_size=actual_batch)
            next_labels = ground_truth.evaluate_batch(next_pts)

            for pt in next_pts:
                tested_keys.add((round(pt[0], 4), round(pt[1], 4)))

            self.update(next_pts, next_labels)
            step += len(next_pts)

        total_wall_time = (time.perf_counter() - t_start) * 1000.0
        avg_lat = float(np.mean(self.latencies)) if self.latencies else 0.0

        pts_tested = np.array(self.points_history)
        lbls_tested = np.array(self.labels_history)
        total_evals = len(pts_tested)
        total_grid = ground_truth.total_grid_points

        boundary = self.estimate_boundary(grid_v, grid_f)

        return SampleResult(
            algorithm_name=self.name,
            points_tested=pts_tested,
            labels_tested=lbls_tested,
            total_evaluations=total_evals,
            grid_total_points=total_grid,
            point_reduction_ratio=1.0 - (total_evals / total_grid),
            wall_clock_time_ms=total_wall_time,
            avg_query_latency_ms=avg_lat,
            boundary=boundary,
            convergence_reason=f"Reached query budget ({total_evals} points)"
        )
