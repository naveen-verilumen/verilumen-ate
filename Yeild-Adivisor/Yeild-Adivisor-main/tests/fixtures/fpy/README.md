# FPY golden fixtures (tiny, deterministic)

Observable inputs only. No ground-truth root-cause columns.

Each `case_XX/` contains:

- `die_attempts.csv` — grain: unique die × attempt
- `test_results.csv` — optional; grain: attempt × test
- `expected.json` — FPY, exclusions, primary/any-fail attribution

Policy: `configs/fpy_policy.yaml` (`yi_fpy_v1`).
Bin/taxonomy: `configs/bin_map.yaml`, `configs/taxonomy.yaml`.

`analyze()` of the future agent must consume CSVs only, never `expected.json`.
Pytest reads `expected.json` after computing FPY.

See `manifest.json` for the case list.
