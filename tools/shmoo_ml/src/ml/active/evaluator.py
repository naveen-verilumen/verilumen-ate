"""
Evaluation framework and benchmark runner for comparing Shmoo boundary search algorithms.

Computes:
- Mean Boundary Error (MBE in mV)
- Hausdorff Distance (worst-case deviation in mV)
- Point Reduction Ratio (PRR)
- Boundary Intersection-over-Union (IoU)
- Query step latency (ms) and wall-clock execution time
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
from .base import BoundaryEstimate, SampleResult
from .benchmarks import BenchmarkGroundTruth


@dataclass
class MetricReport:
    algorithm: str
    benchmark: str
    total_grid_points: int
    points_tested: int
    point_reduction_ratio: float        # PRR: 1 - (tested / total)
    mbe_mv: float                       # Mean Boundary Error in mV
    hausdorff_mv: float                 # Worst-case boundary error in mV
    boundary_iou: float                 # Passing region IoU (0 to 1)
    wall_clock_ms: float
    avg_latency_ms: float
    hypotheses_validated: Dict[str, bool] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    reports: List[MetricReport]

    def to_summary_table(self) -> str:
        """Format a clean markdown table of benchmark results."""
        headers = [
            "Algorithm", "Benchmark", "Pts Tested", "PRR (%)", "MBE (mV)",
            "Hausdorff (mV)", "IoU", "Latency/Query (ms)"
        ]
        col_fmt = "{:<28} | {:<22} | {:<10} | {:<8} | {:<9} | {:<14} | {:<6} | {:<18}"
        lines = []
        lines.append(col_fmt.format(*headers))
        lines.append("-" * 135)

        for r in self.reports:
            lines.append(col_fmt.format(
                r.algorithm,
                r.benchmark,
                f"{r.points_tested}/{r.total_grid_points}",
                f"{r.point_reduction_ratio * 100:.1f}%",
                f"{r.mbe_mv:.1f}",
                f"{r.hausdorff_mv:.1f}",
                f"{r.boundary_iou:.3f}",
                f"{r.avg_latency_ms:.2f}"
            ))
        return "\n".join(lines)


class ShmooBenchmarkEvaluator:
    """Evaluates sample results against ground-truth benchmarks."""

    @staticmethod
    def evaluate(
        result: SampleResult,
        ground_truth: BenchmarkGroundTruth
    ) -> MetricReport:
        true_vmin = ground_truth.true_vmin
        pred_vmin = result.boundary.vmin_pred

        # 1. Valid overlapping frequencies
        valid_mask = ~np.isnan(true_vmin) & ~np.isnan(pred_vmin)
        if np.sum(valid_mask) > 0:
            diff_v = np.abs(true_vmin[valid_mask] - pred_vmin[valid_mask])
            mbe_mv = float(np.mean(diff_v) * 1000.0)
            hausdorff_mv = float(np.max(diff_v) * 1000.0)
        else:
            mbe_mv = 999.0
            hausdorff_mv = 999.0

        # 2. Boundary IoU (Pass region overlap)
        grid_v = ground_truth.grid_v
        grid_f = ground_truth.grid_f
        n_v = len(grid_v)
        n_f = len(grid_f)
        oracle = ground_truth.oracle_matrix

        # Reconstruct predicted passing grid from pred_vmin
        pred_grid = np.zeros((n_f, n_v), dtype=int)
        for i_f in range(n_f):
            v_th = pred_vmin[i_f]
            if not np.isnan(v_th):
                pred_grid[i_f, grid_v >= v_th] = 1

        intersection = np.sum((oracle == 1) & (pred_grid == 1))
        union = np.sum((oracle == 1) | (pred_grid == 1))
        iou = float(intersection / union) if union > 0 else 1.0

        # 3. Test hypothesis evaluations:
        # H1: Point reduction >= 50%
        # H2: MBE < 15 mV
        # H3: Query latency < 10 ms (ATE real-time ceiling)
        hypotheses = {
            "H1_reduction_ge_50pct": bool(result.point_reduction_ratio >= 0.50),
            "H2_accuracy_mbe_le_15mv": bool(mbe_mv <= 15.0),
            "H3_edge_latency_le_10ms": bool(result.avg_query_latency_ms <= 10.0),
        }

        return MetricReport(
            algorithm=result.algorithm_name,
            benchmark=ground_truth.name,
            total_grid_points=result.grid_total_points,
            points_tested=result.total_evaluations,
            point_reduction_ratio=result.point_reduction_ratio,
            mbe_mv=mbe_mv,
            hausdorff_mv=hausdorff_mv,
            boundary_iou=iou,
            wall_clock_ms=result.wall_clock_time_ms,
            avg_latency_ms=result.avg_query_latency_ms,
            hypotheses_validated=hypotheses
        )
