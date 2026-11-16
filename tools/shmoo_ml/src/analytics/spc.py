"""
Statistical Process Control (SPC) & Statistical Guardbanding Module.

Implements standard semiconductor process capability indices (Cp, Cpk) derived
from measured Vmin distributions across dies against specification limits (LSL, USL).
Replaces arbitrary percentage offsets with 3-sigma / 6-sigma process spread guardbands.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import stats


@dataclass
class ProcessCapabilityMetrics:
    """NIST-compliant process capability indices and yield statistics."""
    feature_name: str
    sample_size: int
    mean: float                         # Sample mean (e.g. Mean Vmin in V)
    std_dev: float                      # Sample standard deviation (s)
    lsl: float                          # Lower Specification Limit
    usl: float                          # Upper Specification Limit
    cp: float                           # Process Capability (USL - LSL) / (6s)
    cpu: float                          # Upper capability (USL - mu) / (3s)
    cpl: float                          # Lower capability (mu - LSL) / (3s)
    cpk: float                          # Minimum capability min(cpu, cpl)
    cpk_ci_lower_95: float              # 95% Confidence Interval lower bound
    cpk_ci_upper_95: float              # 95% Confidence Interval upper bound
    expected_yield_pct: float           # Expected yield % based on normal CDF
    expected_dpmo: float                # Expected Defect Parts Per Million
    status: str                         # "CAPABLE" (Cpk >= 1.33), "MARGINAL", "INCAPABLE"


@dataclass
class StatisticalGuardband:
    """Rigorous statistical guardband recommendation replacing arbitrary offsets."""
    nominal_operating_point: float      # mu (V or GHz)
    process_sigma: float                # s
    k_factor: float                     # e.g. 3.0, 4.0, 6.0
    raw_guardband_delta: float          # k * s
    temp_derating_delta: float          # delta V for high-temp PVT margin
    aging_derating_delta: float         # delta V for NBTI/HCI reliability aging
    final_test_limit: float             # mu + k*s + temp + aging
    description: str


class StatisticalGuardbandCalculator:
    """Calculates process capability and statistical guardbands from multi-die Vmin data."""

    @staticmethod
    def calculate_cpk(
        values: np.ndarray,
        lsl: float,
        usl: float,
        feature_name: str = "Vmin"
    ) -> ProcessCapabilityMetrics:
        """Compute NIST-standard Cp and Cpk capability metrics from a distribution.

        Args:
            values: 1D array of measured parameters (e.g. Vmin across 25+ dies).
            lsl: Lower Specification Limit.
            usl: Upper Specification Limit.
            feature_name: Identifier of the analyzed parameter.

        Returns:
            ProcessCapabilityMetrics dataclass instance.
        """
        clean_vals = values[~np.isnan(values)]
        n = len(clean_vals)
        if n < 3:
            raise ValueError(f"Insufficient sample size ({n}) to compute process capability. Need at least 3 dies.")

        mu = float(np.mean(clean_vals))
        s = float(np.std(clean_vals, ddof=1))
        if s <= 1e-9:
            s = 1e-6

        # Capability formulas
        cp = (usl - lsl) / (6.0 * s)
        cpu = (usl - mu) / (3.0 * s)
        cpl = (mu - lsl) / (3.0 * s)
        cpk = min(cpu, cpl)

        # NIST 95% Confidence Interval approximation for Cpk:
        # SE = sqrt( 1/(9*n*Cpk^2) + 1/(2*(n-1)) )
        z_95 = 1.96
        if abs(cpk) > 1e-4:
            se_cpk = np.sqrt((1.0 / (9.0 * n * (cpk ** 2))) + (1.0 / (2.0 * (n - 1))))
        else:
            se_cpk = np.sqrt(1.0 / (2.0 * (n - 1)))
        ci_lower = max(0.0, cpk - z_95 * se_cpk)
        ci_upper = cpk + z_95 * se_cpk

        # Expected yield & PPM from normal distribution
        # Fraction conforming = Phi(3*cpu) + Phi(3*cpl) - 1
        p_upper_pass = stats.norm.cdf(3.0 * cpu)
        p_lower_pass = stats.norm.cdf(3.0 * cpl)
        expected_yield = float(max(0.0, (p_upper_pass + p_lower_pass - 1.0) * 100.0))
        dpmo = float(max(0.0, (1.0 - (expected_yield / 100.0)) * 1e6))

        # Industry standard threshold: Cpk >= 1.33 for capable production
        if cpk >= 1.67:
            status = "SIX_SIGMA_CAPABLE"
        elif cpk >= 1.33:
            status = "CAPABLE (Production Ready)"
        elif cpk >= 1.00:
            status = "MARGINAL (Risk of Test Escapes)"
        else:
            status = "INCAPABLE (Yield Loss Expected)"

        return ProcessCapabilityMetrics(
            feature_name=feature_name,
            sample_size=n,
            mean=mu,
            std_dev=s,
            lsl=lsl,
            usl=usl,
            cp=float(cp),
            cpu=float(cpu),
            cpl=float(cpl),
            cpk=float(cpk),
            cpk_ci_lower_95=float(ci_lower),
            cpk_ci_upper_95=float(ci_upper),
            expected_yield_pct=expected_yield,
            expected_dpmo=dpmo,
            status=status
        )

    @staticmethod
    def derive_guardband(
        vmin_distribution: np.ndarray,
        target_sigma_k: float = 3.0,
        temp_derating_v: float = 0.025,
        aging_derating_v: float = 0.015,
        target_fmax_ghz: Optional[float] = None
    ) -> StatisticalGuardband:
        """Derive rigorous 3-sigma / 6-sigma guardband voltage limits.

        V_guardband = mu_vmin + k * sigma_vmin + delta_temp + delta_aging

        Args:
            vmin_distribution: Array of measured Vmin across die population.
            target_sigma_k: Guardband factor (3.0 for 99.73%, 4.5 for high-rel, 6.0 for automotive).
            temp_derating_v: Voltage derating for hot/cold corners (default 25 mV).
            aging_derating_v: Reliability derating for NBTI/HCI (default 15 mV).
        """
        clean = vmin_distribution[~np.isnan(vmin_distribution)]
        if len(clean) == 0:
            raise ValueError("Empty Vmin distribution provided for guardband derivation.")

        mu = float(np.mean(clean))
        sigma = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.010

        process_delta = target_sigma_k * sigma
        final_limit = mu + process_delta + temp_derating_v + aging_derating_v

        desc = (
            f"{target_sigma_k:.1f}-sigma statistical guardband: Base mean {mu:.3f}V + "
            f"{process_delta*1000:.1f}mV ({target_sigma_k}*sigma) + "
            f"{temp_derating_v*1000:.1f}mV temp + {aging_derating_v*1000:.1f}mV aging"
        )

        return StatisticalGuardband(
            nominal_operating_point=mu,
            process_sigma=sigma,
            k_factor=target_sigma_k,
            raw_guardband_delta=process_delta,
            temp_derating_delta=temp_derating_v,
            aging_derating_delta=aging_derating_v,
            final_test_limit=final_limit,
            description=desc
        )
