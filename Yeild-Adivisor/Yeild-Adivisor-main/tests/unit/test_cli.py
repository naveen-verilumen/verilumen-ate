from __future__ import annotations

import pytest

from yield_improvement.__main__ import main
from yield_improvement.utils.paths import fixtures_fpy_dir


def test_cli_case_01(capsys):
    path = str(fixtures_fpy_dir() / "case_01")
    code = main([path])
    captured = capsys.readouterr()
    assert code == 0
    assert '"fpy": 0.9' in captured.out
    assert '"eligible_die_count": 10' in captured.out
    assert '"first_pass_pass_count": 9' in captured.out


def test_cli_hypothesize_requires_dataset(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["hypothesize"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "dataset_dir" in captured.err or "dataset" in captured.err.lower()


def test_cli_opportunity_requires_dataset(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["opportunity"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "dataset_dir" in captured.err or "dataset" in captured.err.lower()


def test_cli_validate_requires_dataset(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["validate"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "dataset_dir" in captured.err or "dataset" in captured.err.lower()


def test_cli_ml_requires_action(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["ml"])
    assert exc.value.code == 2


def test_cli_ml_explain_data_requires_dataset(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["ml", "explain-data"])
    assert exc.value.code == 2


def test_cli_ml_train_requires_dataset(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["ml", "train"])
    assert exc.value.code == 2


def test_cli_monitor_requires_reference(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["monitor", "some_dir"])
    assert exc.value.code == 2


def test_cli_retrain_requires_action(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["retrain"])
    assert exc.value.code == 2


def test_cli_model_requires_action(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["model"])
    assert exc.value.code == 2


def test_cli_model_approve_requires_human(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["model", "approve", "--candidate", "yi_ml_v2_candidate_001"])
    assert exc.value.code == 2


def test_cli_serve_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["serve", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Read-only FastAPI" in captured.out
