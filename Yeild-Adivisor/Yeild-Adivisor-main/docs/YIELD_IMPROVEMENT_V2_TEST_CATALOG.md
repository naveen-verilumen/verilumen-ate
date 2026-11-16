# Yield Improvement V2 Test Catalog

These are **V2 synthetic test catalog definitions**. They are a **display overlay** only.

The generator source of truth is `configs/synthetic_v2.yaml`. That file defines `test_id`, `sequence_index`, `failure_code`, and `sbin`. It does **not** define a separate `test_name`. Generated CSVs also have no test-name column.

Dashboard labels therefore copy the generator **program-slot identifier** (`tests[].failure_code`) so every `T001`–`T010` has an explicit display name. That token is not a newly invented physical ATE type. Stored FAIL `failure_code` values are unchanged.

They do **not** represent a specific real semiconductor company's ATE test program.

| ID | Exact display name (generator program slot) | Failure code on FAIL |
|----|---------------------------------------------|----------------------|
| T001 | CONTINUITY | CONTINUITY |
| T002 | OPENS | OPENS |
| T003 | SHORTS | SHORTS |
| T004 | CONTACT | CONTACT |
| T005 | IDDQ | IDDQ |
| T006 | VMIN | VMIN |
| T007 | VMAX | VMAX |
| T008 | LEAKAGE | LEAKAGE |
| T009 | FUNCTIONAL | FUNCTIONAL |
| T010 | SCAN | SCAN |

Preferred display format:

`T004 — CONTACT`

Do not use `Unclassified V2 Test`. That label hid which test ID was being discussed and is not a generator-defined name.

If a `Txxx` ID is missing from the overlay, the fallback is:

`T00X — No semantic test name defined in V2 source`

## Prior overlay disagreement (corrected)

An earlier overlay invented semiconductor types for T001–T006 that **conflicted** with the generator:

| ID | Invented overlay name (withdrawn) | Generator program slot |
|----|-----------------------------------|------------------------|
| T001 | Continuity / Open-Short Test | CONTINUITY |
| T002 | DC Parametric Test | OPENS |
| T003 | Leakage Test | SHORTS |
| T004 | Functional Test | CONTACT |
| T005 | Timing / AC Test | IDDQ |
| T006 | Power / Thermal Test | VMIN |
| T007–T010 | Unclassified V2 Test | VMAX / LEAKAGE / FUNCTIONAL / SCAN |

The generator/data definition is the source of truth. The catalog is a display layer. The invented names were withdrawn.

## Stable IDs

- Machine-readable IDs stay `T001`–`T010`.
- Do not rename IDs to `TEST_1` or similar.
- Failure codes in `test_results.csv` are unchanged. For example, a T004 FAIL row still carries generator `failure_code=CONTACT`.
- Display names repeat that program-slot token; they are not a rewrite of the stored failure taxonomy.

## Sequence, stop-on-fail, primary failure

Unchanged:

- `sequence_index` 1–10 for T001–T010
- stop-on-fail / `NOT_EXECUTED` behavior
- retest behavior
- PRIMARY_FAILURE selection (`is_first_fail` / sequence)
- Pareto still counts unique dies by primary `test_id`

This overlay does not change FPY, FPY loss, or Pareto counts.

## Hierarchy

LOT → WAFER → DIE → ATTEMPT → TEST → MEASUREMENTS / RESULTS

A die can still have multiple tests (T001–T010).

## ML safety

Test IDs are not ML targets. Do not add `test_id`, `test_name`, `test_type`, `failure_code`, `pass_fail`, `disposition`, or `sequence_index` as ML features because names were added. Champion `yi_ml_v1` is not retrained by this catalog.

Test outcomes and failure codes must not leak into ML features. That deny list is unchanged.

## API

`GET /api/test-catalog` and dashboard field `test_catalog` return:

```json
{
  "test_id": "T004",
  "test_name": "CONTACT",
  "test_type": "CONTACT",
  "display_label": "T004 — CONTACT"
}
```

`test_id` is never removed. Engineering-report Pareto rows still use `failure_key` = `T004`.

See also [YIELD_IMPROVEMENT_V2_DATASET_DOCUMENTATION.md](YIELD_IMPROVEMENT_V2_DATASET_DOCUMENTATION.md) section 11.
