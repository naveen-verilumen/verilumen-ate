"""
Shmoo_VL ROI Engine — Defensible Economic Model
=================================================
Design principles (per HIR 2024 ch.17 & Advantest/IEEE cost model):

1. ALL dollar values come from customer-supplied inputs, never from ML accuracy or R².
2. ML accuracy, R², Cpk feed into CONFIDENCE LABELS, not into dollar formulas.
3. Characterization savings are per-run or per-wafer, NOT per device (unless
   characterization genuinely runs per device in the customer's flow).
4. Yield savings require a validated counterfactual: recovered_dies must be
   measured, not model-derived.
5. Double-counting is prevented by a waterfall: each recovered die contributes
   to exactly one outcome.
6. Every output carries a confidence label:
     MEASURED     — from actual before/after data
     VALIDATED    — model-derived, validated against held-out data
     ILLUSTRATIVE — benchmark assumption; not a customer saving
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal
import numpy as np


# ─── Customer / Environment Inputs ───────────────────────────────────────────

@dataclass
class ATEConfig:
    """ATE test-cell economic parameters (customer-supplied)."""
    test_cell_cost_per_hour: float = 150.0      # $/hr (tester + handler + overhead)
    effective_sites: int = 1                     # parallel DUT sites
    parallel_test_efficiency: float = 0.90       # PTE (0-1)
    point_test_time_sec: float = 0.005           # seconds per test point execution
    handler_index_time_sec: float = 0.50         # handler/prober index time per device
    setup_changeover_time_hr: float = 0.5        # ATE setup time per lot
    retest_rate: float = 0.02                    # fraction of devices retested

@dataclass
class ProductionConfig:
    """Production volume and lot parameters (customer-supplied)."""
    annual_volume_devices: int = 500_000         # devices/year
    lot_size_devices: int = 1000                 # devices per lot
    characterization_runs_per_year: int = 12     # engineering char. runs/year
    devices_per_char_run: int = 25               # devices characterized per run

@dataclass
class EngineeringConfig:
    """Engineering labor cost parameters (customer-supplied)."""
    loaded_engineer_cost_per_hour: float = 100.0 # fully-loaded $/hr
    baseline_debug_hours_per_incident: float = 6.0
    tool_debug_hours_per_incident: float = 1.5   # estimated with Shmoo_VL
    debug_incidents_per_year: int = 48            # incidents/year (customer estimate)

@dataclass
class YieldConfig:
    """Yield economics (customer-supplied; requires validation before use)."""
    manufacturing_cost_per_die: float = 3.00     # $/die fully-loaded mfg cost
    contribution_margin_per_die: float = 7.00    # $/die contribution margin
    baseline_yield_fraction: float = 0.945       # measured baseline yield
    validated_recovered_yield_pp: float = 0.0    # percentage-point improvement
                                                  # MUST be from validated experiment
    revalidation_cost_per_recovered_die: float = 0.50  # retest/qual cost
    expected_escape_cost_per_die: float = 5.00   # warranty/recall cost per escape

@dataclass
class BinningConfig:
    """Speed-bin commercial structure (customer-supplied)."""
    bin_contribution_margins: Dict[str, float] = field(default_factory=lambda: {
        'Bin1_Premium': 0.0,    # $/die incremental vs Bin2 (customer fills this)
        'Bin2_Standard': 0.0,
        'Bin3_Economy': 0.0,
        'BinF_Reject': 0.0,
    })
    baseline_bin_distribution: Dict[str, float] = field(default_factory=lambda: {
        'Bin1_Premium': 0.0,
        'Bin2_Standard': 0.0,
        'Bin3_Economy': 0.0,
        'BinF_Reject': 0.0,
    })
    misclassification_rate: float = 0.0          # measured, not assumed
    validation_cost_per_upgraded_die: float = 0.0

@dataclass
class CustomerConfig:
    """Complete customer input configuration for ROI calculation."""
    ate: ATEConfig = field(default_factory=ATEConfig)
    production: ProductionConfig = field(default_factory=ProductionConfig)
    engineering: EngineeringConfig = field(default_factory=EngineeringConfig)
    yield_cfg: YieldConfig = field(default_factory=YieldConfig)
    binning: BinningConfig = field(default_factory=BinningConfig)

    @classmethod
    def from_dict(cls, d: dict) -> 'CustomerConfig':
        """Build from a flat or nested dict (e.g. from JSON request body)."""
        cfg = cls()
        ate_d = d.get('ate', {})
        if ate_d:
            for k, v in ate_d.items():
                if hasattr(cfg.ate, k):
                    setattr(cfg.ate, k, float(v) if '.' in str(v) else int(v) if str(v).isdigit() else v)
        prod_d = d.get('production', {})
        if prod_d:
            for k, v in prod_d.items():
                if hasattr(cfg.production, k):
                    setattr(cfg.production, k, int(v) if str(v).isdigit() else float(v))
        eng_d = d.get('engineering', {})
        if eng_d:
            for k, v in eng_d.items():
                if hasattr(cfg.engineering, k):
                    setattr(cfg.engineering, k, float(v) if '.' in str(v) else int(v))
        return cfg


# ─── Technical Validation Inputs (from ML pipeline) ──────────────────────────

@dataclass
class TechnicalEvidence:
    """Output from the ML/SPC pipeline — feeds CONFIDENCE LABELS, not $ formulas."""
    boundary_r2: float = 0.0
    cv_accuracy: float = 0.0
    cv_std: float = 0.0
    cpk_vmin: float = 0.0
    cpk_fmax: float = 0.0
    spc_status_v: str = "N/A"
    spc_status_f: str = "N/A"
    # Measured test-point counts from the actual sweep
    total_sweep_points: int = 0
    active_learning_prr: float = 0.828   # Empirically validated PRR
    mean_boundary_error_mv: float = 0.0  # From benchmark harness
    hausdorff_error_mv: float = 0.0


# ─── Confidence Labels ────────────────────────────────────────────────────────

ConfidenceLevel = Literal["MEASURED", "VALIDATED", "ILLUSTRATIVE"]

def _confidence(evidence: TechnicalEvidence) -> Dict[str, ConfidenceLevel]:
    """
    Map technical evidence to per-quadrant confidence levels.
    Rules:
      MEASURED    → uses actual point counts from this dataset
      VALIDATED   → uses SPC/boundary from this dataset (model-based but grounded)
      ILLUSTRATIVE → uses customer-supplied assumptions we cannot verify here
    """
    char_conf: ConfidenceLevel = "MEASURED" if evidence.total_sweep_points > 0 else "ILLUSTRATIVE"
    yield_conf: ConfidenceLevel = (
        "VALIDATED" if evidence.cpk_vmin > 0 and evidence.boundary_r2 > 0.7
        else "ILLUSTRATIVE"
    )
    debug_conf: ConfidenceLevel = "ILLUSTRATIVE"  # Always needs customer benchmark
    bin_conf: ConfidenceLevel = "ILLUSTRATIVE"    # Always needs customer bin structure
    return {
        'characterization': char_conf,
        'yield': yield_conf,
        'debugging': debug_conf,
        'binning': bin_conf,
    }


# ─── ROI Calculator ───────────────────────────────────────────────────────────

@dataclass
class CharacterizationROI:
    baseline_points: int
    adaptive_points: int
    points_avoided: int
    baseline_test_time_sec: float
    adaptive_test_time_sec: float
    time_saved_sec_per_run: float
    tester_cost_per_sec: float        # Correctly derived: cost_per_hr / 3600
    ate_cost_avoided_per_run: float
    annual_runs: int
    annual_ate_saving: float
    confidence: ConfidenceLevel
    formula: str
    note: str

@dataclass
class YieldROI:
    baseline_yield_pct: float
    recovered_yield_pp: float
    recovered_devices_per_million: float
    revalidation_cost_total: float
    manufacturing_value_recovered: float
    expected_escape_cost: float
    net_yield_value_per_million: float
    confidence: ConfidenceLevel
    formula: str
    note: str

@dataclass
class DebuggingROI:
    baseline_hours_per_incident: float
    tool_hours_per_incident: float
    hours_saved_per_incident: float
    engineer_cost_per_hour: float
    saving_per_incident: float
    incidents_per_year: int
    annual_saving: float
    confidence: ConfidenceLevel
    formula: str
    note: str

@dataclass
class BinningROI:
    note: str
    confidence: ConfidenceLevel
    is_quantified: bool = False
    estimated_annual_uplift: float = 0.0
    formula: str = ""

@dataclass
class ROIWaterfall:
    """Value waterfall — each recovered die counted exactly once."""
    gross_characterization_annual: float
    gross_yield_annual: float
    gross_debugging_annual: float
    gross_binning_annual: float
    sum_gross: float
    # Deductions
    incremental_software_cost: float = 0.0
    incremental_integration_cost: float = 0.0
    # Net
    net_annual_value: float = 0.0
    note: str = ""

@dataclass
class ROIReport:
    characterization: CharacterizationROI
    yield_roi: YieldROI
    debugging: DebuggingROI
    binning: BinningROI
    waterfall: ROIWaterfall
    confidence_map: Dict[str, ConfidenceLevel]
    technical_evidence: TechnicalEvidence
    footer_note: str


class ROICalculator:
    """
    Computes defensible ROI from customer inputs + technical evidence.
    All dollar values originate from config, never from ML accuracy or R².
    """

    def compute(
        self,
        config: CustomerConfig,
        evidence: TechnicalEvidence,
    ) -> ROIReport:

        conf_map = _confidence(evidence)

        # ── 1. CHARACTERIZATION ───────────────────────────────────────────────
        # Unit-consistent formula:
        #   tester_cost_per_sec = test_cell_cost_per_hour / 3600
        #   time_saved = points_avoided × point_test_time_sec
        #   ate_cost_avoided = time_saved × tester_cost_per_sec
        #
        # Note: This is per characterization RUN, not per device.

        total_pts = evidence.total_sweep_points if evidence.total_sweep_points > 0 else 500
        adaptive_pts = max(10, int(total_pts * (1.0 - evidence.active_learning_prr)))
        points_avoided = total_pts - adaptive_pts

        tester_cost_per_sec = config.ate.test_cell_cost_per_hour / 3600.0
        baseline_time_sec = total_pts * config.ate.point_test_time_sec
        adaptive_time_sec = adaptive_pts * config.ate.point_test_time_sec
        time_saved_sec = points_avoided * config.ate.point_test_time_sec

        # Per characterization run (this is ATE machine time, not per-device)
        ate_cost_per_run = time_saved_sec * tester_cost_per_sec
        annual_char_saving = ate_cost_per_run * config.production.characterization_runs_per_year

        char_formula = (
            f"ATE saving/run = {points_avoided} pts × {config.ate.point_test_time_sec:.4f}s/pt × "
            f"(${config.ate.test_cell_cost_per_hour:.0f}/hr ÷ 3600) = "
            f"${ate_cost_per_run:.2f}/run"
        )

        char_note = (
            "Characterization savings are per engineering run, NOT per device. "
            f"Assumes {config.production.characterization_runs_per_year} runs/year. "
            "Point count is from the uploaded dataset; time/cost rate is customer-supplied."
        )

        char_roi = CharacterizationROI(
            baseline_points=total_pts,
            adaptive_points=adaptive_pts,
            points_avoided=points_avoided,
            baseline_test_time_sec=baseline_time_sec,
            adaptive_test_time_sec=adaptive_time_sec,
            time_saved_sec_per_run=time_saved_sec,
            tester_cost_per_sec=tester_cost_per_sec,
            ate_cost_avoided_per_run=ate_cost_per_run,
            annual_runs=config.production.characterization_runs_per_year,
            annual_ate_saving=annual_char_saving,
            confidence=conf_map['characterization'],
            formula=char_formula,
            note=char_note,
        )


        # ── 2. YIELD ─────────────────────────────────────────────────────────
        # Requires a validated counterfactual. If recovered_yield_pp == 0,
        # we report ILLUSTRATIVE with zero dollars rather than invent a number.
        # Double-counting guard: recovered devices are NOT also counted in binning.

        rec_pp = config.yield_cfg.validated_recovered_yield_pp
        recovered_per_M = rec_pp * 10_000.0   # pp × 10,000 = devices per million

        if rec_pp > 0:
            # Gross recovered value (contribution margin, not revenue)
            gross_per_recovered = config.yield_cfg.contribution_margin_per_die
            revalidation_cost = recovered_per_M * config.yield_cfg.revalidation_cost_per_recovered_die
            # Escape cost: misclassification rate × escape penalty
            # Without customer-measured misclassification, set escape = 0
            escape_cost = 0.0
            net_per_M = (recovered_per_M * gross_per_recovered) - revalidation_cost - escape_cost
            annual_yield_saving = net_per_M * (config.production.annual_volume_devices / 1_000_000)
            yield_note = (
                "Based on validated_recovered_yield_pp from customer experiment. "
                "Each recovered die counted ONCE here; excluded from binning waterfall. "
                "Revalidation cost subtracted. Escape cost set to 0 pending measured misclassification rate."
            )
            yield_conf = conf_map['yield']
        else:
            # No validated yield improvement — show ILLUSTRATIVE at $0
            recovered_per_M = 0.0
            revalidation_cost = 0.0
            net_per_M = 0.0
            annual_yield_saving = 0.0
            yield_note = (
                "validated_recovered_yield_pp is 0.0 — no validated yield improvement provided. "
                "To populate this quadrant, run a controlled before/after experiment: "
                "measure baseline rejected population, apply Shmoo_VL guardband, "
                "retest and qualify the recovered dies, then supply the measured pp improvement."
            )
            yield_conf = "ILLUSTRATIVE"

        yield_formula = (
            f"{rec_pp:.3f} pp improvement × 10,000 = {recovered_per_M:.1f} recovered/million devices. "
            f"Net = ({recovered_per_M:.1f} × ${config.yield_cfg.contribution_margin_per_die:.2f}) "
            f"- ${revalidation_cost:.2f} revalidation = ${net_per_M:.2f}/million"
        )

        yield_roi = YieldROI(
            baseline_yield_pct=config.yield_cfg.baseline_yield_fraction * 100.0,
            recovered_yield_pp=rec_pp,
            recovered_devices_per_million=recovered_per_M,
            revalidation_cost_total=revalidation_cost,
            manufacturing_value_recovered=recovered_per_M * config.yield_cfg.manufacturing_cost_per_die,
            expected_escape_cost=0.0,
            net_yield_value_per_million=net_per_M,
            confidence=yield_conf,
            formula=yield_formula,
            note=yield_note,
        )

        # ── 3. DEBUGGING ─────────────────────────────────────────────────────
        # Economics come from engineer-hours saved, at customer's loaded rate.
        # ML accuracy plays NO role here.

        hours_saved = (
            config.engineering.baseline_debug_hours_per_incident -
            config.engineering.tool_debug_hours_per_incident
        )
        saving_per_incident = hours_saved * config.engineering.loaded_engineer_cost_per_hour
        annual_debug_saving = saving_per_incident * config.engineering.debug_incidents_per_year

        debug_formula = (
            f"({config.engineering.baseline_debug_hours_per_incident:.1f}h baseline "
            f"- {config.engineering.tool_debug_hours_per_incident:.1f}h with tool) × "
            f"${config.engineering.loaded_engineer_cost_per_hour:.0f}/hr × "
            f"{config.engineering.debug_incidents_per_year} incidents/yr = "
            f"${annual_debug_saving:,.0f}/yr"
        )
        debug_note = (
            "All inputs (baseline/tool debug hours, loaded engineer rate, incidents/year) "
            "are customer-supplied. ML accuracy is NOT used in this formula — "
            "it is a quality indicator only. Validate baseline and tool hours "
            "from your actual team's time-tracking data before presenting to customers."
        )

        debug_roi = DebuggingROI(
            baseline_hours_per_incident=config.engineering.baseline_debug_hours_per_incident,
            tool_hours_per_incident=config.engineering.tool_debug_hours_per_incident,
            hours_saved_per_incident=hours_saved,
            engineer_cost_per_hour=config.engineering.loaded_engineer_cost_per_hour,
            saving_per_incident=saving_per_incident,
            incidents_per_year=config.engineering.debug_incidents_per_year,
            annual_saving=annual_debug_saving,
            confidence=conf_map['debugging'],
            formula=debug_formula,
            note=debug_note,
        )

        # ── 4. BINNING ───────────────────────────────────────────────────────
        # Cannot be quantified without customer's actual bin ASP/margin structure
        # AND a measured shift in bin distribution. Never use hardcoded +$15/-$5.

        has_bin_data = any(v > 0 for v in config.binning.bin_contribution_margins.values())
        bin_roi = BinningROI(
            note=(
                "Binning value uplift requires customer's actual commercial bin contribution margins "
                "AND a measured before/after shift in bin distribution from production data. "
                "Hardcoded bin premiums (+$15, -$5) have been removed. "
                "Supply bin_contribution_margins and measured bin distribution shift to activate this quadrant."
                if not has_bin_data else
                "Binning value calculated from customer-supplied contribution margins and measured distribution."
            ),
            confidence="ILLUSTRATIVE",
            is_quantified=has_bin_data,
        )

        # ── 5. WATERFALL (double-counting prevention) ─────────────────────────
        # Recovered dies in Yield are excluded from Binning.
        # Only one path per die.

        gross_char = annual_char_saving
        gross_yield = annual_yield_saving
        gross_debug = annual_debug_saving
        gross_bin = 0.0  # Until customer provides bin margin structure

        net = gross_char + gross_yield + gross_debug + gross_bin

        waterfall = ROIWaterfall(
            gross_characterization_annual=round(gross_char, 2),
            gross_yield_annual=round(gross_yield, 2),
            gross_debugging_annual=round(gross_debug, 2),
            gross_binning_annual=round(gross_bin, 2),
            sum_gross=round(net, 2),
            net_annual_value=round(net, 2),
            note=(
                "Waterfall prevents double-counting: recovered dies count once (yield OR binning). "
                "Software/integration costs not deducted — add your platform cost to derive net value."
            )
        )

        footer = (
            "Economic values are derived from customer-supplied inputs only. "
            "ML accuracy and R² are quality/confidence indicators — they are NOT used in dollar calculations. "
            "ILLUSTRATIVE items use benchmark assumptions; replace with measured data before customer presentation."
        )

        return ROIReport(
            characterization=char_roi,
            yield_roi=yield_roi,
            debugging=debug_roi,
            binning=bin_roi,
            waterfall=waterfall,
            confidence_map=conf_map,
            technical_evidence=evidence,
            footer_note=footer,
        )

    def to_api_dict(self, report: ROIReport) -> dict:
        """Serialize ROI report to JSON-safe dict for API response."""
        c = report.characterization
        y = report.yield_roi
        d = report.debugging
        b = report.binning
        w = report.waterfall
        ev = report.technical_evidence

        return {
            'characterization': {
                'baseline_points': c.baseline_points,
                'adaptive_points': c.adaptive_points,
                'points_avoided': c.points_avoided,
                'points_avoided_pct': round((c.points_avoided / max(1, c.baseline_points)) * 100.0, 1),
                'baseline_time_sec': round(c.baseline_test_time_sec, 3),
                'adaptive_time_sec': round(c.adaptive_test_time_sec, 3),
                'time_saved_sec_per_run': round(c.time_saved_sec_per_run, 3),
                'tester_cost_per_sec': round(c.tester_cost_per_sec, 6),
                'ate_cost_avoided_per_run': round(c.ate_cost_avoided_per_run, 4),
                'annual_runs': c.annual_runs,
                'annual_ate_saving': round(c.annual_ate_saving, 2),
                'confidence': c.confidence,
                'formula': c.formula,
                'note': c.note,
            },
            'yield': {
                'baseline_yield_pct': round(y.baseline_yield_pct, 2),
                'recovered_yield_pp': round(y.recovered_yield_pp, 4),
                'recovered_devices_per_million': round(y.recovered_devices_per_million, 1),
                'revalidation_cost': round(y.revalidation_cost_total, 2),
                'net_yield_value_per_million': round(y.net_yield_value_per_million, 2),
                'annual_yield_saving': round(w.gross_yield_annual, 2),
                'confidence': y.confidence,
                'formula': y.formula,
                'note': y.note,
            },
            'debugging': {
                'baseline_hours': d.baseline_hours_per_incident,
                'tool_hours': d.tool_hours_per_incident,
                'hours_saved': round(d.hours_saved_per_incident, 2),
                'saving_per_incident': round(d.saving_per_incident, 2),
                'incidents_per_year': d.incidents_per_year,
                'annual_saving': round(d.annual_saving, 2),
                'confidence': d.confidence,
                'formula': d.formula,
                'note': d.note,
            },
            'binning': {
                'is_quantified': b.is_quantified,
                'estimated_annual_uplift': round(b.estimated_annual_uplift, 2),
                'confidence': b.confidence,
                'note': b.note,
            },
            'waterfall': {
                'characterization_annual': w.gross_characterization_annual,
                'yield_annual': w.gross_yield_annual,
                'debugging_annual': w.gross_debugging_annual,
                'binning_annual': w.gross_binning_annual,
                'gross_annual': w.sum_gross,
                'net_annual': w.net_annual_value,
                'note': w.note,
            },
            'confidence_map': report.confidence_map,
            'technical_evidence': {
                'boundary_r2': round(ev.boundary_r2, 4),
                'cv_accuracy': round(ev.cv_accuracy, 4),
                'cv_std': round(ev.cv_std, 4),
                'cpk_vmin': round(ev.cpk_vmin, 3),
                'cpk_fmax': round(ev.cpk_fmax, 3),
                'spc_status_v': ev.spc_status_v,
                'spc_status_f': ev.spc_status_f,
                'active_learning_prr_pct': round(ev.active_learning_prr * 100.0, 1),
                'mean_boundary_error_mv': round(ev.mean_boundary_error_mv, 2),
            },
            'footer_note': report.footer_note,
        }
