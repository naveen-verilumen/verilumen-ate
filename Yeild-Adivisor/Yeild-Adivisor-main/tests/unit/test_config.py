from __future__ import annotations

import pytest

from yield_improvement.config import load_config


def test_all_yaml_configs_load(config):
    assert config.fpy.fpy_policy_version == "yi_fpy_v1"
    assert config.taxonomy.taxonomy_version == "yi_taxonomy_v1"
    assert config.bin_map.bin_map_version == "yi_bin_map_v1"
    assert config.safety.policy_version == "yi_safety_v1"
    assert config.calibration.calibration_version == "yi_calibration_v1"
    assert config.allowlist.allowlist_version == "yi_allowlist_v1"


def test_fpy_policy_matches_frozen_yaml(config):
    policy = config.fpy
    assert policy.abort_is_first_pass_fail is True
    assert policy.abort_policy == "FIRST_PASS_ABORT_IS_FAIL"
    assert policy.part_class_missing.treat_as == "PRODUCTION"
    assert policy.part_class_missing.flag == "part_class_assumed_production"
    assert "ENGINEERING" in policy.excluded_part_classes
    assert "CALIBRATION" in policy.excluded_part_classes
    assert "REWORK" in policy.excluded_part_classes
    assert policy.escape_rate == "unavailable"
    assert policy.insertion == "WAFER_SORT"


def test_safety_production_opportunity_is_zero(config):
    assert config.safety.safety_eligible_production.value == 0.0
    assert config.safety.safety_eligible_production.immutable is True
    assert config.safety.potential_specialist_investigation.invoked is False


def test_malformed_yaml_rejected(tmp_path):
    from yield_improvement.config.loader import load_yaml_model
    from yield_improvement.config.schemas import FpyPolicy
    from yield_improvement.utils.errors import ConfigError

    bad = tmp_path / "fpy_policy.yaml"
    bad.write_text("fpy_policy_version: only_this\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_yaml_model(bad, FpyPolicy)


def test_reload_is_deterministic():
    a = load_config()
    b = load_config()
    assert a.fpy.model_dump() == b.fpy.model_dump()


def test_safety_default_when_is_quoted_always(config):
    last = config.safety.decision_table[-1]
    assert last.id == "S12"
    assert last.when == "ALWAYS"
    assert isinstance(last.when, str)
    assert last.then == "NEEDS_MORE_DATA"


def test_part_class_missing_policy_unchanged(config):
    """Prompt 5: keep missing part_class → PRODUCTION + assumption flag."""
    missing = config.fpy.part_class_missing
    assert missing.treat_as == "PRODUCTION"
    assert missing.flag == "part_class_assumed_production"
    assert missing.status == "FROZEN_OPEN_TO_REVERSE"


def test_yaml_boolean_when_is_rejected():
    from pydantic import ValidationError

    from yield_improvement.config.schemas import DecisionRule

    with pytest.raises(ValidationError, match="quoted string"):
        DecisionRule.model_validate({"id": "Sx", "when": True, "then": "NEEDS_MORE_DATA"})
