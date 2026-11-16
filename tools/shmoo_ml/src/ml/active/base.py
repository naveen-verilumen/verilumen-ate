"""
Base classes, interfaces, and data models for Adaptive Sampling & Active Learning.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class BoundaryEstimate:
    """Estimated Shmoo boundary parameters and coordinates."""
    frequencies: np.ndarray             # Frequencies evaluated (GHz)
    vmin_pred: np.ndarray               # Predicted Vmin for each frequency (V)
    vmin_lower: Optional[np.ndarray] = None  # Lower confidence bound (V)
    vmin_upper: Optional[np.ndarray] = None  # Upper confidence bound (V)
    uncertainty: Optional[np.ndarray] = None # Epistemic uncertainty along boundary
    pass_probabilities: Optional[np.ndarray] = None # P(PASS) on the 2D grid
    grid_v: Optional[np.ndarray] = None
    grid_f: Optional[np.ndarray] = None


@dataclass
class SampleResult:
    """Telemetry and results from an active sampling or search run."""
    algorithm_name: str
    points_tested: np.ndarray           # (N, 2) array of [VDD, Freq]
    labels_tested: np.ndarray           # (N,) array of 0 (FAIL) or 1 (PASS)
    total_evaluations: int
    grid_total_points: int
    point_reduction_ratio: float        # 1 - (tested / total)
    wall_clock_time_ms: float
    avg_query_latency_ms: float
    boundary: BoundaryEstimate
    convergence_reason: str
    metadata: Dict = field(default_factory=dict)


class AdaptiveSampler(ABC):
    """Abstract interface for all active learning and search samplers."""

    def __init__(self, name: str):
        self.name = name
        self.points_history: List[Tuple[float, float]] = []
        self.labels_history: List[int] = []

    @abstractmethod
    def reset(self) -> None:
        """Reset sampler internal state for a new search."""
        pass

    @abstractmethod
    def select_next(
        self,
        candidate_points: np.ndarray,
        batch_size: int = 1
    ) -> np.ndarray:
        """Select the next point(s) to evaluate from untested candidate points.

        Args:
            candidate_points: (M, 2) array of available untested (V, F) coordinates.
            batch_size: Number of points to select for parallel ATE sites.

        Returns:
            (batch_size, 2) array of chosen points.
        """
        pass

    @abstractmethod
    def update(self, points: np.ndarray, labels: np.ndarray) -> None:
        """Update posterior model with newly observed test results.

        Args:
            points: (K, 2) evaluated coordinates [VDD, Freq].
            labels: (K,) observed results (0=FAIL, 1=PASS).
        """
        pass

    @abstractmethod
    def estimate_boundary(
        self,
        grid_v: np.ndarray,
        grid_f: np.ndarray
    ) -> BoundaryEstimate:
        """Derive the estimated Vmin(f) boundary curve and confidence intervals.

        Args:
            grid_v: 1D array of distinct voltage points in sweep space.
            grid_f: 1D array of distinct frequency points in sweep space.

        Returns:
            BoundaryEstimate object.
        """
        pass

    @abstractmethod
    def get_uncertainty_map(
        self,
        grid_v: np.ndarray,
        grid_f: np.ndarray
    ) -> np.ndarray:
        """Compute the 2D uncertainty / entropy heatmap over the test space.

        Returns:
            (len(grid_f), len(grid_v)) 2D array of uncertainty scores.
        """
        pass

    @abstractmethod
    def is_converged(self, epsilon: float = 0.05) -> bool:
        """Check whether the active learning loop has satisfied stopping criteria."""
        pass
