"""
Unified Semiconductor Test Data Schema & Artifact Filter.

Provides data structures compatible with standard ATE exports (STDF V4 records:
MIR, WIR, PIR, PTR, MPR, FTR, PRR and native tester CSV/Excel datalogs).

Includes detectors for test floor non-idealities:
- Contact bounce / probe touchdown glitches
- Site-to-site calibration drift and outlier test sites
- Thermal runaway during burst patterns
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple
import numpy as np


@dataclass
class ShmooTestPoint:
    """Unified single-point measurement structure across ATE formats."""
    # Identity & Location
    lot_id: str
    wafer_id: str
    die_x: int
    die_y: int
    site_id: int                            # ATE test site (1-indexed)
    head_num: int = 1                       # ATE test head number
    temperature_c: float = 25.0             # Junction/ambient temperature (C)

    # Sweep Coordinates
    vdd_v: float = 0.0                      # Supply voltage (V)
    frequency_ghz: float = 0.0              # Operating frequency (GHz)

    # Result & Failure Categorization
    test_result: Literal["PASS", "FAIL"] = "PASS"
    failure_code: str = "NA"                # FREQ_MARGIN, TIMING, CONTACT, MBIST_FAIL, etc.
    hard_bin: int = 1
    soft_bin: int = 1

    # MBIST Specific Diagnostics
    mbist_bank: Optional[int] = None        # Memory bank index
    mbist_address: Optional[int] = None     # Memory failing address
    mbist_failing_bits: Optional[int] = None # Bitmask of failing I/O or cells
    mbist_algorithm: Optional[str] = None   # March C-, Checkerboard, etc.
    memory_instance: Optional[str] = None   # SRAM instance identifier

    # Parametric & Electrical Telemetry
    current_ma: Optional[float] = None      # IDD active current
    leakage_ua: Optional[float] = None      # Standby/IDDQ leakage
    timing_ns: Optional[float] = None       # Measured critical path delay
    margin_ghz: Optional[float] = None      # Observed timing margin

    # Metadata & Quality Flags
    test_time_ms: Optional[float] = None    # Execution duration per point
    pattern_id: Optional[str] = None        # ATPG / test pattern ID
    test_num: Optional[int] = None          # STDF PTR test number
    is_contact_bounce: bool = False
    is_outlier_site: bool = False
    is_thermal_drift: bool = False


@dataclass
class ShmooSweepRun:
    """Complete Shmoo characterization sweep for a device or wafer."""
    lot_id: str
    wafer_id: str
    die_x: int
    die_y: int
    temperature_c: float
    corner: str = "TT"                      # TT, FF, SS, SF, FS
    points: List[ShmooTestPoint] = field(default_factory=list)

    @property
    def die_id(self) -> str:
        return f"{self.wafer_id}_X{self.die_x}_Y{self.die_y}"

    @property
    def total_points(self) -> int:
        return len(self.points)

    @property
    def pass_count(self) -> int:
        return sum(1 for p in self.points if p.test_result == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for p in self.points if p.test_result == "FAIL")

    @property
    def yield_rate(self) -> float:
        return self.pass_count / len(self.points) if self.points else 0.0

    def get_vmin_per_frequency(self) -> Dict[float, float]:
        """Compute minimum passing VDD for each evaluated frequency."""
        freq_map: Dict[float, List[float]] = {}
        for p in self.points:
            if p.test_result == "PASS" and not p.is_contact_bounce:
                freq_map.setdefault(round(p.frequency_ghz, 4), []).append(p.vdd_v)

        return {f: min(voltages) for f, voltages in freq_map.items()}


class TestFloorArtifactFilter:
    """Detects and flags non-ideal test floor artifacts in raw ATE datalogs."""

    @staticmethod
    def detect_contact_bounce(
        points: List[ShmooTestPoint],
        initial_touchdown_window: int = 5
    ) -> List[ShmooTestPoint]:
        """Flag probe contact bounce during the first few touchdown test points.

        If a die fails the very first 1-2 points at high VDD/low frequency but then
        immediately passes subsequent identical/stricter points, mark as CONTACT.
        """
        if len(points) <= initial_touchdown_window:
            return points

        for i in range(min(initial_touchdown_window, len(points) - 1)):
            pt = points[i]
            # If point failed, but subsequent points pass at lower/equal VDD and equal/higher frequency:
            if pt.test_result == "FAIL":
                subsequent_pass = any(
                    next_p.test_result == "PASS" and
                    next_p.vdd_v <= pt.vdd_v and
                    next_p.frequency_ghz >= pt.frequency_ghz
                    for next_p in points[i + 1 : i + 6]
                )
                if subsequent_pass:
                    pt.is_contact_bounce = True
                    pt.failure_code = "CONTACT_BOUNCE"

        return points

    @staticmethod
    def detect_site_drift(
        runs: List[ShmooSweepRun],
        threshold_sigma: float = 3.0
    ) -> Dict[int, float]:
        """Detect tester channel calibration drift and outlier test sites.

        Computes mean Vmin per test site across dies; flags sites exceeding threshold_sigma.
        Returns:
            Dict mapping site_id -> Vmin offset (drift) in mV.
        """
        site_vmins: Dict[int, List[float]] = {}

        for run in runs:
            for pt in run.points:
                if pt.test_result == "PASS" and not pt.is_contact_bounce:
                    site_vmins.setdefault(pt.site_id, []).append(pt.vdd_v)

        if not site_vmins:
            return {}

        site_means = {s: float(np.mean(vals)) for s, vals in site_vmins.items()}
        all_means = list(site_means.values())
        overall_mu = float(np.mean(all_means))
        overall_sigma = float(np.std(all_means)) if len(all_means) > 1 else 0.001

        site_offsets_mv: Dict[int, float] = {}
        for s, mu_s in site_means.items():
            delta_mv = (mu_s - overall_mu) * 1000.0
            site_offsets_mv[s] = delta_mv

            # Flag outlier sites
            if overall_sigma > 1e-4 and abs(mu_s - overall_mu) > (threshold_sigma * overall_sigma):
                for run in runs:
                    for pt in run.points:
                        if pt.site_id == s:
                            pt.is_outlier_site = True

        return site_offsets_mv

    @staticmethod
    def detect_thermal_runaway(
        points: List[ShmooTestPoint],
        current_slope_threshold: float = 2.5
    ) -> bool:
        """Detect thermal runaway via monotonic IDD current growth during burst patterns."""
        currents = [p.current_ma for p in points if p.current_ma is not None]
        if len(currents) < 10:
            return False

        # Fit linear trend to IDD vs test step
        steps = np.arange(len(currents))
        slope, _ = np.polyfit(steps, currents, 1)

        if slope > current_slope_threshold:
            for p in points:
                p.is_thermal_drift = True
            return True

        return False
