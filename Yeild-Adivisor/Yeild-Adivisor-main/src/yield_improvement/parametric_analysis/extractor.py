from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement

@dataclass(frozen=True)
class FirstPassDieParametricRecord:
    attempt_id: str
    lot_id: str
    wafer_id: str
    die_id: str
    parameter_name: str
    measurement: float
    unit: str
    first_pass_failed: bool
    failure_code: str | None
    condition_id: str
    temperature_c: float | None
    voltage_v: float | None

@dataclass(frozen=True)
class ExtractionResult:
    records_by_param: dict[str, list[FirstPassDieParametricRecord]]
    eligible_dies_count: int
    first_pass_pass_count: int
    first_pass_fail_count: int
    retests_excluded_count: int
    missing_measurements_count: int
    quarantined_attempts_count: int
    quarantined_dies_count: int
    lots_present: list[str]
    wafers_present: list[str]
    warnings: list[str]

def extract_first_pass_parametric_data(
    attempts: list[DieAttempt],
    parametric: list[ParametricMeasurement],
) -> ExtractionResult:
    warnings: list[str] = []
    quarantined_attempt_ids: set[str] = set()
    quarantined_die_keys: set[tuple[str, str, str]] = set()

    first_pass_candidates: dict[str, DieAttempt] = {}
    retest_attempt_ids: set[str] = set()

    for att in attempts:
        has_first_flag = att.is_first_attempt is True
        has_first_num = att.attempt_number == 1

        if has_first_flag and has_first_num:
            first_pass_candidates[att.attempt_id] = att
        elif (not has_first_flag) and (att.attempt_number is not None and att.attempt_number > 1):
            retest_attempt_ids.add(att.attempt_id)
        elif att.is_retest is True:
            retest_attempt_ids.add(att.attempt_id)
        else:
            quarantined_attempt_ids.add(att.attempt_id)
            quarantined_die_keys.add(att.die_key())
            warnings.append(
                f'Quarantined attempt {att.attempt_id} for die {att.die_key()}: '
                f'conflicting first-pass metadata (is_first_attempt={att.is_first_attempt}, attempt_number={att.attempt_number}, is_retest={att.is_retest})'
            )

    die_attempts_map: dict[tuple[str, str, str], list[DieAttempt]] = defaultdict(list)
    for att_id, att in first_pass_candidates.items():
        die_attempts_map[att.die_key()].append(att)

    valid_first_pass_attempts: dict[str, DieAttempt] = {}
    for die_key, att_list in die_attempts_map.items():
        if die_key in quarantined_die_keys:
            continue
        if len(att_list) > 1:
            quarantined_die_keys.add(die_key)
            for dup in att_list:
                quarantined_attempt_ids.add(dup.attempt_id)
            warnings.append(
                f'Quarantined physical die {die_key}: detected {len(att_list)} duplicate first-pass attempts ({[d.attempt_id for d in att_list]})'
            )
        else:
            valid_first_pass_attempts[att_list[0].attempt_id] = att_list[0]

    eligible_dies = len(valid_first_pass_attempts)
    fpy_fails = sum(1 for a in valid_first_pass_attempts.values() if a.pass_fail == 'FAIL' or a.disposition == 'FAIL')
    fpy_passes = sum(1 for a in valid_first_pass_attempts.values() if a.pass_fail == 'PASS' or a.disposition == 'PASS')

    retests_excluded = 0
    records_by_param: dict[str, list[FirstPassDieParametricRecord]] = defaultdict(list)
    seen_die_param: dict[tuple[tuple[str, str, str], str], str] = {}
    orphan_measurements = 0
    quarantined_measurements = 0

    for p in parametric:
        if p.attempt_id in retest_attempt_ids:
            retests_excluded += 1
            continue

        if p.attempt_id in quarantined_attempt_ids:
            quarantined_measurements += 1
            continue

        attempt = valid_first_pass_attempts.get(p.attempt_id)
        if attempt is None:
            orphan_measurements += 1
            continue

        die_key = attempt.die_key()
        param_key = (die_key, p.parameter_name)

        if param_key in seen_die_param:
            warnings.append(
                f'Duplicate measurement for physical die {die_key} on parameter {p.parameter_name}: '
                f'attempt {p.attempt_id} duplicates earlier observation'
            )
            continue
        seen_die_param[param_key] = p.attempt_id

        if p.measurement is None or (isinstance(p.measurement, float) and (p.measurement != p.measurement or abs(p.measurement) == float('inf'))):
            warnings.append(f'Invalid non-finite measurement on die {die_key} for {p.parameter_name}: {p.measurement}')
            continue

        rec = FirstPassDieParametricRecord(
            attempt_id=attempt.attempt_id,
            lot_id=attempt.lot_id,
            wafer_id=attempt.wafer_id,
            die_id=attempt.die_id,
            parameter_name=p.parameter_name,
            measurement=float(p.measurement),
            unit=p.unit or '',
            first_pass_failed=(attempt.pass_fail == 'FAIL' or attempt.disposition == 'FAIL'),
            failure_code=attempt.failure_code,
            condition_id=p.condition_id or 'NONE',
            temperature_c=p.temperature_c if p.temperature_c is not None else attempt.temperature_c,
            voltage_v=p.voltage_v if p.voltage_v is not None else attempt.voltage_v,
        )
        records_by_param[p.parameter_name].append(rec)

    if orphan_measurements > 0:
        warnings.append(f'Ignored {orphan_measurements} parametric rows with orphan attempt_id not matching any attempt')

    lots = sorted({a.lot_id for a in valid_first_pass_attempts.values()})
    wafers = sorted({f'{a.lot_id}:{a.wafer_id}' for a in valid_first_pass_attempts.values()})

    missing_measurements_total = 0
    all_param_names = set(records_by_param.keys())
    for pname in all_param_names:
        n_measured = len(records_by_param[pname])
        if n_measured < eligible_dies:
            missing_measurements_total += (eligible_dies - n_measured)

    return ExtractionResult(
        records_by_param=dict(records_by_param),
        eligible_dies_count=eligible_dies,
        first_pass_pass_count=fpy_passes,
        first_pass_fail_count=fpy_fails,
        retests_excluded_count=retests_excluded,
        missing_measurements_count=missing_measurements_total,
        quarantined_attempts_count=len(quarantined_attempt_ids),
        quarantined_dies_count=len(quarantined_die_keys),
        lots_present=lots,
        wafers_present=wafers,
        warnings=warnings,
    )
