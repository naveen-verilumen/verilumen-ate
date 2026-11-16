"""
Classical and industry-standard search algorithms for Shmoo boundary characterization.

Implements:
1. FullGridSweep (brute-force 100% raster sweep baseline)
2. PerFrequencyBinarySearch (ATE hardware search routine: O(N_f * log2(N_v)))
3. DivideAndConquerSearch (Patten 2004 ITC algorithm: hierarchical 2D quad-tree boundary tracking)
"""

from typing import Dict, List, Optional, Set, Tuple
import numpy as np
from .base import AdaptiveSampler, BoundaryEstimate, SampleResult
from .benchmarks import BenchmarkGroundTruth


class FullGridSweep:
    """Brute force evaluation of 100% of the parameter space."""

    def __init__(self, name: str = "Full_Raster_Sweep"):
        self.name = name

    def run(self, ground_truth: BenchmarkGroundTruth) -> SampleResult:
        grid_v = ground_truth.grid_v
        grid_f = ground_truth.grid_f
        n_v = len(grid_v)
        n_f = len(grid_f)
        total_pts = n_v * n_f

        points = []
        labels = []
        for f in grid_f:
            for v in grid_v:
                res = ground_truth.evaluate(v, f)
                points.append([v, f])
                labels.append(res)

        pts_arr = np.array(points)
        lbl_arr = np.array(labels)

        # Exact Vmin from raster:
        vmin_pred = np.full(n_f, np.nan)
        for i_f, f in enumerate(grid_f):
            mask = (pts_arr[:, 1] == f) & (lbl_arr == 1)
            passing = pts_arr[mask, 0]
            if len(passing) > 0:
                vmin_pred[i_f] = np.min(passing)

        boundary = BoundaryEstimate(
            frequencies=grid_f,
            vmin_pred=vmin_pred,
            grid_v=grid_v,
            grid_f=grid_f,
            pass_probabilities=ground_truth.oracle_matrix.copy()
        )

        return SampleResult(
            algorithm_name=self.name,
            points_tested=pts_arr,
            labels_tested=lbl_arr,
            total_evaluations=total_pts,
            grid_total_points=total_pts,
            point_reduction_ratio=0.0,
            wall_clock_time_ms=0.0,
            avg_query_latency_ms=0.0,
            boundary=boundary,
            convergence_reason="100% Exhaustive sweep completed"
        )


class PerFrequencyBinarySearch:
    """Per-frequency 1D binary search for Vmin(f) along the voltage axis."""

    def __init__(self, name: str = "Binary_Search_Vmin"):
        self.name = name

    def run(self, ground_truth: BenchmarkGroundTruth) -> SampleResult:
        grid_v = ground_truth.grid_v
        grid_f = ground_truth.grid_f
        n_v = len(grid_v)
        n_f = len(grid_f)
        total_grid = n_v * n_f

        points_tested = []
        labels_tested = []
        tested_dict: Dict[Tuple[float, float], int] = {}

        def eval_pt(v: float, f: float) -> int:
            key = (round(v, 4), round(f, 4))
            if key in tested_dict:
                return tested_dict[key]
            lbl = ground_truth.evaluate(v, f)
            tested_dict[key] = lbl
            points_tested.append([v, f])
            labels_tested.append(lbl)
            return lbl

        vmin_pred = np.full(n_f, np.nan)

        for i_f, f in enumerate(grid_f):
            low = 0
            high = n_v - 1
            best_passing_v = np.nan

            # Quick check at highest VDD to see if frequency can pass at all:
            if eval_pt(grid_v[high], f) == 0:
                # Device cannot pass at any voltage for this frequency
                vmin_pred[i_f] = np.nan
                continue

            # Check at lowest VDD
            if eval_pt(grid_v[low], f) == 1:
                vmin_pred[i_f] = grid_v[low]
                continue

            # Standard binary search on monotonic transition
            while low <= high:
                mid = (low + high) // 2
                res = eval_pt(grid_v[mid], f)
                if res == 1:
                    best_passing_v = grid_v[mid]
                    high = mid - 1  # Try to find lower passing voltage
                else:
                    low = mid + 1   # Need higher voltage to pass

            vmin_pred[i_f] = best_passing_v

        pts_arr = np.array(points_tested)
        lbl_arr = np.array(labels_tested)
        tested_count = len(points_tested)

        boundary = BoundaryEstimate(
            frequencies=grid_f,
            vmin_pred=vmin_pred,
            grid_v=grid_v,
            grid_f=grid_f
        )

        return SampleResult(
            algorithm_name=self.name,
            points_tested=pts_arr,
            labels_tested=lbl_arr,
            total_evaluations=tested_count,
            grid_total_points=total_grid,
            point_reduction_ratio=1.0 - (tested_count / total_grid),
            wall_clock_time_ms=0.0,
            avg_query_latency_ms=0.0,
            boundary=boundary,
            convergence_reason="Binary search converged per frequency line"
        )


class DivideAndConquerSearch:
    """Patten (2004) Divide & Conquer fast Shmoo search algorithm.

    Hierarchically evaluates coarse boundary grid cells and selectively
    subdivides only cells containing a PASS-to-FAIL transition.
    """

    def __init__(self, name: str = "Divide_and_Conquer_2004"):
        self.name = name

    def run(self, ground_truth: BenchmarkGroundTruth) -> SampleResult:
        grid_v = ground_truth.grid_v
        grid_f = ground_truth.grid_f
        n_v = len(grid_v)
        n_f = len(grid_f)
        total_grid = n_v * n_f

        points_tested = []
        labels_tested = []
        eval_cache: Dict[Tuple[int, int], int] = {}

        def eval_idx(iv: int, jf: int) -> int:
            if (iv, jf) in eval_cache:
                return eval_cache[(iv, jf)]
            v = grid_v[iv]
            f = grid_f[jf]
            res = ground_truth.evaluate(v, f)
            eval_cache[(iv, jf)] = res
            points_tested.append([v, f])
            labels_tested.append(res)
            return res

        # Recursive subdivision on index bounding boxes [iv_min, iv_max] x [jf_min, jf_max]
        def subdivide(v0: int, v1: int, f0: int, f1: int):
            # Evaluate 4 corners of current rectangle
            c1 = eval_idx(v0, f0)
            c2 = eval_idx(v1, f0)
            c3 = eval_idx(v0, f1)
            c4 = eval_idx(v1, f1)

            # If all 4 corners are identical and box is small, stop subdividing
            if c1 == c2 == c3 == c4:
                # If rectangle is large (> 4 steps), sample midpoint to ensure no interior island
                if (v1 - v0) > 4 or (f1 - f0) > 4:
                    vm = (v0 + v1) // 2
                    fm = (f0 + f1) // 2
                    mid_val = eval_idx(vm, fm)
                    if mid_val == c1:
                        return  # Homogeneous cell, skip interior
                else:
                    return  # Homogeneous cell

            # If box cannot be subdivided further (1 step along either axis)
            if (v1 - v0) <= 1 and (f1 - f0) <= 1:
                return

            # Subdivide into 4 quadrants
            vm = (v0 + v1) // 2
            fm = (f0 + f1) // 2

            if v1 > v0 and f1 > f0:
                subdivide(v0, vm, f0, fm)
                subdivide(vm, v1, f0, fm)
                subdivide(v0, vm, fm, f1)
                subdivide(vm, v1, fm, f1)
            elif v1 > v0:
                subdivide(v0, vm, f0, f1)
                subdivide(vm, v1, f0, f1)
            elif f1 > f0:
                subdivide(v0, v1, f0, fm)
                subdivide(v0, v1, fm, f1)

        # Run hierarchical subdivision starting from full perimeter
        subdivide(0, n_v - 1, 0, n_f - 1)

        # Interpolate estimated Vmin from tested points
        pts_arr = np.array(points_tested)
        lbl_arr = np.array(labels_tested)
        tested_count = len(points_tested)

        vmin_pred = np.full(n_f, np.nan)
        for i_f, f in enumerate(grid_f):
            pass_v = [p[0] for p, l in zip(points_tested, labels_tested) if abs(p[1] - f) < 1e-4 and l == 1]
            if len(pass_v) > 0:
                vmin_pred[i_f] = min(pass_v)
            else:
                # Fallback to nearest measured frequency's trend
                vmin_pred[i_f] = np.nan

        boundary = BoundaryEstimate(
            frequencies=grid_f,
            vmin_pred=vmin_pred,
            grid_v=grid_v,
            grid_f=grid_f
        )

        return SampleResult(
            algorithm_name=self.name,
            points_tested=pts_arr,
            labels_tested=lbl_arr,
            total_evaluations=tested_count,
            grid_total_points=total_grid,
            point_reduction_ratio=1.0 - (tested_count / total_grid),
            wall_clock_time_ms=0.0,
            avg_query_latency_ms=0.0,
            boundary=boundary,
            convergence_reason="Patten Divide & Conquer subdivision finished"
        )
