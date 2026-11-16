# Pre-Disposition Measurement Design for V2

Design only. Nothing was implemented. V2 was not regenerated. No model was trained. `yi_ml_v1` stays ACTIVE. `yi_ml_v5` was not created. The dashboard was not changed. Production authorization stays false.

## 1. Executive summary

**APPROVED_FOR_IMPLEMENTATION** as a later change, not as work done here.

Add one numeric column, `pre_sort_oxide_thickness_nm`, on every first-pass die. It is an inline oxide-thickness reading taken before wafer sort. It is a noisy observation of the lot-level and wafer-level process offsets that `build_population` already adds into `fail_p`. Sort disposition does not read it. The existing fail bit, test outcomes, and the 251 / 2,249 split stay in place.

The column is not `fail_p`, not a scenario label, and not a rename of `VMIN`, `IDDQ`, or `VMAX`.

## 2. Current V2 data limitation

`docs/YIELD_IMPROVEMENT_ML_COLUMN_LINEAGE_CONTRACT.md` concluded **NO — source-data enhancement required.**

The 16-column contract is either not predictive enough across held-out lots or is a training-label mean (`tester_fail_rate`, `probe_fail_rate`). The eight parametric measurements are drawn before the fail bit, and a limit miss then forces FAIL. Renaming them does not remove that arrow. T001–T010 store outcomes written from the fail bit, so a GRU sequence stays `BLOCKED_LEAKAGE_RISK`.

Statistical diagnosis can still use the canonical tables. Those tables do not contain a qualifying ML measurement.

## 3. Existing generator dependency analysis

`build_population` in `src/yield_improvement/synthetic/v2_generator.py` runs before any fail bit exists. For every die it stores coordinates, equipment ids, temperature, voltage, timestamp, and `fail_p`.

`fail_p` is clipped baseline probability plus:

- `lot_eff`, one normal draw per lot
- `wafer_eff`, one normal draw per wafer
- `tester_effects[tester]`, one normal draw per tester
- `extra`, from the hidden lot block: a constant, an edge term, a tester term, and a per-wafer ramp
- `die_noise`, one normal draw per die

Temperature and voltage are drawn in that same loop. They do not enter `fail_p`. They are already on the attempt row.

`realize` then:

1. Applies hidden-role mean shifts to `CONTACT_RESISTANCE`, `IDDQ`, and `VMIN`.
2. Draws the eight parametric values.
3. Sets `die.failed` from `rng.random() < die.fail_p`.
4. If any parametric value is outside its limit, sets `die.failed = True`.

`build_tables` writes disposition, failure code, and T001–T010 from that bit. Retest rows copy the same measurements.

| Variable | Before disposition | Influences the fail bit | Written after the fail bit |
| --- | --- | --- | --- |
| `x`, `y`, equipment ids, timestamp | Yes | Only through `extra` when the hidden lot block says so | No |
| `temperature_c`, `voltage_v` | Yes | No | No |
| `lot_eff`, `wafer_eff`, `tester_effects` | Yes, internal only | Yes, added into `fail_p` | Not stored |
| `die_noise`, `fail_p`, `extra` | Yes, internal only | Yes | Not stored |
| Eight parametric values | Drawn before the bit is set | Yes, when outside the limit | Stored with a limit `pass_fail` |
| Test-slot status, failure code, disposition | No | They are the bit | Yes |

Hidden lot fields (`role`, `extra_p`, `extra_p_edge`, `extra_p_tester`, `extra_p_per_wafer`, `affected_tester`, `expected_signal`) are not agent-visible. They change `extra` and some parametric means. They are scenario controls, not measurements.

What can move a new observable without deciding PASS/FAIL: `lot_eff` and `wafer_eff`. They already exist for every lot and every wafer, they are computed before the coin flip, and they are not the fail bit. `die_noise` and `fail_p` are too close to the coin flip. `extra` is the injected scenario probability. Parametric values are already wired into the limit override.

## 4. Candidate measurement

| Property | Assessment |
| --- | --- |
| Measurement name | `pre_sort_oxide_thickness_nm` |
| Physical meaning | Inline ellipsometry of gate-oxide thickness before wafer sort |
| Unit | nm |
| Generated when | In `build_population`, after `fail_p` is computed for that die, from a side random stream |
| Input variables | Nominal 3.20 nm, that die’s existing `lot_eff`, that die’s existing `wafer_eff`, and independent metrology noise |
| Generated before disposition? | Yes |
| Does disposition read it? | No |
| Can it change PASS/FAIL? | No |
| Uses hidden truth? | No |
| Uses target? | No |
| Available for 2,500 dies? | Yes |
| Cross-lot signal | Yes. Every lot has its own `lot_eff`, and the thickness scale is the same function in every lot |
| Cross-wafer signal | Yes. Every wafer has its own `wafer_eff` |
| Expected ML usefulness | Modest. Lot and wafer offsets are small beside scenario `extra`, `die_noise`, and the coin flip. Usefulness is not a reason this candidate was chosen |
| Leakage risk | Low, if the side stream is used and `realize` never reads the column |
| Why it is legitimate | It is a thickness in nm. Sort limits do not compare it. It shares a process offset with `fail_p` and does not contain `fail_p` |

The value for a die is:

```text
pre_sort_oxide_thickness_nm
    = 3.20
    + (8.0 nm) * lot_eff
    + (8.0 nm) * wafer_eff
    + side_stream_normal(0, 0.05 nm)
```

`8.0` is a fixed physical scale, in nm per unit of the existing probability offset. It is not fit to ROC-AUC, PR-AUC, F1, or top-k capture. The metrology noise is large enough that the column is not a rescaled copy of `lot_eff`.

## 5. Physical interpretation

Gate oxide is measured in the fab, before sort, by ellipsometry. Lot-to-lot furnace offset and wafer-to-wafer position in the run move the thickness. A later sort fail rate can move with that same process offset because `lot_eff` and `wafer_eff` are already inside `fail_p`. The sort program does not have an oxide-thickness limit, so the reading does not accept or reject the die.

This is not a good/bad flag. It is a continuous nanometer value with die-level metrology noise.

## 6. Generation timing

```text
build_population
    compute lot_eff, wafer_eff, tester_effects, extra, die_noise
    compute fail_p
    draw temperature and voltage
    draw pre_sort_oxide_thickness_nm from the side stream
        using only lot_eff, wafer_eff, and side-stream noise
realize
    draw the eight existing parameters
    set die.failed from fail_p
    force die.failed if an existing parameter misses its limit
    do not read pre_sort_oxide_thickness_nm
build_tables
    write the existing disposition and tests from die.failed
    write the thickness beside the first-pass attempt
```

The side stream is a separate `random.Random` instance. It must not be the `rng` object that draws `fail_p`, the parametric values, or the fail coin flip.

## 7. Data lineage

```text
lot_eff, wafer_eff          side-stream noise
        │                          │
        └──────────┬───────────────┘
                   ▼
     pre_sort_oxide_thickness_nm
                   │
                   ▼
            stored on the first-pass die
                   │
                   ▼
            future ML column only

fail_p and existing parametric limits
                   │
                   ▼
              die.failed
                   │
                   ▼
        disposition, tests, first_pass_fail
```

There is no arrow from the stored thickness into `die.failed`.

## 8. Disposition independence proof

`die.failed` is assigned in exactly two places in `realize`:

- `die.failed = rng.random() < die.fail_p`
- `die.failed = True` when `_param_fail` is true for one of the eight existing parameters

`_param_fail` inspects `die.measurements` for those eight names and their limits. The new thickness is not one of those names, is not added to `params`, and is not passed to `_param_fail`. Test-slot status is copied from `die.failed` and `fail_test_ids` after that assignment. Neither list is built from the thickness.

So:

```text
pre_sort_oxide_thickness_nm  ──X──►  disposition decision
```

## 9. Leakage analysis

The column does not contain `first_pass_fail`, attempt `pass_fail`, a failure code, a primary failure, a test outcome, a disposition, an sbin, a sequence index, or a retest result.

It does not contain `die_noise` or `fail_p`, so it is not the coin-flip probability. Two dies on the same wafer share `lot_eff` and `wafer_eff` and differ by metrology noise only. Within-wafer rank will be weak. That is accepted.

Leave-one-lot-out does not use held-out labels to build the value. The thickness is already on the die before any label exists. Training-fold scaling, if added later, is fit on training lots only.

## 10. Hidden-truth analysis

The column is not `scenario_id`, `role`, `expected_signal`, `true_cause`, `injected_effect`, `ground_truth`, `recoverable_fraction`, or the generator seed.

`extra`, `extra_p`, `extra_p_edge`, `extra_p_tester`, and `extra_p_per_wafer` are not inputs. Edge versus inner, the affected tester, and the L004 wafer ramp stay in `fail_p` and in the existing parametric shifts. They are not copied into the thickness.

`lot_eff` and `wafer_eff` are internal normal draws, not scenario names. Publishing only the thickness does not publish the scenario label. A lot with a high thickness is a lot with a high process offset, which every lot can have.

## 11. Existing-outcome preservation

The 2,500 eligible dies, 251 first-pass failures, 2,249 first-pass passes, and FPY 0.8996 come from `die.failed` and from retests not rewriting the first-pass label.

This design does not change `fail_p`, does not change the eight parametric draws, does not change `_param_fail`, and does not consume the main random stream. Replaying generation with a side stream therefore assigns the same `die.failed` values as the saved tables. Appending the column, or writing it to a sibling file keyed by `(lot_id, wafer_id, die_id, attempt_id)`, leaves the existing pass/fail cells in place.

If a later implementation draws the thickness from the main `rng` before the coin flip, reject that implementation. It would change who fails. That failure mode is a condition in section 21, not a property of this design.

## 12. Cross-lot applicability

The same formula runs for L001, L002, L003, L004, and L005. Each lot contributes one `lot_eff`. Each of its five wafers contributes one `wafer_eff`. Nothing in the formula checks `role` or lot id.

The association with failure is the shared process offset, not a single-lot rule. L002’s edge gap, L003’s tester gap, and L004’s wafer ramp remain in the existing fail process and are intentionally absent from this column. The thickness should not be judged by whether it reproduces those three patterns.

The expected relationship is modest on every lot: a higher lot or wafer offset slightly raises `fail_p` and shifts thickness by `8.0 * offset` nm, and the sort outcome is still the coin flip plus the existing limit checks.

## 13. Coverage

One finite value per eligible first-pass die: 2,500 / 2,500. Missingness is none.

Retest attempts do not get a second metrology draw. If a retest row is emitted, it repeats the first-pass thickness. The ML row remains the first-pass attempt only.

## 14. LOLO compatibility

The value is fixed before labels exist. Held-out-lot labels are not an input. A later model may standardize the column using training lots only. The raw nanometer value for a held-out die does not depend on that fold.

## 15. Why the measurement is genuinely new

It is not a function of the stored attempt columns. Coordinates, timestamp, temperature, voltage, site, and equipment ids do not determine `lot_eff` or `wafer_eff`. Those two offsets are computed in the generator and then discarded. The thickness is the first agent-visible observation of them.

## 16. Why existing feature engineering cannot replace it

Normalized coordinates, radius, border/inner, lot-relative time, and equipment encodings were already evaluated. They stay below a constant-rate PR-AUC of 0.1004. They cannot recover `lot_eff` or `wafer_eff`.

A margin or a distance-to-limit on `VMIN`, `VMAX`, or `IDDQ` still uses values that force FAIL: 28, 1, and 29 limit misses, all failures, 56 distinct dies, zero passes. That transform stays rejected.

## 17. Alternatives considered

| Property | Assessment |
| --- | --- |
| Measurement name | `pre_sort_oxide_thickness_nm` restricted to a wafer-index ramp on the drifting lot only |
| Physical meaning | Boat-position oxide drift |
| Unit | nm |
| Generated when | Before disposition |
| Input variables | Wafer index, and only when the hidden role is process drift |
| Generated before disposition? | Yes |
| Does disposition read it? | No |
| Can it change PASS/FAIL? | No |
| Uses hidden truth? | It switches on the hidden role |
| Uses target? | No |
| Available for 2,500 dies? | Only if a flat value is filled elsewhere |
| Cross-lot signal | No. The slope exists on one lot |
| Cross-wafer signal | On that lot only |
| Expected ML usefulness | Not used as a selection criterion |
| Leakage risk | Encodes one scenario |
| Why it is not primary | It is a one-lot feature. Wafer order is already visible from timestamps |

A second rejected form is noted in section 18 rather than fully specified: storing `fail_p`.

## 18. Rejection reasons

- `fail_p`, `extra`, or `die_noise` as the stored value. That is a failure probability, not a measurement.
- Any transform of `VMIN`, `VMAX`, `IDDQ`, `SUPPLY_CURRENT`, `CONTACT_RESISTANCE`, `INTERCONNECT_RESISTANCE`, `ON_RESISTANCE`, or `VDD`. Disposition already reads them, or the force path exists and the column is not a new observation.
- T001–T010 outcomes, failure codes, and dispositions.
- A column that is 1 on the affected tester or 1 on edge dies of one role. The coordinates and tester id are already stored, and the flag would be the scenario.
- A thickness formula that takes `extra_p`, `extra_p_edge`, `extra_p_tester`, or `extra_p_per_wafer` as inputs. Those are the injected probabilities.
- Any draw that advances the main `rng` used for `fail_p`, parametric draws, or the fail coin flip. That would change the 251 failures.

## 19. Exact implementation changes that would be required later

Not done in this task.

- Add `pre_sort_oxide_thickness_nm` to the in-memory die after `fail_p` is computed in `build_population`.
- Draw it with a side `random.Random`, seeded independently of the main generator stream, in stable die order.
- Do not add the name to the `parametric` limit map, `_param_fail`, `fail_ids`, or the `die.failed` assignments in `realize`.
- Persist it on the first-pass attempt under `(lot_id, wafer_id, die_id, attempt_id)`. Do not put it in a column the current limit checker reads.
- Leave `die_attempts.csv` pass/fail, the test-result outcomes, and the eight parametric values unchanged.
- A later ML allowlist entry is a separate step after the column exists and the preservation checks pass. This design does not add that entry and does not train on it.

## 20. Validation checks required after implementation

- Eligible dies 2,500, first-pass fails 251, first-pass passes 2,249, FPY 0.8996.
- Existing pass/fail cells match the pre-change file.
- 2,500 non-null thickness values on first-pass dies, one per physical key, no `die_id`-only join.
- No code path from the new column to `die.failed` or `_param_fail`.
- The main random stream is not consumed by the thickness draw. A regression that deletes the side draw reproduces the previous outcomes.
- The column is absent from hidden-truth fields and from T001–T010 outcome columns.
- `yi_ml_v1` is still the active artifact. Production authorization is still false.

## 21. Conditions for proceeding to implementation

- The thickness uses the side stream and the formula in section 4, not a refit aimed at a score.
- `realize` still does not read the column.
- Existing first-pass outcomes are checked equal to the saved V2 counts before any ML work.
- The column is not described as a root cause or as a guaranteed yield recovery.
- No ATE limit, recipe, equipment setting, production authorization, automatic retrain, or automatic activation is added.
- Training remains a later decision. This document does not authorize `yi_ml_v5`.

## 22. Final recommendation

**APPROVED_FOR_IMPLEMENTATION**

Implement later, as an added pre-sort oxide-thickness column on the existing V2 dies, using a side random stream and the lot and wafer process offsets that already exist before the fail bit. Do not implement it in this task. Do not train a model until the preservation checks in section 20 have passed on the saved files.
