"""Read-only checks for the V2 feature audit. Does not train."""

from __future__ import annotations

import pandas as pd

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.benchmark_v1 import SEQUENCE_SLOTS, audit_gru_sequence
from yield_improvement.ml.dataset import PARAM_NAMES, load_ml_dataset
from yield_improvement.ml.v2_build import DATASET_ID
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.utils.paths import repo_root

PARAMS = (
    "VMIN",
    "VMAX",
    "IDDQ",
    "SUPPLY_CURRENT",
    "CONTACT_RESISTANCE",
    "INTERCONNECT_RESISTANCE",
    "ON_RESISTANCE",
    "VDD",
)
DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / DATASET_ID


def test_v2_params_join_without_retest_or_die_id_collapse():
    attempts = pd.read_csv(DATASET / "die_attempts.csv")
    params = pd.read_csv(DATASET / "parametric_measurements.csv")
    first = attempts.loc[attempts["attempt_number"].astype(int) == 1]
    assert len(first) == 2500
    assert int(first["pass_fail"].astype(str).eq("FAIL").sum()) == 251
    ids = set(first["attempt_id"].astype(str))
    fp = params.loc[params["attempt_id"].astype(str).isin(ids)]
    assert int((~params["attempt_id"].astype(str).isin(ids)).sum()) == 480
    key = ["lot_id", "wafer_id", "die_id", "attempt_id"]
    assert int(first.groupby(["lot_id", "wafer_id", "die_id"]).size().max()) == 1
    assert int(first.groupby("die_id").size().max()) == 25
    any_limit = pd.Series(False, index=first["attempt_id"].astype(str).unique())
    for name in PARAMS:
        sub = fp.loc[fp["parameter_name"].astype(str) == name]
        counts = sub.groupby(key).size()
        assert len(sub) == 2500
        assert int((counts > 1).sum()) == 0
        assert int(sub.groupby("die_id").size().max()) == 25
        joined = first.merge(sub[key + ["pass_fail"]], on=key, how="left", indicator=True)
        assert int(joined["_merge"].eq("both").sum()) == 2500
        limit_fail = joined["pass_fail_y"].astype(str).eq("FAIL")
        attempt_fail = joined["pass_fail_x"].astype(str).eq("FAIL")
        assert int((limit_fail & ~attempt_fail).sum()) == 0
        any_limit = any_limit | limit_fail.set_axis(joined["attempt_id"].astype(str))
    assert int(any_limit.sum()) == 56


def test_default_matrix_excludes_v2_params_and_test_outcomes():
    data = load_ml_dataset(DATASET)
    assert len(data.frame) == 2500
    assert int(data.y.sum()) == 251
    assert not set(PARAMS) & set(data.frame.columns)
    assert not set(PARAM_NAMES) & set(data.frame.columns)
    denied = {"pass_fail", "failure_code", "first_pass_fail", "scenario_id", "true_cause", "ground_truth"}
    assert not denied & set(data.frame.columns)
    audit = audit_gru_sequence(DATASET)
    assert audit["status"] == "BLOCKED_LEAKAGE_RISK"
    assert audit["measurement_columns"] == []
    assert audit["order_matches_defined_slots"] is True
    assert [row["test_id"] for row in audit["sequence_slots"]] == [slot[0] for slot in SEQUENCE_SLOTS]
    assert audit["dies_where_any_test_fail_equals_attempt_fail"] == 2500


def test_active_model_unchanged_after_audit():
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["production_authorized"] is False
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    folder = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
    assert hash_files(folder, CHAMPION_FILES) == registry["models"]["yi_ml_v1"]["artifact_hashes"]
    assert "yi_ml_v5" not in registry["models"]
    from yield_improvement.ml.features import fit_feature_builder

    data = load_ml_dataset(DATASET)
    assert list(fit_feature_builder(data.frame, data.y).feature_names_) == list(ACTIVE_FEATURE_CONTRACT)
