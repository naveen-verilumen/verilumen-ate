from __future__ import annotations

from pathlib import Path

from yield_improvement.ingestion.loader import load_csv
from yield_improvement.pipeline import run_pipeline
from yield_improvement.utils.paths import repo_root


def test_forbidden_column_rejected(tmp_path, config):
    path = tmp_path / "die_attempts.csv"
    path.write_text(
        "lot_id,wafer_id,die_id,product_id,step_id,attempt_id,true_root_cause\n"
        "L,W,D,DEV_A,WS_SORT,E1,PLANTED\n",
        encoding="utf-8",
    )
    result = run_pipeline(path, config=config)
    assert result.status == "INVALID"
    assert any(e.code == "FORBIDDEN_COLUMN" for e in result.errors)


def test_population_mix_invalid(tmp_path, config):
    src = repo_root() / "tests" / "fixtures" / "fpy" / "case_01" / "die_attempts.csv"
    text = src.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    lines[1] = lines[1].replace("DEV_A", "DEV_B", 1)
    mixed = tmp_path / "die_attempts.csv"
    mixed.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = run_pipeline(mixed, config=config)
    assert result.status == "INVALID"
    assert any(e.code == "POPULATION_MIX" for e in result.errors)


def test_parquet_roundtrip(tmp_path, config):
    csv_path = repo_root() / "tests" / "fixtures" / "fpy" / "case_01" / "die_attempts.csv"
    frame = load_csv(csv_path)
    parquet_path = tmp_path / "die_attempts.parquet"
    frame.to_parquet(parquet_path, index=False)
    result = run_pipeline(parquet_path, config=config)
    assert result.status == "OK"
    assert result.fpy == 0.9


def test_required_columns_error(tmp_path, config):
    path = tmp_path / "die_attempts.csv"
    path.write_text("lot_id\nL001\n", encoding="utf-8")
    result = run_pipeline(path, config=config)
    assert result.status == "INVALID"
    assert any(e.code == "MISSING_REQUIRED_COLUMNS" for e in result.errors)
