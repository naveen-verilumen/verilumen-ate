"""
Ground-truth synthetic benchmark generators for Shmoo boundary evaluation.

Provides 5 physically-grounded semiconductor failure signatures:
1. Linear Speedpath (classic CMOS propagation delay limit)
2. Reverse Speedpath / Thermal Inversion (non-monotonic boundary)
3. Low-VDD Wall & Hold-Time Race (strict voltage cutoffs)
4. Dynamic Logic Floor (charge-leakage failure at low frequency)
5. Resonance Notch / Harmonic Coupling (localized frequency notch)
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class BenchmarkGroundTruth:
    """Pre-computed ground truth oracle and metadata for a Shmoo sweep space."""
    name: str
    description: str
    grid_v: np.ndarray                  # 1D distinct voltage values
    grid_f: np.ndarray                  # 1D distinct frequency values
    oracle_matrix: np.ndarray           # 2D shape (n_freq, n_vdd), 1=PASS, 0=FAIL
    true_vmin: np.ndarray               # 1D array of exact Vmin per frequency (or np.nan if unpassable)
    true_fmax: np.ndarray               # 1D array of exact Fmax per voltage
    failure_mode_map: Optional[np.ndarray] = None # 2D array of failure code strings

    def evaluate(self, v: float, f: float) -> int:
        """Lookup ground truth result for nearest grid point."""
        v_idx = int(np.argmin(np.abs(self.grid_v - v)))
        f_idx = int(np.argmin(np.abs(self.grid_f - f)))
        return int(self.oracle_matrix[f_idx, v_idx])

    def evaluate_batch(self, points: np.ndarray) -> np.ndarray:
        """Evaluate an array of (V, F) coordinates."""
        results = np.zeros(len(points), dtype=int)
        for i, (v, f) in enumerate(points):
            results[i] = self.evaluate(v, f)
        return results

    @property
    def total_grid_points(self) -> int:
        return len(self.grid_v) * len(self.grid_f)


class SyntheticShmooGenerator:
    """Factory creating physically realistic Shmoo benchmarks."""

    @staticmethod
    def create_linear_speedpath(
        vdd_range: Tuple[float, float] = (0.70, 1.20),
        freq_range: Tuple[float, float] = (0.50, 3.00),
        v_steps: int = 26,
        f_steps: int = 26,
        slope: float = 3.8,
        intercept: float = -1.5,
    ) -> BenchmarkGroundTruth:
        """Standard CMOS linear speedpath: Fmax = slope * Vdd + intercept."""
        grid_v = np.linspace(vdd_range[0], vdd_range[1], v_steps)
        grid_f = np.linspace(freq_range[0], freq_range[1], f_steps)
        n_v = len(grid_v)
        n_f = len(grid_f)

        oracle = np.zeros((n_f, n_v), dtype=int)
        for i_f, f in enumerate(grid_f):
            # Physical limit: f <= slope * v + intercept  =>  v >= (f - intercept) / slope
            v_req = (f - intercept) / slope
            for i_v, v in enumerate(grid_v):
                if v >= v_req:
                    oracle[i_f, i_v] = 1

        true_vmin = np.full(n_f, np.nan)
        for i_f in range(n_f):
            passing_v = grid_v[oracle[i_f, :] == 1]
            if len(passing_v) > 0:
                true_vmin[i_f] = passing_v[0]

        true_fmax = np.full(n_v, np.nan)
        for i_v in range(n_v):
            passing_f = grid_f[oracle[:, i_v] == 1]
            if len(passing_f) > 0:
                true_fmax[i_v] = passing_f[-1]

        return BenchmarkGroundTruth(
            name="Linear_Speedpath",
            description="CMOS propagation-delay limited speedpath: Fmax = 3.8*V - 1.5",
            grid_v=grid_v,
            grid_f=grid_f,
            oracle_matrix=oracle,
            true_vmin=true_vmin,
            true_fmax=true_fmax,
        )

    @staticmethod
    def create_reverse_speedpath(
        vdd_range: Tuple[float, float] = (0.70, 1.25),
        freq_range: Tuple[float, float] = (0.50, 2.50),
        v_steps: int = 25,
        f_steps: int = 25,
        peak_v: float = 0.98,
        peak_f: float = 2.10,
    ) -> BenchmarkGroundTruth:
        """Non-monotonic Shmoo: dynamic self-heating / leakage causes Fmax degradation at high VDD."""
        grid_v = np.linspace(vdd_range[0], vdd_range[1], v_steps)
        grid_f = np.linspace(freq_range[0], freq_range[1], f_steps)
        n_v = len(grid_v)
        n_f = len(grid_f)

        oracle = np.zeros((n_f, n_v), dtype=int)
        # Quadratic concave envelope: Fmax(V) = peak_f - curvature * (V - peak_v)^2
        curvature = 18.0
        for i_v, v in enumerate(grid_v):
            f_max_v = peak_f - curvature * ((v - peak_v) ** 2)
            for i_f, f in enumerate(grid_f):
                if f <= f_max_v and v >= 0.76:
                    oracle[i_f, i_v] = 1

        true_vmin = np.full(n_f, np.nan)
        for i_f in range(n_f):
            passing_v = grid_v[oracle[i_f, :] == 1]
            if len(passing_v) > 0:
                true_vmin[i_f] = passing_v[0]

        true_fmax = np.full(n_v, np.nan)
        for i_v in range(n_v):
            passing_f = grid_f[oracle[:, i_v] == 1]
            if len(passing_f) > 0:
                true_fmax[i_v] = passing_f[-1]

        return BenchmarkGroundTruth(
            name="Reverse_Speedpath",
            description="Non-monotonic failure boundary with high-voltage thermal/leakage roll-off",
            grid_v=grid_v,
            grid_f=grid_f,
            oracle_matrix=oracle,
            true_vmin=true_vmin,
            true_fmax=true_fmax,
        )

    @staticmethod
    def create_low_vdd_wall(
        vdd_range: Tuple[float, float] = (0.70, 1.20),
        freq_range: Tuple[float, float] = (0.50, 2.80),
        v_steps: int = 26,
        f_steps: int = 24,
        v_wall: float = 0.84,
    ) -> BenchmarkGroundTruth:
        """Low VDD wall (level-shifter or SRAM retention failure) below which circuit cannot operate."""
        grid_v = np.linspace(vdd_range[0], vdd_range[1], v_steps)
        grid_f = np.linspace(freq_range[0], freq_range[1], f_steps)
        n_v = len(grid_v)
        n_f = len(grid_f)

        oracle = np.zeros((n_f, n_v), dtype=int)
        for i_v, v in enumerate(grid_v):
            if v < v_wall:
                continue  # Hard wall: fail regardless of frequency
            f_max_v = 3.2 * v - 1.1
            for i_f, f in enumerate(grid_f):
                if f <= f_max_v:
                    oracle[i_f, i_v] = 1

        true_vmin = np.full(n_f, np.nan)
        for i_f in range(n_f):
            passing_v = grid_v[oracle[i_f, :] == 1]
            if len(passing_v) > 0:
                true_vmin[i_f] = passing_v[0]

        true_fmax = np.full(n_v, np.nan)
        for i_v in range(n_v):
            passing_f = grid_f[oracle[:, i_v] == 1]
            if len(passing_f) > 0:
                true_fmax[i_v] = passing_f[-1]

        return BenchmarkGroundTruth(
            name="Low_VDD_Wall",
            description="Abrupt vertical low-voltage cutoff at 0.84V due to SRAM minimum functional VDD",
            grid_v=grid_v,
            grid_f=grid_f,
            oracle_matrix=oracle,
            true_vmin=true_vmin,
            true_fmax=true_fmax,
        )

    @staticmethod
    def create_frequency_floor(
        vdd_range: Tuple[float, float] = (0.70, 1.20),
        freq_range: Tuple[float, float] = (0.20, 2.50),
        v_steps: int = 26,
        f_steps: int = 24,
        floor_freq: float = 0.85,
    ) -> BenchmarkGroundTruth:
        """Dynamic charge leakage failure: circuit fails when frequency is TOO SLOW."""
        grid_v = np.linspace(vdd_range[0], vdd_range[1], v_steps)
        grid_f = np.linspace(freq_range[0], freq_range[1], f_steps)
        n_v = len(grid_v)
        n_f = len(grid_f)

        oracle = np.zeros((n_f, n_v), dtype=int)
        for i_v, v in enumerate(grid_v):
            f_max_v = 3.0 * v - 1.0
            for i_f, f in enumerate(grid_f):
                # Fails if frequency is below dynamic node retention limit OR above speedpath
                if floor_freq <= f <= f_max_v:
                    oracle[i_f, i_v] = 1

        true_vmin = np.full(n_f, np.nan)
        for i_f in range(n_f):
            passing_v = grid_v[oracle[i_f, :] == 1]
            if len(passing_v) > 0:
                true_vmin[i_f] = passing_v[0]

        true_fmax = np.full(n_v, np.nan)
        for i_v in range(n_v):
            passing_f = grid_f[oracle[:, i_v] == 1]
            if len(passing_f) > 0:
                true_fmax[i_v] = passing_f[-1]

        return BenchmarkGroundTruth(
            name="Frequency_Floor",
            description="Dual boundary: High-frequency speedpath + low-frequency dynamic node leakage floor",
            grid_v=grid_v,
            grid_f=grid_f,
            oracle_matrix=oracle,
            true_vmin=true_vmin,
            true_fmax=true_fmax,
        )

    @staticmethod
    def create_resonance_notch(
        vdd_range: Tuple[float, float] = (0.70, 1.20),
        freq_range: Tuple[float, float] = (0.50, 2.50),
        v_steps: int = 26,
        f_steps: int = 25,
        notch_freq_center: float = 1.45,
        notch_width: float = 0.18,
    ) -> BenchmarkGroundTruth:
        """Resonant harmonic coupling / power droop creating a finger-like notch failure."""
        grid_v = np.linspace(vdd_range[0], vdd_range[1], v_steps)
        grid_f = np.linspace(freq_range[0], freq_range[1], f_steps)
        n_v = len(grid_v)
        n_f = len(grid_f)

        oracle = np.zeros((n_f, n_v), dtype=int)
        for i_v, v in enumerate(grid_v):
            base_fmax = 2.8 * v - 0.8
            # Inject localized resonance drop:
            notch_depth = 0.55 * np.exp(-((base_fmax - notch_freq_center) ** 2) / (2 * (notch_width ** 2)))
            f_max_v = base_fmax - notch_depth

            for i_f, f in enumerate(grid_f):
                if f <= f_max_v and v >= 0.75:
                    oracle[i_f, i_v] = 1

        true_vmin = np.full(n_f, np.nan)
        for i_f in range(n_f):
            passing_v = grid_v[oracle[i_f, :] == 1]
            if len(passing_v) > 0:
                true_vmin[i_f] = passing_v[0]

        true_fmax = np.full(n_v, np.nan)
        for i_v in range(n_v):
            passing_f = grid_f[oracle[:, i_v] == 1]
            if len(passing_f) > 0:
                true_fmax[i_v] = passing_f[-1]

        return BenchmarkGroundTruth(
            name="Resonance_Notch",
            description="Non-convex notch boundary caused by clock network LC resonance harmonic coupling",
            grid_v=grid_v,
            grid_f=grid_f,
            oracle_matrix=oracle,
            true_vmin=true_vmin,
            true_fmax=true_fmax,
        )

    @classmethod
    def get_all_benchmarks(cls) -> List[BenchmarkGroundTruth]:
        """Return the standard 5-case benchmark suite."""
        return [
            cls.create_linear_speedpath(),
            cls.create_reverse_speedpath(),
            cls.create_low_vdd_wall(),
            cls.create_frequency_floor(),
            cls.create_resonance_notch(),
        ]
