# Registry
from __future__ import annotations
from dataclasses import dataclass
from yield_improvement.parametric_analysis.contracts import SpecProvenance, ThresholdDirection

@dataclass(frozen=True)
class ParameterDefinition:
    parameter_name: str
    source_field: str
    unit: str
    measurement_semantics: str
    default_direction: ThresholdDirection
    is_two_sided: bool
    spec_provenance: SpecProvenance
    synthetic_reference_lower: float | None
    synthetic_reference_upper: float | None
    target_failure_code: str | None
    analysis_eligible: bool
    engineering_notes: str

PARAMETER_REGISTRY: dict[str, ParameterDefinition] = {
    'IDDQ': ParameterDefinition(
        parameter_name='IDDQ',
        source_field='measurement',
        unit='uA',
        measurement_semantics='Quiescent supply current leakage. High leakage indicates defects like bridging or oxide defects.',
        default_direction='UPPER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=None,
        synthetic_reference_upper=50.0,
        target_failure_code='IDDQ',
        analysis_eligible=True,
        engineering_notes='Strong high-tail separation observed in first-pass failing dies.',
    ),
    'VMIN': ParameterDefinition(
        parameter_name='VMIN',
        source_field='measurement',
        unit='V',
        measurement_semantics='Minimum operating voltage required for circuit functionality.',
        default_direction='UPPER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=None,
        synthetic_reference_upper=0.85,
        target_failure_code='VMIN',
        analysis_eligible=True,
        engineering_notes='High VMIN failure mode. Excursion and distribution shift heavily concentrated in Lot L004.',
    ),
    'VMAX': ParameterDefinition(
        parameter_name='VMAX',
        source_field='measurement',
        unit='V',
        measurement_semantics='Maximum operating voltage before timing breakdown or reliability wearout.',
        default_direction='LOWER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=1.05,
        synthetic_reference_upper=None,
        target_failure_code='VMAX',
        analysis_eligible=True,
        engineering_notes='Marginal lower-bound behavior. Very small specific failure count in V2 (12 dies); subject to small-sample warnings.',
    ),
    'VDD': ParameterDefinition(
        parameter_name='VDD',
        source_field='measurement',
        unit='V',
        measurement_semantics='Nominal core supply voltage rail.',
        default_direction='BAND',
        is_two_sided=True,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=0.72,
        synthetic_reference_upper=0.88,
        target_failure_code=None,
        analysis_eligible=False,
        engineering_notes='Nominal bias rail. Zero failures in dataset; values tightly centered around 0.80V.',
    ),
    'SUPPLY_CURRENT': ParameterDefinition(
        parameter_name='SUPPLY_CURRENT',
        source_field='measurement',
        unit='mA',
        measurement_semantics='Active dynamic operating supply current (IDD). Monitored against dynamic LEAKAGE test failure mechanism.',
        default_direction='UPPER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=None,
        synthetic_reference_upper=120.0,
        target_failure_code='LEAKAGE',
        analysis_eligible=False,
        engineering_notes='High pass/fail distribution overlap in V2 (|d| < 0.25). Only 9 LEAKAGE fails exist in canonical dataset. Ineligible for candidate threshold.',
    ),
    'CONTACT_RESISTANCE': ParameterDefinition(
        parameter_name='CONTACT_RESISTANCE',
        source_field='measurement',
        unit='ohm',
        measurement_semantics='Probe pin to pad contact interface resistance.',
        default_direction='UPPER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=None,
        synthetic_reference_upper=2.5,
        target_failure_code='CONTACT',
        analysis_eligible=True,
        engineering_notes='Moderate correlation with CONTACT failure code, but broad overlap with passing population.',
    ),
    'INTERCONNECT_RESISTANCE': ParameterDefinition(
        parameter_name='INTERCONNECT_RESISTANCE',
        source_field='measurement',
        unit='ohm',
        measurement_semantics='Internal interconnect metallization resistance.',
        default_direction='UPPER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=None,
        synthetic_reference_upper=8.0,
        target_failure_code=None,
        analysis_eligible=False,
        engineering_notes='No empirical separation between pass and fail dies in V2 dataset.',
    ),
    'ON_RESISTANCE': ParameterDefinition(
        parameter_name='ON_RESISTANCE',
        source_field='measurement',
        unit='ohm',
        measurement_semantics='Transistor channel on-resistance.',
        default_direction='UPPER_BOUND',
        is_two_sided=False,
        spec_provenance='SYNTHETIC_GENERATOR_REFERENCE',
        synthetic_reference_lower=None,
        synthetic_reference_upper=15.0,
        target_failure_code=None,
        analysis_eligible=False,
        engineering_notes='No empirical separation between pass and fail dies in V2 dataset.',
    ),
}
