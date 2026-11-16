"""Controlled V2 oxide-thickness measurement. Does not train or activate a model."""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

from yield_improvement.api.service import list_datasets
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.synthetic.v2_generator import (
    OXIDE_BASELINE_NM,
    OXIDE_COLUMN,
    OXIDE_EFFECT_SCALE_NM,
    OXIDE_NOISE_SD_NM,
    OXIDE_SIDE_STREAM_SEED,
    build_population,
    load_v2_config,
    oxide_thickness_nm,
    realize,
)
from yield_improvement.synthetic.v2_oxide_enhancement import (
    UNCHANGED_FILES,
    enhanced_dataset_dir,
    file_sha256,
    generate_enhanced_population,
    leakage_report,
    outcome_counts,
    preservation_mismatches,
    source_dataset_dir,
)
from yield_improvement.utils.paths import repo_root

SOURCE_HASHES = {
    "die_attempts.csv": "3aebf4b320ea086d8b4a86fd38a55cc7b362651fbb760dc8b83aff243f5fad4e",
    "parametric_measurements.csv": "ae99fe60313374b94a86fd5b1116f5ba9dead3cc1afa0b58d45a769035edb678",
    "test_results.csv": "843f6c38c20aa5744bd9380c2f341706a124aa33552a3b1020d62341e6ed0e9b",
}


class _FixedNoise:
    def gauss(self, mu: float, sigma: float) -> float:
        assert mu == 0.0
        assert sigma == OXIDE_NOISE_SD_NM
        return 0.01


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_formula_is_baseline_plus_process_offsets_plus_side_noise():
    value = oxide_thickness_nm(0.1, -0.05, _FixedNoise())
    assert value == OXIDE_BASELINE_NM + OXIDE_EFFECT_SCALE_NM * 0.1 + OXIDE_EFFECT_SCALE_NM * -0.05 + 0.01


def test_generation_is_deterministic_and_uses_an_independent_stream():
    cfg = load_v2_config()
    first = build_population(cfg, random.Random(int(cfg["seed"])))
    second = build_population(cfg, random.Random(int(cfg["seed"])))
    assert [die.pre_sort_oxide_thickness_nm for die in first] == [die.pre_sort_oxide_thickness_nm for die in second]

    rng_a = random.Random(int(cfg["seed"]))
    rng_b = random.Random(int(cfg["seed"]))
    dies_a = build_population(cfg, rng_a)
    dies_b = build_population(cfg, rng_b, oxide_stream_seed=OXIDE_SIDE_STREAM_SEED + 1)
    assert rng_a.getstate() == rng_b.getstate()
    assert [die.fail_p for die in dies_a] == [die.fail_p for die in dies_b]
    assert [die.pre_sort_oxide_thickness_nm for die in dies_a] != [die.pre_sort_oxide_thickness_nm for die in dies_b]
    realize(cfg, rng_a, dies_a)
    realize(cfg, rng_b, dies_b)
    assert [die.failed for die in dies_a] == [die.failed for die in dies_b]
    assert [die.measurements for die in dies_a] == [die.measurements for die in dies_b]
    assert [die.failure_code for die in dies_a] == [die.failure_code for die in dies_b]
    assert [die.fail_test_ids for die in dies_a] == [die.fail_test_ids for die in dies_b]


def test_thickness_does_not_depend_on_the_fail_bit_or_label():
    cfg = load_v2_config()
    dies = build_population(cfg, random.Random(int(cfg["seed"])))
    before = [die.pre_sort_oxide_thickness_nm for die in dies]
    realize(cfg, random.Random(int(cfg["seed"])), dies)
    assert [die.pre_sort_oxide_thickness_nm for die in dies] == before
    for die in dies:
        die.failed = not die.failed
        die.failure_code = "SHORTS" if die.failure_code is None else None
    assert [die.pre_sort_oxide_thickness_nm for die in dies] == before
    assert all(value > 2.0 for value in before)


def test_outcome_preservation_and_coverage():
    _cfg, dies, tables = generate_enhanced_population()
    assert preservation_mismatches(tables) == []
    counts = outcome_counts(tables["die_attempts"])
    assert counts["eligible_dies"] == 2500
    assert counts["first_pass_failures"] == 251
    assert counts["first_pass_passes"] == 2249
    assert counts["fpy"] == 0.8996
    assert counts["fpy_loss"] == 0.1004
    first = [row for row in tables["die_attempts"] if int(row["attempt_number"]) == 1]
    assert len(first) == 2500
    assert all(isinstance(row[OXIDE_COLUMN], float) for row in first)
    assert all(row[OXIDE_COLUMN] == row[OXIDE_COLUMN] for row in first)
    source_first = [row for row in _csv(source_dataset_dir() / "die_attempts.csv") if row["attempt_number"] == "1"]
    assert Counter(row["failure_code"] for row in source_first if row["pass_fail"] == "FAIL") == Counter(
        row["failure_code"] for row in first if row["pass_fail"] == "FAIL"
    )
    report = leakage_report(dies, tables, enhanced_dataset_dir())
    assert report
    assert all(report.values()), report


def test_enhanced_dataset_identity_retests_and_units():
    source = source_dataset_dir()
    enhanced = enhanced_dataset_dir()
    for name, digest in SOURCE_HASHES.items():
        assert file_sha256(source / name) == digest
    for name in UNCHANGED_FILES:
        assert (enhanced / name).read_bytes() == (source / name).read_bytes()
    original = _csv(source / "die_attempts.csv")
    rows = _csv(enhanced / "die_attempts.csv")
    assert list(rows[0].keys()) == list(original[0].keys()) + [OXIDE_COLUMN]
    assert len(rows) == len(original)
    identities = {(row["lot_id"], row["wafer_id"], row["die_id"]) for row in rows}
    assert len(identities) == 2500
    assert sum(1 for row in rows if row["die_id"] == "D001") > 1
    by_die: dict[tuple[str, str, str], set[str]] = {}
    first_pass = []
    for stored, row in zip(original, rows, strict=True):
        for key, value in stored.items():
            assert row[key] == value
        value = row[OXIDE_COLUMN]
        assert value != ""
        parsed = float(value)
        assert parsed == parsed
        by_die.setdefault((row["lot_id"], row["wafer_id"], row["die_id"]), set()).add(value)
        if row["attempt_number"] == "1":
            first_pass.append(row)
    assert len(first_pass) == 2500
    assert all(len(values) == 1 for values in by_die.values())
    retests = [row for row in rows if row["attempt_number"] != "1"]
    assert retests
    assert len(rows) == 2500 + len(retests)
    lineage = (enhanced / "enhancement.json").read_text(encoding="utf-8")
    assert '"unit": "nm"' in lineage
    assert "generator_seed" not in lineage
    assert "scenario_id" not in lineage
    assert "true_cause" not in lineage
    assert "ground_truth" not in lineage
    assert "injected_effect" not in lineage


def test_production_selector_and_active_model_stay_unchanged():
    assert [row["dataset_id"] for row in list_datasets()] == ["yi_synthetic_v2"]
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert "yi_ml_v5" not in registry["models"]
    assert not (repo_root() / "artifacts" / "ml" / "yi_ml_v5").exists()
