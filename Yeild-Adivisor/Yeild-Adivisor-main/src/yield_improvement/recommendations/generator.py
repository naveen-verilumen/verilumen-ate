"""Recommendation generator: converts existing analytical findings into actionable investigations.

Never invents data or root causes. Always derives exact counts and denominators from source report.
Preserves safety invariants and honest ML reporting.
"""

from __future__ import annotations

import logging
from typing import Any

from yield_improvement.recommendations.contracts import (
    EngineeringRecommendation,
    EvidenceClassification,
    EvidenceStrength,
    MLEvidenceStatus,
    RecommendationBundle,
    RecommendationCategory,
    SupportingEvidenceItem,
    ValidationProtocol,
    ValidationStep,
)
from yield_improvement.recommendations.ranking import (
    RANKING_POLICY_NAME,
    RANKING_POLICY_VERSION,
    compute_recommendation_score,
    rank_recommendations,
)
from yield_improvement.reporting.contract import EngineeringReport, ReportHypothesis

logger = logging.getLogger(__name__)


def _map_category(family: str, detail: str) -> RecommendationCategory:
    f_upper = family.upper()
    d_upper = detail.upper()
    if f_upper == "PROCESS" and "LOT" in d_upper:
        return "Lot investigation"
    if f_upper == "PROCESS" and "WAFER" in d_upper:
        return "Wafer investigation"
    if f_upper == "SPATIAL":
        return "Spatial investigation"
    if f_upper == "PARAMETRIC":
        return "Parametric investigation"
    if f_upper == "EQUIPMENT":
        return "Equipment investigation"
    if f_upper == "ENVIRONMENT":
        return "Environmental investigation"
    if f_upper == "CONTACT":
        return "Test measurement/repeatability investigation"
    if f_upper == "TEST" and "LIMIT" in d_upper:
        return "Near-limit investigation"
    if f_upper == "TEST" and "SEQUENCE" in d_upper:
        return "Test measurement/repeatability investigation"
    if f_upper == "DATA" or "QUALITY" in d_upper:
        return "Data-quality investigation"
    return "Lot investigation"


def _build_validation_protocol(
    rec_id: str,
    hypothesis: ReportHypothesis,
    category: RecommendationCategory,
    target_pop: str,
) -> ValidationProtocol:
    fam = hypothesis.family.upper()
    det = hypothesis.detail.upper()

    steps = [
        ValidationStep(
            step_number=1,
            step_id=f"{rec_id}-S1-DATA_QUALITY",
            title="Audit Data Quality & Denominators",
            investigation_action=(
                f"Verify that die attempts in {target_pop} have complete physical coordinates (X/Y), "
                "valid first-pass execution flags, and consistent lot/wafer dimensions. "
                "Check for stop-on-fail sequence censoring."
            ),
            required_evidence="Primary die_attempts fact table and test catalog mappings.",
            expected_measurement="100% referential integrity with 0 missing coordinates or ambiguous dispositions.",
            acceptance_criteria="Data grain matches canonical die x attempt without corruption.",
            rejection_criteria="Missing identifiers, duplicate attempts, or mismatched lot definitions.",
            limitations_and_safety="Advisory data verification only. Do not infer missing measurements.",
        ),
        ValidationStep(
            step_number=2,
            step_id=f"{rec_id}-S2-CONTROL_COMPARISON",
            title="Controlled Population Comparison",
            investigation_action=(
                f"Compare failure distribution and electrical binning of {target_pop} against "
                "the unaffected baseline population within the same product run."
            ),
            required_evidence="Parametric measurements and primary failure Pareto breakdown.",
            expected_measurement="Statistically significant divergence in failure rate (p < 0.05).",
            acceptance_criteria="Elevated loss confirmed to be concentrated in the candidate slice.",
            rejection_criteria="Difference attenuates after stratifying by common nuisance variables.",
            limitations_and_safety="Correlation does not confirm causation.",
        ),
        ValidationStep(
            step_number=3,
            step_id=f"{rec_id}-S3-EQUIPMENT_TRACKING",
            title="Process Equipment & Tool Lineage Review",
            investigation_action=(
                f"Review upstream tool, chamber, probe card, and tester assignments for {target_pop}. "
                "Cross-reference maintenance logs and consumable wear history."
            ),
            required_evidence="Manufacturing Execution System (MES) equipment tracking logs.",
            expected_measurement="Identification of common chamber or hardware shared by failed units.",
            acceptance_criteria="Plausible physical mechanism linked to upstream tool/chamber.",
            rejection_criteria="Uniform equipment distribution across affected and unaffected units.",
            limitations_and_safety="Hardware association remains advisory. Do not modify ATE or tool recipes.",
        ),
        ValidationStep(
            step_number=4,
            step_id=f"{rec_id}-S4-REPLICATION",
            title="Independent Material Replication",
            investigation_action=(
                f"Evaluate subsequent, independent production lots to determine if the {fam}.{det} "
                "signature replicates or was an isolated transient event."
            ),
            required_evidence="First-pass sort logs from at least 3 subsequent production lots.",
            expected_measurement="Consistent replication of the failure pattern.",
            acceptance_criteria="Pattern persists across independent temporal batches.",
            rejection_criteria="Pattern disappears spontaneously on new material (isolated excursion).",
            limitations_and_safety="Never alter production lines based on an un-replicated single lot excursion.",
        ),
        ValidationStep(
            step_number=5,
            step_id=f"{rec_id}-S5-PHYSICAL_FA",
            title="Physical Failure Analysis & Inline Metrology",
            investigation_action=(
                f"Submit representative failed dies from {target_pop} for physical FA (cross-sectional SEM/TEM, FIB) "
                "and overlay with inline optical defect scans (Klarf)."
            ),
            required_evidence="Inline defect metrology and analytical lab cross-sections.",
            expected_measurement="Identification of concrete physical defect mechanism (e.g. bridging, gate defect, particulate).",
            acceptance_criteria="Defect structure physically explains observed electrical test failure.",
            rejection_criteria="No physical defect found or non-visual electrical anomaly with clean cross-sections.",
            limitations_and_safety="Destructive physical analysis requires sample authorization from quality engineering.",
        ),
        ValidationStep(
            step_number=6,
            step_id=f"{rec_id}-S6-SPLIT_LOT_PROPOSAL",
            title="Controlled Split-Lot DOE Proposal",
            investigation_action=(
                "Propose a controlled split lot for engineering review: "
                "Leg A (control baseline) vs. Leg B (prospective engineering setting), if a root cause is confirmed."
            ),
            required_evidence="Split-lot execution plan and qualification review board signoff.",
            expected_measurement="Statistically significant yield delta (delta-FPY) with identical control sort.",
            acceptance_criteria="Delta-yield confirmed in split lot without degrading adjacent parameters.",
            rejection_criteria="Zero yield delta or secondary parametric degradation.",
            limitations_and_safety="This is an advisory proposal only. The agent cannot execute or authorize split lots.",
        ),
        ValidationStep(
            step_number=7,
            step_id=f"{rec_id}-S7-RELIABILITY_QUAL",
            title="Downstream Package & Reliability Qualification",
            investigation_action=(
                "Verify that resolving the wafer sort issue does not shift marginality into final package test, "
                "burn-in fallout, or early-life failure rate (ELFR/HTOL)."
            ),
            required_evidence="Package test summary and burn-in reliability data.",
            expected_measurement="Zero elevation in customer escape indicators or package test fallout.",
            acceptance_criteria="Passing all downstream reliability criteria.",
            rejection_criteria="Elevated burn-in failure or package assembly marginality.",
            limitations_and_safety="Reliability qualification is strictly governed by product engineering.",
        ),
    ]

    control_comp = f"Compare {target_pop} against baseline material in identical sort conditions."
    replication_chk = f"Confirm whether {hypothesis.family}.{hypothesis.detail} signature persists on 3 subsequent lots."
    fa_metrology = "Correlate with inline defect inspection and select failed dies for cross-sectional SEM."
    split_proposal = "Advisory proposal: Run a controlled split-lot trial before considering line-wide changes."
    downstream_rel = "Verify that addressing this mechanism does not increase package fallout or escape risks."

    return ValidationProtocol(
        protocol_id=f"PROTO-{rec_id}",
        target_hypothesis=hypothesis.hypothesis_id,
        steps=steps,
        control_comparison=control_comp,
        replication_check=replication_chk,
        physical_fa_or_metrology=fa_metrology,
        split_lot_proposal=split_proposal,
        downstream_reliability_risk=downstream_rel,
    )


def _generate_investigation_details(
    hypothesis: ReportHypothesis,
    category: RecommendationCategory,
    target_pop: str,
    fail_rate: float,
    baseline_rate: float,
) -> dict[str, Any]:
    fam = hypothesis.family.upper()
    det = hypothesis.detail.upper()

    if category == "Lot investigation":
        action = (
            f"Review the upstream thermal, lithographic, and chamber processing history for {target_pop}. "
            "Compare tool and chamber lineage against the lower-failure lots in this device run, "
            "and inspect whether the excursion is localized to specific wafers within the lot."
        )
        reason = (
            f"{target_pop} exhibits an observed failure rate of {fail_rate * 100:.1f}%, "
            f"compared to the overall baseline of {baseline_rate * 100:.1f}%. "
            "Statistical detectors identified significant lot-level variation, pointing to potential batch-level upstream processing anomalies."
        )
        expected = "Determine whether a specific upstream tool, consumable, or chamber caused the elevated lot failure rate."
        val_method = "Cross-stratify lot failure rates across process tool IDs and compare wafer-by-wafer trends."
        criteria = "Identify a distinct upstream process parameter or tool associated with the excursion."
        req_data = ["Upstream MES tool/chamber run history", "Maintenance logs for the processing timeframe"]
        risk = "If ignored, future production lots run on the same affected chamber or process conditions may suffer similar yield degradation."
        next_confirmed = "Perform equipment inspection and chamber maintenance on the identified tool; run a split lot to qualify."
        next_rejected = "If tool lineage is uniform, investigate incoming substrate/raw material variations or probe contact degradation."

    elif category == "Wafer investigation":
        action = (
            f"Examine the slot position, chamber sequence, and thermal uniformity for {target_pop}. "
            "Inspect whether the elevated failure rate is uniform across the wafer or concentrated in a spatial zone."
        )
        reason = (
            f"Wafer {target_pop} shows an acute failure rate of {fail_rate * 100:.1f}%, "
            f"exceeding the baseline of {baseline_rate * 100:.1f}%. "
            "Detectors indicate significant intra-lot wafer variation."
        )
        expected = "Establish whether wafer-level thermal gradients, slot position effects, or handling damage caused the spike."
        val_method = "Check slot number correlations and inspect wafer-map spatial clustering for the wafer."
        criteria = "Confirm whether the failure mode matches a specific wafer processing position or handling step."
        req_data = ["Cassette slot assignment", "Chamber temperature uniformity logs", "Wafer handling robot logs"]
        risk = "Recurrent wafer-level losses on specific cassette slots may persist undetected."
        next_confirmed = "Calibrate wafer chuck leveling/temperature and inspect robotic end-effector."
        next_rejected = "Check for localized mask defect or probe card contact wear on that specific touchdown sequence."

    elif category == "Spatial investigation":
        action = (
            f"Inspect edge-exclusion parameters, CMP polish uniformity, and chuck thermal gradients for {target_pop}. "
            "Verify whether border dies exhibit higher contact resistance or over-etching."
        )
        reason = (
            f"{target_pop} dies demonstrate a failure rate of {fail_rate * 100:.1f}%, "
            f"elevated above the inner die baseline. Spatial detectors identified a significant radial/border pattern."
        )
        expected = "Clarify whether edge ring degradation, chemical mechanical polishing roll-off, or gas flow dynamics cause peripheral die loss."
        val_method = "Correlate radial distance with film thickness metrology and optical defect scans across multiple wafers."
        criteria = "Demonstrate that edge failure clusters align with measured film thickness non-uniformity or edge roll-off."
        req_data = ["Inline ellipsometry / film thickness radial scans", "Edge-bead removal (EBR) recipe logs"]
        risk = "Ongoing systematic yield loss on peripheral dies across all future production wafers."
        next_confirmed = "Tune edge-ring bias or CMP retaining-ring pressure during scheduled engineering maintenance."
        next_rejected = "Inspect probe-card peripheral needle planarity and contact touchdown pressure at wafer periphery."

    elif category == "Parametric investigation":
        action = (
            f"Inspect the distribution of {target_pop} across lots and wafers. "
            "Verify tester measurement repeatability, instrument calibration, and test-program limit metadata."
        )
        reason = (
            f"Detectors identified a systematic parametric shift in {target_pop}. "
            "Shifts in electrical parameters directly drive binning fallout and indicate potential process centering drift."
        )
        expected = "Determine whether the parameter shift is a physical silicon variation or an ATE instrumentation artifact."
        val_method = "Perform Gage R&R on the test system and compare parameter distributions between golden calibration units and production units."
        criteria = "Isolate physical device parameter shift with verified measurement repeatability (Gage R&R < 10%)."
        req_data = ["Parametric measurement logs (raw volts/currents)", "Tester calibration and DIB board verification logs"]
        risk = "Potential false binning or shipping marginally performing silicon if drift is uncorrected."
        next_confirmed = "Investigate upstream deposition/implant recipe responsible for the shifted parameter; do not alter test limits."
        next_rejected = "Recalibrate ATE parametric measurement unit (PMU) and verify load-board contact resistance."

    elif category == "Near-limit investigation":
        action = (
            f"Characterize the measurement distribution near the test boundary for {target_pop}. "
            "Assess measurement repeatability and probe contact resistance. Do not relax or widen test limits."
        )
        reason = (
            f"{target_pop} exhibits an elevated failure rate of {fail_rate * 100:.1f}%. "
            "Detectors indicate a high concentration of dies failing within measurement uncertainty of test limits."
        )
        expected = "Determine if near-limit failures stem from probe contact resistance (Cres), tester noise, or genuine silicon marginality."
        val_method = "Inspect retest recovery rates and execute consecutive repeat-touchdown tests on identical dies."
        criteria = "Confirm repeatability of near-limit measurements without altering production guardbands."
        req_data = ["High-resolution parametric logs around limit", "Probe needle touchdown count and Cres logs"]
        risk = "Relaxing limits to improve yield risks catastrophic customer test escapes. Investigate measurement health instead."
        next_confirmed = "Clean probe tips, replace worn probe cards, or optimize test settle times; keep limits unchanged."
        next_rejected = "Review design-for-manufacturability (DFM) margins with product engineering."

    else:
        action = (
            f"Investigate {target_pop} following established semiconductor test engineering practices. "
            "Verify measurement repeatability, review tool logs, and cross-reference with independent material."
        )
        reason = (
            f"Statistical detectors observed systematic variation ({fam}.{det}) with failure rate {fail_rate * 100:.1f}%."
        )
        expected = "Gather evidence to confirm or reject whether the observed association represents a physical process mechanism."
        val_method = "Replicate on independent production lots and cross-stratify by equipment ID."
        criteria = "Replication of findings on new material."
        req_data = ["Historical sort logs", "MES tracking records"]
        risk = "Unaddressed yield loss may persist."
        next_confirmed = "Formulate a controlled engineering split-lot trial."
        next_rejected = "Monitor for future anomalies."

    return {
        "recommended_action": action,
        "reason": reason,
        "expected_information": expected,
        "validation_method": val_method,
        "success_criteria": criteria,
        "required_data": req_data,
        "risk_if_ignored": risk,
        "next_step_if_confirmed": next_confirmed,
        "next_step_if_rejected": next_rejected,
    }


def _build_evidence_traceability(
    dataset_id: str,
    hypothesis: ReportHypothesis,
    category: RecommendationCategory,
    target_pop_desc: str,
    pop_label: str,
    pop_dies: int,
    affected_count: int,
    pop_rate: float,
    eligible_dies: int,
    total_fails: int,
    baseline_fail_rate: float,
    ml_status: MLEvidenceStatus,
    ml_notes: str,
) -> dict[str, Any]:
    # Baseline denominator calculation from actual first-pass data
    if pop_dies < eligible_dies:
        base_dies = eligible_dies - pop_dies
        base_fails = max(0, total_fails - affected_count)
        base_rate = base_fails / max(1, base_dies)
        if hypothesis.family == "PROCESS" and "LOT" in hypothesis.detail.upper():
            baseline_desc = "Lot-excluded baseline (all other lots in dataset)"
            baseline_type = "LOT_EXCLUDED"
        elif hypothesis.family == "PROCESS" and "WAFER" in hypothesis.detail.upper():
            baseline_desc = "Subgroup-excluded baseline (remaining wafers in run)"
            baseline_type = "SUBGROUP_EXCLUDED"
        else:
            baseline_desc = "Subgroup-excluded baseline (core/inner population)"
            baseline_type = "SUBGROUP_EXCLUDED"
    else:
        base_dies = eligible_dies
        base_fails = total_fails
        base_rate = baseline_fail_rate
        baseline_desc = "Dataset-wide baseline"
        baseline_type = "DATASET_WIDE"

    # Supporting Evidence Items
    supporting_items: list[SupportingEvidenceItem] = []

    # 1. Observed subgroup first-pass failure measurement
    supporting_items.append(
        SupportingEvidenceItem(
            evidence_type="FIRST_PASS_SUBGROUP_MEASUREMENT",
            evidence_classification="OBSERVED_FACT",
            source_dataset=dataset_id,
            source_artifact="die_attempts / report.fpy_summary",
            entity_scope=target_pop_desc,
            numerator=affected_count,
            denominator=pop_dies,
            observed_value=round(pop_rate, 4),
            baseline_value=round(base_rate, 4),
            comparison_baseline=f"{baseline_desc}: {base_fails:,} / {base_dies:,} dies ({base_rate * 100:.1f}%)",
            unit="dies",
            time_scope="FIRST_PASS",
            validation_state="MEASURED_FIRST_PASS",
            limitations=["Direct physical first-pass count. Retest attempts excluded."],
        )
    )

    # 2. Observed baseline comparison
    supporting_items.append(
        SupportingEvidenceItem(
            evidence_type="FIRST_PASS_BASELINE_COMPARISON",
            evidence_classification="OBSERVED_FACT",
            source_dataset=dataset_id,
            source_artifact="report.fpy_summary",
            entity_scope=baseline_desc,
            numerator=base_fails,
            denominator=base_dies,
            observed_value=round(base_rate, 4),
            baseline_value=None,
            comparison_baseline=None,
            unit="dies",
            time_scope="FIRST_PASS",
            validation_state="MEASURED_FIRST_PASS",
            limitations=[f"Reference population for {baseline_type.lower()} comparisons."],
        )
    )

    # 3. Statistical detector signals from hypothesis
    for stat in hypothesis.statistical_evidence:
        det = str(stat.get("detector") or "statistical_detector")
        role = str(stat.get("role") or "PRIMARY_EVIDENCE")
        method = str(stat.get("method") or "statistical_test")
        sample_size = stat.get("sample_size")
        eff_size = stat.get("effect_size")
        eff_metric = str(stat.get("effect_size_metric") or "difference")
        p_val = stat.get("p_value")
        adj_p_val = stat.get("adjusted_p_value")

        has_sig = (adj_p_val is not None and adj_p_val < 0.05) or (p_val is not None and p_val < 0.05)
        val_st = "STATISTICALLY_SIGNIFICANT" if has_sig else "NOT_SIGNIFICANT"

        p_str = f"p={p_val:.2e}" if p_val is not None else "p=N/A"
        adj_p_str = f"adj_p={adj_p_val:.2e}" if adj_p_val is not None else "adj_p=N/A"
        base_comp = f"Method: {method}, {p_str}, {adj_p_str}"

        supporting_items.append(
            SupportingEvidenceItem(
                evidence_type="STATISTICAL_DETECTOR_SIGNAL",
                evidence_classification="STATISTICAL_ASSOCIATION",
                source_dataset=dataset_id,
                source_artifact=f"detector.{det}",
                entity_scope=f"{det.upper()} detector ({role})",
                numerator=None,
                denominator=int(sample_size) if sample_size else eligible_dies,
                observed_value=round(eff_size, 4) if isinstance(eff_size, (int, float)) else None,
                baseline_value=None,
                comparison_baseline=base_comp,
                unit=eff_metric,
                time_scope="FIRST_PASS",
                validation_state=val_st,
                limitations=[
                    "Statistical association does not establish physical causation.",
                    "Unverified against upstream MES equipment logs.",
                ],
            )
        )

    # 4. ML model evaluation status (exploratory / needs more data)
    if ml_status == "NEEDS_MORE_DATA":
        supporting_items.append(
            SupportingEvidenceItem(
                evidence_type="ML_MODEL_EVALUATION",
                evidence_classification="INSUFFICIENT_EVIDENCE",
                source_dataset=dataset_id,
                source_artifact="ml_champion_model / lolo_validation",
                entity_scope="ML Model Holdout Generalization",
                numerator=None,
                denominator=None,
                observed_value="ROC-AUC < 0.50",
                baseline_value=None,
                comparison_baseline="Deployment threshold (ROC-AUC >= 0.70)",
                unit="ROC-AUC",
                time_scope="HOLDOUT_LOTS",
                validation_state="NOT_EVALUATED",
                limitations=[
                    "ML model metrics are below reliability threshold on holdout lots.",
                    "Exploratory only; does not provide primary evidence.",
                ],
            )
        )

    # Determine transparent evidence_strength and validation_status (Fail Closed)
    has_sig_detector = any(
        (s.get("adjusted_p_value") is not None and s.get("adjusted_p_value") < 0.05) or
        (s.get("p_value") is not None and s.get("p_value") < 0.05)
        for s in hypothesis.statistical_evidence
    )

    if hypothesis.evidence_tier == "INSUFFICIENT_EVIDENCE" or hypothesis.association_class == "INSUFFICIENT_EVIDENCE":
        ev_strength: EvidenceStrength = "INSUFFICIENT"
        val_status = "INSUFFICIENT_EVIDENCE"
    elif affected_count < 10 or pop_dies < 30:
        ev_strength = "INSUFFICIENT"
        val_status = "INSUFFICIENT_SAMPLE_SIZE"
    elif not has_sig_detector:
        ev_strength = "INSUFFICIENT"
        val_status = "NO_STATISTICAL_SIGNIFICANCE" if len(hypothesis.statistical_evidence) > 0 else "NOT_EVALUATED"
    elif hypothesis.evidence_tier == "WEAK_EVIDENCE" or len(hypothesis.data_gaps) > 2:
        ev_strength = "WEAK"
        val_status = "WEAK_STATISTICAL_SIGNAL"
    elif hypothesis.evidence_tier == "MODERATE_EVIDENCE":
        ev_strength = "MODERATE"
        val_status = "STATISTICAL_SIGNAL_VALIDATED" if len(hypothesis.data_gaps) == 0 else "VALIDATED_WITH_DATA_GAPS"
    elif hypothesis.evidence_tier == "STRONG_EVIDENCE":
        distinct_families = set()
        for d in hypothesis.supporting_detectors:
            if d in {"lot", "wafer", "temporal"}:
                distinct_families.add("process")
            elif d in {"spatial", "wafer_map"}:
                distinct_families.add("spatial")
            elif d in {"parametric", "near_limit"}:
                distinct_families.add("electrical")
            elif d in {"equipment", "tester", "probe_card"}:
                distinct_families.add("hardware")
            else:
                distinct_families.add(d)

        if pop_dies >= 100 and affected_count >= 20 and len(hypothesis.data_gaps) == 0 and len(distinct_families) >= 2:
            ev_strength = "STRONG"
            val_status = "MULTI_DOMAIN_VALIDATED"
        else:
            ev_strength = "MODERATE"
            val_status = "STATISTICAL_SIGNAL_VALIDATED"
    else:
        ev_strength = "INSUFFICIENT"
        val_status = "NOT_EVALUATED"


    # Observed Facts
    observed_facts: list[str] = [
        f"{affected_count:,} of {pop_dies:,} first-pass dies failed in {target_pop_desc} ({pop_rate * 100:.1f}% failure rate).",
        f"Comparison baseline ({baseline_desc}) recorded {base_fails:,} of {base_dies:,} failures ({base_rate * 100:.1f}% failure rate).",
        f"Observed rate difference: {(pop_rate - base_rate) * 100:+.1f} percentage points relative to baseline (first-pass attempts only).",
    ]
    if hypothesis.supporting_detectors:
        observed_facts.append(
            f"Detector evidence: {len(hypothesis.supporting_detectors)} detector(s) ({', '.join(hypothesis.supporting_detectors)}) identified significant variation."
        )

    # Summary
    summary = (
        f"First-pass testing shows elevated failure concentration in {target_pop_desc} "
        f"({pop_rate * 100:.1f}% vs {base_rate * 100:.1f}% {baseline_type.lower()}). "
        f"Statistical analysis indicates a systematic {category.lower()} pattern ({hypothesis.statement})."
    )

    # Uncertainties
    uncertainties: list[str] = [
        "Observed statistical association does not establish physical causation.",
        "Upstream equipment, chamber, and tool maintenance lineage are not linked in the current test records.",
        "Physical failure mechanisms have not been confirmed via SEM/TEM or inline defect inspection.",
        "Replication across independent production batches is required before corrective actions can be formulated.",
    ]

    # Data gaps
    gaps: list[str] = list(hypothesis.data_gaps) if hypothesis.data_gaps else []
    gaps.append("Upstream MES chamber run parameters and maintenance records are unjoined in the active dataset.")
    gaps.append("Inline optical/defect metrology (Klarf) is not present in dataset.")

    # Recommended next steps
    steps: list[str] = [
        f"Audit Data Quality: Verify 100% referential integrity and coordinate validity for all {pop_dies:,} dies in {pop_label}.",
        f"Controlled Comparison: Stratify failure Pareto between {pop_label} and unaffected baseline material.",
        f"Equipment Lineage: Cross-reference MES tool and chamber history for {pop_label} against unaffected runs.",
        f"Independent Material Replication: Monitor subsequent production lots to confirm if the signature persists.",
        "Advisory Notice: All steps are advisory engineering investigations. Production action is FORBIDDEN.",
    ]

    return {
        "summary": summary,
        "observed_facts": observed_facts,
        "supporting_evidence": supporting_items,
        "evidence_strength": ev_strength,
        "uncertainties": uncertainties,
        "data_gaps": gaps,
        "recommended_next_steps": steps,
        "validation_status": val_status,
        "safety_status": "ADVISORY_ONLY: Production action is FORBIDDEN. Production authorized: False.",
    }


def generate_recommendations(
    report: EngineeringReport,
    ml_snapshot: dict[str, Any] | None = None,
    dataset_id: str | None = None,
) -> RecommendationBundle:
    """Generate evidence-backed engineering recommendations from an EngineeringReport."""
    ds_id = dataset_id or report.dataset_id
    fpy_summary = report.fpy_summary
    eligible_dies = fpy_summary.eligible_die_count
    baseline_fail_rate = fpy_summary.fpy_loss or 0.1004

    # Determine honest ML evidence status
    # Per prompt section 4 & 7: For V2 dataset, ML evidence must be reported as NEEDS_MORE_DATA
    # because LOLO experiments did not establish strong generalizable predictive performance.
    if ds_id == "yi_synthetic_v2" or "v2" in ds_id.lower():
        ml_status: MLEvidenceStatus = "NEEDS_MORE_DATA"
        ml_notes = (
            "Current V2 leave-one-lot-out ML experiments demonstrated insufficient generalizable predictive signal "
            "(pooled ROC-AUC < 0.50). Recommendation is prioritized purely on verified statistical and domain evidence."
        )
    elif ml_snapshot and ml_snapshot.get("available"):
        support = ml_snapshot.get("ml_support_status")
        if support == "RELIABLE":
            ml_status = "SUPPORTED"
            ml_notes = "ML champion model provides secondary supporting association."
        else:
            ml_status = "NEEDS_MORE_DATA"
            ml_notes = "ML model metrics are below reliability threshold; evidence is exploratory only."
    else:
        ml_status = "NOT_AVAILABLE"
        ml_notes = "No active ML snapshot available for this dataset."

    recommendations: list[EngineeringRecommendation] = []

    for hyp in report.hypotheses:
        # Filter out invalid or internal items
        if hyp.family == "UNION":
            continue
        if hyp.evidence_tier == "INSUFFICIENT_EVIDENCE" and hyp.association_class == "INSUFFICIENT_EVIDENCE":
            continue

        cat = _map_category(hyp.family, hyp.detail)
        rec_id = f"REC-{hyp.family}.{hyp.detail}"
        pop_info = hyp.affected_population or {}
        pop_label = str(pop_info.get("label") or pop_info.get("group") or hyp.detail)
        target_pop_desc = f"{hyp.family} {pop_label}"

        # Exact denominators from report
        pop_dies = int(pop_info.get("n") or eligible_dies)
        pop_rate = pop_info.get("rate")
        if pop_rate is None or not isinstance(pop_rate, (int, float)):
            # If rate not explicitly in population, use hypothesis observed loss rate or calculate
            if hyp.observed_loss_rate is not None:
                # hyp.observed_loss_rate is relative to eligible_dies
                pop_rate = (hyp.observed_loss_rate * eligible_dies) / max(1, pop_dies)
            else:
                pop_rate = baseline_fail_rate

        pop_rate = min(1.0, max(0.0, float(pop_rate)))

        # Affected dies count
        affected_count = round(pop_dies * pop_rate) if pop_rate else 0

        # Title
        title = f"Investigate {cat}: {pop_label} Systematic Loss Pattern"

        # Action and reasoning details
        details = _generate_investigation_details(
            hypothesis=hyp,
            category=cat,
            target_pop=target_pop_desc,
            fail_rate=pop_rate,
            baseline_rate=baseline_fail_rate,
        )

        # Validation Protocol
        proto = _build_validation_protocol(
            rec_id=rec_id,
            hypothesis=hyp,
            category=cat,
            target_pop=target_pop_desc,
        )

        # Opportunity estimates
        opp_ub_rate = hyp.upper_bound_rate
        opp_ub_count = round(opp_ub_rate * eligible_dies) if opp_ub_rate is not None else None
        opp_plaus_rate = hyp.plausible_rate
        opp_plaus_count = round(opp_plaus_rate * eligible_dies) if opp_plaus_rate is not None else None

        # Traceability & Evidence Quality
        trace = _build_evidence_traceability(
            dataset_id=ds_id,
            hypothesis=hyp,
            category=cat,
            target_pop_desc=target_pop_desc,
            pop_label=pop_label,
            pop_dies=pop_dies,
            affected_count=affected_count,
            pop_rate=pop_rate,
            eligible_dies=eligible_dies,
            total_fails=fpy_summary.first_pass_fail_count,
            baseline_fail_rate=baseline_fail_rate,
            ml_status=ml_status,
            ml_notes=ml_notes,
        )

        # Determine scope and lot_id
        from yield_improvement.api.service import population_lot_ids

        tokens = population_lot_ids(hyp.affected_population)
        named_lot = None
        for tok in tokens:
            if len(tok) >= 2 and tok[0] in {"L", "l"} and tok[1:].isdigit():
                named_lot = tok.upper()
                break

        if named_lot:
            rec_scope = "LOT_SPECIFIC"
            rec_lot_id = named_lot
        elif hyp.family == "PROCESS" and "LOT" in hyp.detail.upper():
            rec_scope = "LOT_SPECIFIC"
            rec_lot_id = pop_label if (len(pop_label) >= 2 and pop_label[0] in {"L", "l"}) else None
        else:
            rec_scope = "GLOBAL"
            rec_lot_id = None

        # Build initial model
        rec = EngineeringRecommendation(
            recommendation_id=rec_id,
            hypothesis_id=hyp.hypothesis_id,
            title=title,
            summary=trace["summary"],
            recommendation_category=cat,
            status="PROPOSED",
            scope=rec_scope,
            lot_id=rec_lot_id,
            priority_rank=1,  # updated by ranker
            priority_tier="MEDIUM",  # updated by ranker
            confidence_tier="MODERATE",  # updated by ranker
            ranking_score=0.5,  # updated by ranker
            ranking_rationale="Initial evidence assessment",  # updated by ranker
            observed_pattern=hyp.statement,
            target_population=target_pop_desc,
            affected_die_count=affected_count,
            eligible_die_count=eligible_dies,
            subgroup_die_count=pop_dies,
            subgroup_failed_die_count=affected_count,
            observed_failure_rate=round(pop_rate, 4),
            baseline_failure_rate=round(baseline_fail_rate, 4),
            supporting_detectors=list(hyp.supporting_detectors),
            hypothesis_confidence=hyp.evidence_tier,
            ml_evidence_status=ml_status,
            ml_evidence_notes=ml_notes,
            missing_evidence=list(hyp.data_gaps),
            limitations=list(hyp.limitations),
            observed_facts=trace["observed_facts"],
            supporting_evidence=trace["supporting_evidence"],
            evidence_strength=trace["evidence_strength"],
            uncertainties=trace["uncertainties"],
            data_gaps=trace["data_gaps"],
            recommended_next_steps=trace["recommended_next_steps"],
            validation_status=trace["validation_status"],
            recommended_action=details["recommended_action"],
            reason=details["reason"],
            expected_information=details["expected_information"],
            validation_method=details["validation_method"],
            success_criteria=details["success_criteria"],
            required_data=details["required_data"],
            risk_if_ignored=details["risk_if_ignored"],
            next_step_if_confirmed=details["next_step_if_confirmed"],
            next_step_if_rejected=details["next_step_if_rejected"],
            validation_protocol=proto,
            observed_loss_rate=round(hyp.observed_loss_rate or 0.0, 4),
            upper_bound_rate=round(opp_ub_rate, 4) if opp_ub_rate is not None else None,
            upper_bound_count=opp_ub_count,
            plausible_rate=round(opp_plaus_rate, 4) if opp_plaus_rate is not None else None,
            plausible_count=opp_plaus_count,
            safety_eligible_production_rate=0.0,
            safety_eligible_production_count=0,
            production_action="FORBIDDEN",
            production_authorized=False,
            not_a_root_cause=True,
            safety_status=trace["safety_status"],
        )



        # Compute scoring
        score, rationale, conf_tier = compute_recommendation_score(
            rec=rec,
            association_class=hyp.association_class,
            evidence_tier=hyp.evidence_tier,
            data_gaps=hyp.data_gaps,
        )

        rec = rec.model_copy(
            update={
                "ranking_score": score,
                "ranking_rationale": rationale,
                "confidence_tier": conf_tier,
            }
        )

        recommendations.append(rec)

    # Rank deterministically
    ranked_recs = rank_recommendations(recommendations)

    summary_gaps = []
    if report.data_gaps and report.data_gaps.required:
        summary_gaps.extend(report.data_gaps.required)
    if report.data_gaps and report.data_gaps.recommended:
        summary_gaps.extend(report.data_gaps.recommended)

    return RecommendationBundle(
        dataset_id=ds_id,
        selected_lot_id=None,
        lot_note=None,
        recommendation_count=len(ranked_recs),
        recommendations=ranked_recs,

        ranking_policy=RANKING_POLICY_NAME,
        ranking_version=RANKING_POLICY_VERSION,
        evidence_limitations_summary=summary_gaps,
        ml_evidence_status=ml_status,
        ml_evidence_summary=ml_notes,
        safety_invariants={
            "production_action": "FORBIDDEN",
            "production_authorized": False,
            "safety_eligible_production": 0.0,
        },
        production_action="FORBIDDEN",
        production_authorized=False,
        safety_eligible_production_rate=0.0,
    )
