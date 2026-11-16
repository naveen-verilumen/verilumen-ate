"""Canonical first-pass failing dies drill-down for engineering recommendations.

Strictly diagnostic. Production action is FORBIDDEN.
Never keys dies by die_id alone or (wafer_id, die_id) alone.
Uses canonical physical identity (lot_id, wafer_id, die_id).
Excludes retest-only failures.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from yield_improvement.api.service import display_lot_name, find_dataset_dir, get_recommendations_bundle
from yield_improvement.config.loader import load_config
from yield_improvement.detectors.common import cal
from yield_improvement.detectors.near_limit import _nearest_limit
from yield_improvement.reporting.adapter import load_canonical_data
from yield_improvement.reporting.contract import DISCLAIMER, SAFETY_STATEMENT
from yield_improvement.yield_analysis.grid_region import is_grid_border, is_positive_filled_grid

logger = logging.getLogger(__name__)


def extract_recommendation_failing_dies(
    dataset_id: str,
    recommendation_id: str,
    lot_id: str | None = None,
) -> dict[str, Any]:
    """Extract first-pass failing dies and explicit denominators for a recommendation."""
    folder = find_dataset_dir(dataset_id)
    if folder is None:
        raise FileNotFoundError(f"Dataset '{dataset_id}' not found.")

    selected_lot = lot_id.strip() if isinstance(lot_id, str) and lot_id.strip() else None

    # 1. Fetch recommendation metadata from the bundle
    bundle = get_recommendations_bundle(dataset_id, lot_id=selected_lot)
    recs = bundle.get("recommendations", [])
    matched_rec = next((r for r in recs if r.get("recommendation_id") == recommendation_id), None)
    if matched_rec is None:
        # Check global bundle if not in lot-scoped bundle
        global_bundle = get_recommendations_bundle(dataset_id, lot_id=None)
        matched_rec = next((r for r in global_bundle.get("recommendations", []) if r.get("recommendation_id") == recommendation_id), None)
        if matched_rec is None:
            raise FileNotFoundError(f"Recommendation '{recommendation_id}' not found in dataset '{dataset_id}'.")

    category = matched_rec.get("recommendation_category", "")
    target_pop = matched_rec.get("target_population", "")
    title = matched_rec.get("title", "")
    rec_scope = matched_rec.get("scope", "GLOBAL")
    rec_lot_id = matched_rec.get("lot_id") or selected_lot

    # 2. Load canonical data
    cfg = load_config()
    attempts, test_results, parametric, cfg = load_canonical_data(folder, cfg)
    near_limit_delta = float(cal(cfg, "near_limit_delta"))

    # 3. Index attempts by physical die key: (lot_id, wafer_id, die_id)
    attempts_by_die: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for att in attempts:
        key = (att.lot_id, att.wafer_id, att.die_id)
        attempts_by_die[key].append(att)

    # 4. Resolve exact first-pass attempt for each physical die
    first_pass_dies: dict[tuple[str, str, str], Any] = {}
    for key, die_attempts in attempts_by_die.items():
        # First attempt flag or attempt_number == 1
        first_candidates = [a for a in die_attempts if a.is_first_attempt or (a.attempt_number == 1)]
        if not first_candidates:
            # Fallback: attempt with minimum attempt_number or minimum timestamp
            first_candidates = sorted(
                die_attempts,
                key=lambda a: (a.attempt_number if a.attempt_number is not None else 10**9, a.timestamp or ""),
            )
        else:
            first_candidates.sort(
                key=lambda a: (a.attempt_number if a.attempt_number is not None else 1, a.timestamp or ""),
            )
        first_pass_dies[key] = first_candidates[0]

    # Index tests by attempt_id
    tests_by_attempt: dict[str, list[Any]] = defaultdict(list)
    for t in test_results:
        tests_by_attempt[t.attempt_id].append(t)

    # Index parametric measurements by attempt_id
    params_by_attempt: dict[str, list[Any]] = defaultdict(list)
    for p in parametric:
        params_by_attempt[p.attempt_id].append(p)

    # 5. Dataset-level and lot-level counts (first-pass only)
    dataset_eligible_dies = len(first_pass_dies)
    dataset_failing_dies = sum(1 for a in first_pass_dies.values() if (a.pass_fail or "").strip().upper() == "FAIL")

    lot_eligible_dies: int | None = None
    lot_failing_dies: int | None = None
    if rec_lot_id:
        lot_dies = [a for a in first_pass_dies.values() if a.lot_id == rec_lot_id]
        lot_eligible_dies = len(lot_dies)
        lot_failing_dies = sum(1 for a in lot_dies if (a.pass_fail or "").strip().upper() == "FAIL")

    # 6. Recommendation-specific Subgroup Predicate
    # Parse target population tokens
    subgroup_keys: set[tuple[str, str, str]] = set()
    near_limit_meas_subgroup_count: int | None = None
    near_limit_meas_failing_count: int | None = None
    subgroup_desc = ""

    # Scope restriction for lot-level recommendations
    lot_filter = rec_lot_id if rec_scope == "LOT_SPECIFIC" else None

    # Case A: Wafer Investigation (e.g. "PROCESS L004/W05")
    wafer_match = re.search(r"([A-Z0-9_-]+)/([A-Z0-9_-]+)", target_pop)
    if category == "Wafer investigation" and wafer_match:
        t_lot = wafer_match.group(1).upper()
        t_wafer = wafer_match.group(2).upper()
        subgroup_desc = f"Physical dies tested on wafer {t_wafer} in lot {t_lot}"
        for key, att in first_pass_dies.items():
            if att.lot_id.upper() == t_lot and att.wafer_id.upper() == t_wafer:
                subgroup_keys.add(key)

    # Case B: Lot Investigation (e.g. "PROCESS L004" or category == "Lot investigation")
    elif category == "Lot investigation" or (category == "Process variation" and "LOT" in target_pop.upper()):
        lot_match = re.search(r"\b(L\d{3,4}|LOT[-_ ]?[A-Z0-9]+)\b", target_pop, re.IGNORECASE)
        t_lot = (lot_match.group(1).upper() if lot_match else (rec_lot_id or "")).upper()
        subgroup_desc = f"Physical dies belonging to lot {t_lot}"
        for key, att in first_pass_dies.items():
            if att.lot_id.upper() == t_lot:
                subgroup_keys.add(key)

    # Case C: Spatial Investigation (e.g. "SPATIAL BORDER", "SPATIAL EDGE", "SPATIAL RING")
    elif category == "Spatial investigation" or "SPATIAL" in target_pop.upper():
        xs = [float(a.x) for a in first_pass_dies.values() if a.x is not None]
        ys = [float(a.y) for a in first_pass_dies.values() if a.y is not None]
        bounds = (min(xs), max(xs), min(ys), max(ys)) if xs and ys else (0.0, 0.0, 0.0, 0.0)

        region_token = "BORDER"
        for tok in ["BORDER", "INNER", "EDGE", "CENTER", "RING"]:
            if tok in target_pop.upper():
                region_token = tok
                break

        subgroup_desc = f"Physical dies situated in the {region_token} spatial region"
        if lot_filter:
            subgroup_desc += f" of lot {lot_filter}"

        for key, att in first_pass_dies.items():
            if lot_filter and att.lot_id != lot_filter:
                continue
            if att.x is None or att.y is None:
                continue

            if region_token == "BORDER":
                if is_grid_border(float(att.x), float(att.y), bounds):
                    subgroup_keys.add(key)
            elif region_token == "INNER":
                if not is_grid_border(float(att.x), float(att.y), bounds):
                    subgroup_keys.add(key)
            else:
                # Fallback for general spatial regions: border/outer
                if is_grid_border(float(att.x), float(att.y), bounds):
                    subgroup_keys.add(key)

    # Case D: Near-Limit Investigation (e.g. "TEST near_vs_far" or category == "Near-limit investigation")
    elif category == "Near-limit investigation" or "NEAR" in target_pop.upper():
        subgroup_desc = f"Physical dies with first-pass parametric measurements within {near_limit_delta * 100:.1f}% of test limits"
        if lot_filter:
            subgroup_desc += f" in lot {lot_filter}"

        near_meas_count = 0
        near_fail_meas_count = 0

        for key, att in first_pass_dies.items():
            if lot_filter and att.lot_id != lot_filter:
                continue

            att_params = params_by_attempt.get(att.attempt_id, [])
            has_near = False
            for p in att_params:
                lim = _nearest_limit(p.measurement, p.lower_limit, p.upper_limit)
                if lim is not None and abs(lim) > 0:
                    prox = abs(p.measurement - lim) / abs(lim)
                    if prox <= near_limit_delta:
                        near_meas_count += 1
                        if (att.pass_fail or "").strip().upper() == "FAIL":
                            near_fail_meas_count += 1
                        has_near = True

            if has_near:
                subgroup_keys.add(key)

        near_limit_meas_subgroup_count = near_meas_count
        near_limit_meas_failing_count = near_fail_meas_count

    # Case E: Parametric Investigation (e.g. "PARAMETRIC VMIN:L004")
    elif category == "Parametric investigation" or "PARAMETRIC" in target_pop.upper():
        param_token = "VMIN"
        for candidate_param in ["IDDQ", "VMIN", "VMAX", "VDD", "SUPPLY_CURRENT", "CONTACT_RESISTANCE"]:
            if candidate_param in target_pop.upper():
                param_token = candidate_param
                break

        lot_match = re.search(r":([A-Z0-9]+)", target_pop)
        p_lot = lot_match.group(1).upper() if lot_match else (lot_filter or None)

        subgroup_desc = f"Physical dies evaluated for parameter '{param_token}'"
        if p_lot:
            subgroup_desc += f" in lot {p_lot}"

        for key, att in first_pass_dies.items():
            if p_lot and att.lot_id.upper() != p_lot:
                continue

            # Check if die has a measurement for this parameter or failure code matches
            att_params = params_by_attempt.get(att.attempt_id, [])
            has_param = any(p.parameter_name.upper() == param_token for p in att_params)
            has_code = (att.failure_code or "").upper() == param_token
            if has_param or has_code:
                subgroup_keys.add(key)

    # Case F: Equipment Investigation (e.g. "EQUIPMENT T01")
    elif category == "Equipment investigation" or "EQUIPMENT" in target_pop.upper():
        tool_match = re.search(r"EQUIPMENT\s+([A-Z0-9_-]+)", target_pop, re.IGNORECASE)
        t_tool = tool_match.group(1).upper() if tool_match else "T01"
        subgroup_desc = f"Physical dies tested on tester tool '{t_tool}'"
        if lot_filter:
            subgroup_desc += f" in lot {lot_filter}"

        for key, att in first_pass_dies.items():
            if lot_filter and att.lot_id != lot_filter:
                continue
            if (att.tester_id or "").upper() == t_tool:
                subgroup_keys.add(key)

    # Case G: Contact / Probe Card Investigation (e.g. "CONTACT PC02")
    elif "CONTACT" in target_pop.upper() or category == "Test measurement/repeatability investigation":
        pc_match = re.search(r"CONTACT\s+([A-Z0-9_-]+)", target_pop, re.IGNORECASE)
        t_pc = pc_match.group(1).upper() if pc_match else "PC02"
        subgroup_desc = f"Physical dies tested using probe card '{t_pc}'"
        if lot_filter:
            subgroup_desc += f" in lot {lot_filter}"

        for key, att in first_pass_dies.items():
            if lot_filter and att.lot_id != lot_filter:
                continue
            if (att.probe_card_id or "").upper() == t_pc:
                subgroup_keys.add(key)

    # Fallback: if subgroup could not be determined, use recommendation's lot scope or all dies
    if not subgroup_keys:
        subgroup_desc = f"Physical dies in scope ({target_pop})"
        for key, att in first_pass_dies.items():
            if lot_filter and att.lot_id != lot_filter:
                continue
            subgroup_keys.add(key)

    # 7. Subgroup Counts
    subgroup_eligible_dies = len(subgroup_keys)
    subgroup_failing_dies = sum(
        1 for k in subgroup_keys if (first_pass_dies[k].pass_fail or "").strip().upper() == "FAIL"
    )

    # 8. Build List of First-Pass Failing Dies in Subgroup
    failing_records: list[dict[str, Any]] = []
    for key in sorted(subgroup_keys, key=lambda k: (k[0], k[1], k[2])):
        att = first_pass_dies[key]
        if (att.pass_fail or "").strip().upper() != "FAIL":
            continue

        # Extract failed test IDs
        die_tests = tests_by_attempt.get(att.attempt_id, [])
        failed_test_ids: list[str] = []
        for t in die_tests:
            if (t.test_pass_fail or "").strip().upper() == "FAIL":
                failed_test_ids.append(t.test_id)

        # Primary failure code
        first_fail_test = next((t for t in die_tests if t.is_first_fail), None)
        primary_code = (
            first_fail_test.failure_code
            if (first_fail_test and first_fail_test.failure_code)
            else (att.failure_code or "FAIL")
        )

        # Extract relevant parametric measurements
        die_params = params_by_attempt.get(att.attempt_id, [])
        measurements_list: list[dict[str, Any]] = []
        for p in die_params:
            lim = _nearest_limit(p.measurement, p.lower_limit, p.upper_limit)
            is_near = False
            prox_val = None
            if lim is not None and abs(lim) > 0:
                prox_val = abs(p.measurement - lim) / abs(lim)
                is_near = prox_val <= near_limit_delta

            measurements_list.append(
                {
                    "parameter_name": p.parameter_name,
                    "value": round(p.measurement, 4),
                    "unit": p.unit or "",
                    "lower_limit": p.lower_limit,
                    "upper_limit": p.upper_limit,
                    "near_limit": is_near,
                    "proximity_ratio": round(prox_val, 4) if prox_val is not None else None,
                }
            )

        failing_records.append(
            {
                "lot_id": att.lot_id,
                "wafer_id": att.wafer_id,
                "die_id": att.die_id,
                "x": att.x,
                "y": att.y,
                "first_pass_result": "FAIL",
                "primary_failure_code": primary_code,
                "failed_test_ids": failed_test_ids,
                "relevant_measurements": measurements_list,
            }
        )

    # Calculate explicit failure rates
    subgroup_fail_rate = (
        round(subgroup_failing_dies / subgroup_eligible_dies, 4) if subgroup_eligible_dies > 0 else 0.0
    )
    lot_fail_rate = (
        round(lot_failing_dies / lot_eligible_dies, 4)
        if (lot_eligible_dies is not None and lot_eligible_dies > 0 and lot_failing_dies is not None)
        else None
    )
    dataset_fail_rate = (
        round(dataset_failing_dies / dataset_eligible_dies, 4) if dataset_eligible_dies > 0 else 0.0
    )

    counts = {
        "subgroup_failing_dies": subgroup_failing_dies,
        "subgroup_eligible_dies": subgroup_eligible_dies,
        "subgroup_failure_rate": subgroup_fail_rate,
        "lot_id": rec_lot_id,
        "lot_display": display_lot_name(rec_lot_id) if rec_lot_id else None,
        "lot_failing_dies": lot_failing_dies,
        "lot_eligible_dies": lot_eligible_dies,
        "lot_failure_rate": lot_fail_rate,
        "dataset_failing_dies": dataset_failing_dies,
        "dataset_eligible_dies": dataset_eligible_dies,
        "dataset_failure_rate": dataset_fail_rate,
        "subgroup_failing_measurements": near_limit_meas_failing_count,
        "subgroup_eligible_measurements": near_limit_meas_subgroup_count,
    }

    return {
        "dataset_id": dataset_id,
        "recommendation_id": recommendation_id,
        "lot_id": rec_lot_id,
        "title": title,
        "target_population": target_pop,
        "recommendation_category": category,
        "subgroup_definition": subgroup_desc,
        "counts": counts,
        "failing_dies_count": len(failing_records),
        "failing_dies": failing_records,
        "production_action": "FORBIDDEN",
        "production_authorized": False,
        "safety_statement": SAFETY_STATEMENT,
        "disclaimer": DISCLAIMER,
    }
