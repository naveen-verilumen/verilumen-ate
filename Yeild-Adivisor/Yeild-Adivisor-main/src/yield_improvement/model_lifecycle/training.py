"""Manual candidate training. Never writes artifacts/ml/yi_ml_v1."""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT, FORBIDDEN_FEATURES, run_lolo_models
from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.models import make_model
from yield_improvement.model_lifecycle.audit import append_event, utc_now
from yield_improvement.model_lifecycle.hashes import dumps, hash_files, hash_text
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    LifecyclePaths,
    assert_champion_unchanged,
    bootstrap_champion,
    champion_hashes,
    default_paths,
    get_record,
    load_registry,
    new_record,
    put_record,
    save_registry,
)
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import LifecycleError, assert_transition
from yield_improvement.model_lifecycle.versioning import (
    APPROVED_ARCHITECTURE,
    CHAMPION_ARCHITECTURE,
    assert_unused,
    next_candidate_version,
)

CANDIDATE_FILES = ("model.pkl", "metadata.json", "feature_list.json", "metrics.json")


def _config_hash() -> str:
    from yield_improvement.utils.paths import configs_dir

    ml = (configs_dir() / "ml.yaml").read_text(encoding="utf-8")
    allow = (configs_dir() / "ml_feature_allowlist.yaml").read_text(encoding="utf-8")
    return hash_text(ml + "\n" + allow + "\narchitecture=logistic\n")


def prepare_candidate(
    dataset_dir: str | Path,
    *,
    paths: LifecyclePaths | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Create a CANDIDATE version slot. Does not train, approve, or activate."""
    assert_production_invariants()
    paths = paths or default_paths()
    before = champion_hashes(paths)
    bootstrap_champion(paths)
    registry = load_registry(paths)
    dataset_path = Path(dataset_dir).resolve()
    if not (dataset_path / "die_attempts.csv").is_file():
        raise LifecycleError(f"dataset_dir missing die_attempts.csv: {dataset_path}")
    app = config or load_config()
    data = load_ml_dataset(dataset_path, config=app)
    forbidden = set(c.lower() for c in data.frame.columns) & (FORBIDDEN_FEATURES - {"lot_id", "wafer_id", "die_id"})
    # identity keys may exist on the source table; hidden labels must not.
    hidden = set(c.lower() for c in data.frame.columns) & {
        "scenario_id",
        "true_cause",
        "injected_effect",
        "generator_seed",
        "ground_truth",
    }
    if hidden:
        raise LifecycleError(f"hidden labels on dataset: {sorted(hidden)}")
    if forbidden & {"scenario_id", "true_cause"}:
        raise LifecycleError(f"forbidden columns: {sorted(forbidden)}")
    champion = registry.get("active_version") or CHAMPION_VERSION
    version = next_candidate_version(list(registry.get("models", {})), champion_version=champion)
    assert_unused(version, list(registry.get("models", {})))
    assert_transition(None, "CANDIDATE", event="MODEL_CREATED")
    dest = paths.version_dir(version)
    dest.mkdir(parents=True, exist_ok=False)
    prepare = {
        "model_version": version,
        "dataset_id": data.analysis_id,
        "dataset_dir": str(dataset_path),
        "dataset_sha256": hash_text((dataset_path / "die_attempts.csv").read_text(encoding="utf-8")),
        "parent_model_version": champion,
        "architecture": APPROVED_ARCHITECTURE,
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "feature_contract_version": load_ml_config().feature_set_version,
        "seed": load_ml_config().seed,
        "training_config_hash": _config_hash(),
        "created_at": utc_now(),
        "trained": False,
        **safety_payload(),
    }
    (dest / "prepare.json").write_text(dumps(prepare), encoding="utf-8")
    record = new_record(
        version=version,
        architecture=CHAMPION_ARCHITECTURE,
        state="CANDIDATE",
        dataset_id=data.analysis_id,
        dataset_dir=str(dataset_path),
        parent=champion,
        training_config_hash=prepare["training_config_hash"],
        notes="Prepared candidate. Not trained. Not approved. Not active.",
        seed=prepare["seed"],
        feature_contract=list(ACTIVE_FEATURE_CONTRACT),
        feature_contract_version=prepare["feature_contract_version"],
    )
    put_record(registry, record)
    save_registry(paths, registry)
    append_event(
        paths.audit_path,
        {
            "event_type": "MODEL_CREATED",
            "model_version": version,
            "previous_state": None,
            "new_state": "CANDIDATE",
            "actor": "unavailable",
            "reason": "retrain_prepare",
            "artifact_hashes": {},
            "parent_version": champion,
        },
    )
    assert_champion_unchanged(paths, before)
    return {**prepare, "state": "CANDIDATE", "active_version": registry.get("active_version"), **safety_payload()}


def train_candidate(version: str, *, paths: LifecyclePaths | None = None, config: AppConfig | None = None) -> dict[str, Any]:
    """Fit logistic on the prepared dataset. Never overwrites the champion. Never activates."""
    assert_production_invariants()
    paths = paths or default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    record = get_record(registry, version)
    if record["state"] != "CANDIDATE":
        raise LifecycleError(f"train requires CANDIDATE, found {record['state']}")
    dest = paths.version_dir(version)
    prepare_path = dest / "prepare.json"
    if not prepare_path.is_file():
        raise LifecycleError(f"missing prepare.json for {version}")
    if (dest / "model.pkl").is_file():
        raise LifecycleError(f"refusing to retrain existing candidate {version}")
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    app = config or load_config()
    cfg = load_ml_config()
    data = load_ml_dataset(prepare["dataset_dir"], config=app)
    # Nested LOLO for the deployed calibrator. Metrics are produced by evaluate, not here.
    bench = run_lolo_models(data, model_names=["logistic"], cfg=cfg, with_importance=False)
    y = data.y.to_numpy()
    builder = fit_feature_builder(data.frame, data.y)
    x_all = builder.transform(data.frame)
    if any(name.lower() in FORBIDDEN_FEATURES for name in x_all.columns):
        raise LifecycleError(f"forbidden features in training matrix: {list(x_all.columns)}")
    numeric = [c for c in builder.numeric_features_ if c in x_all.columns]
    categorical = [c for c in builder.categorical_features_ if c in x_all.columns]
    pipeline = make_model("logistic", cfg, cfg.seed, numeric, categorical)
    pipeline.fit(x_all, y)
    calibrator = ProbabilityCalibrator().fit(bench["_oof"]["logistic"]["raw"], y)
    blob = pickle.dumps(
        {
            "pipeline": pipeline,
            "builder": builder,
            "calibrator": calibrator,
            "model_name": "logistic",
            "feature_names": list(x_all.columns),
            "split_strategy": bench["split_strategy"],
        },
        protocol=4,
    )
    (dest / "model.pkl").write_bytes(blob)
    try:
        import sklearn
        sklearn_version = sklearn.__version__
    except Exception:  # noqa: BLE001
        sklearn_version = "unavailable"
    meta = {
        "model_version": version,
        "model_name": "logistic",
        "architecture": CHAMPION_ARCHITECTURE,
        "feature_set_version": cfg.feature_set_version,
        "calibration_version": cfg.calibration_version,
        "split_strategy": bench["split_strategy"],
        "seed": cfg.seed,
        "feature_names": list(x_all.columns),
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "n_features": int(len(x_all.columns)),
        "trained_at": utc_now(),
        "parent_model_version": record.get("parent_model_version"),
        "dataset_id": data.analysis_id,
        "training_config_hash": prepare["training_config_hash"],
        "python_version": sys.version.split()[0],
        "sklearn_version": sklearn_version,
        "disclaimer": "Predictive association only. Not a root cause. Not a production authorization.",
        **safety_payload(),
    }
    (dest / "metadata.json").write_text(dumps(meta), encoding="utf-8")
    (dest / "feature_list.json").write_text(json.dumps(list(x_all.columns), indent=2) + "\n", encoding="utf-8")
    (dest / "metrics.json").write_text(
        dumps(
            {
                "model_name": "logistic",
                "metrics": None,
                "note": "Metrics are written by retrain evaluate. Train does not approve or activate.",
                "disclaimer": meta["disclaimer"],
            }
        ),
        encoding="utf-8",
    )
    hashes = hash_files(dest, CANDIDATE_FILES)
    (dest / "hashes.json").write_text(dumps(hashes), encoding="utf-8")
    prepare["trained"] = True
    prepare_path.write_text(dumps(prepare), encoding="utf-8")
    record = dict(record)
    record["artifact_hashes"] = hashes
    record["python_version"] = meta["python_version"]
    record["sklearn_version"] = sklearn_version
    record["feature_contract"] = list(x_all.columns)
    record["notes"] = "Trained candidate. Not validated. Not approved. Not active."
    put_record(registry, record)
    save_registry(paths, registry)
    assert_champion_unchanged(paths, before)
    if registry.get("active_version") != CHAMPION_VERSION and paths.root == default_paths().root:
        raise LifecycleError("train mutated active pointer")
    return {
        "model_version": version,
        "state": "CANDIDATE",
        "architecture": "logistic",
        "n_samples": bench["n_samples"],
        "n_lots": bench["n_lots"],
        "artifact_hashes": hashes,
        "activated": False,
        "approved": False,
        **safety_payload(),
    }
