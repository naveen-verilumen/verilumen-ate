# ML Column-Lineage Contract

Design only. The ML view was not built. No model was trained. V2 was not modified. `yi_ml_v1` stays ACTIVE. Production authorization stays false.

## Conclusion

**NO — source-data enhancement required.**

The current canonical tables do not contain a qualifying new predictive measurement. The ordering of generation is known, so the result is not ambiguous. Building the ML view from the columns that already exist would only repackage a matrix that has already failed leave-one-lot-out.

## 1. Purpose

This contract states what a future ML column must satisfy before it can enter a feature matrix for `first_pass_fail`. It is the gate in front of any later view or candidate model. It does not authorize `yi_ml_v5`.

A column is not made valid by renaming it, scaling it, or moving it into a separate file.

## 2. Canonical source

The only source is `data/synthetic/agent_visible/yi_synthetic_v2/`.

That directory stays the source of truth for the same lots, wafers, dies, coordinates, spatial layout, equipment, environment, tests, parametric measurements, first-pass outcomes, and failure records. A future ML view is a deterministic projection of those tables. It is not a second synthetic manufacturing world.

Current model state, unchanged by this contract:

- `yi_ml_v1` is ACTIVE
- `yi_ml_v2` is unchanged
- `yi_ml_v3_spatial` is unchanged
- `yi_ml_v4` is CANDIDATE with support `NEEDS_MORE_DATA`
- GRU is `BLOCKED_LEAKAGE_RISK`

## 3. Current feature inventory

`FeatureBuilder` emits 16 columns. The V2 parametric names are not among them. The loader keeps only the older parameter names `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, and `TEST_TIME_MS`, and none of those names are in the V2 file.

Each existing column is classified once. `NOT_PREDICTIVE_ENOUGH` means the lineage is real and the column was already evaluated, and it must not be treated as a new signal. `TARGET_DERIVED` means the column is a function of `first_pass_fail`.

| Feature | Class |
| --- | --- |
| `die_x` | `NOT_PREDICTIVE_ENOUGH` |
| `die_y` | `NOT_PREDICTIVE_ENOUGH` |
| `normalized_x` | `NOT_PREDICTIVE_ENOUGH` |
| `normalized_y` | `NOT_PREDICTIVE_ENOUGH` |
| `radial_distance` | `NOT_PREDICTIVE_ENOUGH` |
| `edge_distance` | `NOT_PREDICTIVE_ENOUGH` |
| `spatial_region` | `NOT_PREDICTIVE_ENOUGH` |
| `timestamp_epoch` | `NOT_PREDICTIVE_ENOUGH` |
| `temperature_c` | `NOT_PREDICTIVE_ENOUGH` |
| `voltage_v` | `NOT_PREDICTIVE_ENOUGH` |
| `site` | `NOT_PREDICTIVE_ENOUGH` |
| `tester_id` | `NOT_PREDICTIVE_ENOUGH` |
| `probe_card_id` | `NOT_PREDICTIVE_ENOUGH` |
| `prober_id` | `NOT_PREDICTIVE_ENOUGH` |
| `tester_fail_rate` | `TARGET_DERIVED` |
| `probe_fail_rate` | `TARGET_DERIVED` |

No current column is `APPROVED_EXISTING` in the sense of a qualifying new measurement. No current column is `NEEDS_MORE_EVIDENCE`. The benchmark and the feature audit already measured them.

## 4. Feature-by-feature lineage

Population fields are written in `build_population` before `die.failed` exists. `realize` draws parameters and then sets the fail bit. `build_tables` writes disposition and T001–T010 outcomes from that bit. `first_pass_fail` is the first-attempt disposition from `calculate_fpy`.

| Feature | Canonical source | When it exists | Reads the fail bit | Meaning |
| --- | --- | --- | --- | --- |
| `die_x`, `die_y` | `die_attempts.csv` `x`, `y` | Before disposition | No | Grid position, integers 1 through 10 |
| `normalized_x`, `normalized_y` | Same `x`, `y` | Derived in the training fold | No | Position scaled by the training-fold min and span |
| `radial_distance` | Same `x`, `y` | Derived | No | Distance from the origin |
| `edge_distance` | Same `x`, `y` | Derived in the training fold | No | Training-fold maximum radius minus radial distance |
| `spatial_region` | Same `x`, `y` | Derived in the training fold | No | `EDGE` / `CENTER` / `OTHER` from training-fold radius quantiles |
| `timestamp_epoch` | `timestamp` | Before disposition; encoding uses the training-fold minimum | No | Seconds after the earliest training timestamp |
| `temperature_c`, `voltage_v` | Attempt columns | Before disposition | No | Drawn environment on the attempt |
| `site` | Attempt column | Before disposition | No | `(x - 1) % 2` |
| `tester_id`, `probe_card_id`, `prober_id` | Attempt columns | Before disposition | No | Equipment identifiers |
| `tester_fail_rate` | Training rows of `first_pass_fail` by `tester_id` | After labels exist on the training lots | Yes, the training labels | Mean fail rate, not a sensor |
| `probe_fail_rate` | Training rows of `first_pass_fail` by `probe_card_id` | After labels exist on the training lots | Yes, the training labels | Mean fail rate, not a sensor |

On this grid every leave-one-lot fit produces the same coordinate bounds, so the spatial encoding does not move between folds. The two fail rates do move, because they are label means.

Held-out evidence already on record, calibrated, prevalence 0.1004:

- `yi_ml_v2` logistic PR-AUC 0.0909, ROC-AUC 0.4592
- `yi_ml_v3_spatial` border/inner PR-AUC 0.0939, ROC-AUC 0.4666
- `yi_ml_v4` lot-relative time PR-AUC 0.0894, ROC-AUC 0.4499
- Benchmark families from logistic through a small MLP: PR-AUC 0.0898 to 0.0965, ROC-AUC below 0.50

Within-lot coordinate effects change sign. Timestamp’s pooled ROC of 0.559 is the L004 gradient (within-lot ROC 0.748). The other lots sit near 0.50. Temperature, voltage, site, and equipment ids do not hold a direction across L001–L005.

## 5. Approved transformations

A transformation is approved only as a representation of an already-lineage-valid field. Approval does not make it a new measurement and does not authorize training.

Allowed when fitted on training lots only, or when the rule does not use labels at all:

- Min-span scaling of `x` and `y`
- Radial distance and edge distance from those coordinates
- Border versus inner from the observed grid bounds in `yield_analysis.grid_region`, which on V2 is the 1–10 rectangle
- One-hot or other deterministic encodings of `tester_id`, `probe_card_id`, and `prober_id`
- The raw `temperature_c`, `voltage_v`, and `site` values
- A lot-relative timestamp that uses only timestamps in that lot: earliest 0, latest 1, no labels

These are the transforms already covered by `yi_ml_v2`, `yi_ml_v3_spatial`, and `yi_ml_v4`. Repeating them in a new view is not a qualifying feature.

## 6. Rejected transformations

| Proposed form | Class | Why |
| --- | --- | --- |
| Radius `EDGE` / `CENTER` / `OTHER` as a new signal | `REJECTED_ALREADY_TESTED` | It is the current `spatial_region`. Pooled PR-AUC stays below 0.1004 |
| `BORDER` / `INNER` as a new signal | `REJECTED_ALREADY_TESTED` | `yi_ml_v3_spatial`. The L002 gap does not hold on L001, L003, and L004 together |
| `relative_position_within_lot` as a new signal | `REJECTED_ALREADY_TESTED` | `yi_ml_v4`. L004 ROC-AUC fell below 0.50 |
| Any margin, residual, or renamed copy of `VMIN`, `VMAX`, or `IDDQ` | Rejected | The fail bit is assigned from the limit check. A new name does not remove that |
| Parametric `pass_fail` | Rejected | It is the limit result |
| T001–T010 `test_pass_fail`, `pass_fail`, `failure_code`, or `is_first_fail` as a sequence | `BLOCKED_LEAKAGE_RISK` | Those fields are written from the fail bit. Any slot FAIL matches the attempt FAIL on all 2,500 dies |
| `tester_fail_rate`, `probe_fail_rate` as pre-disposition sensors | `TARGET_DERIVED` | They are means of `first_pass_fail` |
| `die_id` as a global key | Rejected | 100 ids, 25 first-pass rows each |

## 7. Parametric decisions

The eight V2 parameters stay rejected for this ML task. Feature engineering does not reopen them.

`realize` draws each value before it sets `die.failed`. If the value is outside its limit, it then sets `die.failed = True`. The draw does not read the fail bit. The fail bit does read the draw. That is why a margin feature is still the label rule.

Observed first-pass limit misses, each one also an attempt FAIL, with zero misses on first-pass passes:

| Parameter | Limit misses | Decision |
| --- | ---: | --- |
| VMIN | 28 | Remains rejected. Upper limit assigns FAIL |
| VMAX | 1 | Remains rejected. Lower limit assigns FAIL |
| IDDQ | 29 | Remains rejected. Upper limit assigns FAIL |
| SUPPLY_CURRENT | 0 | Remains rejected. The force path exists, and the column does not separate lots |
| CONTACT_RESISTANCE | 0 | Remains rejected. Pooled ROC 0.538, and L001 is below 0.50 |
| INTERCONNECT_RESISTANCE | 0 | Remains rejected. No cross-lot separation |
| ON_RESISTANCE | 0 | Remains rejected. No cross-lot separation |
| VDD | 0 | Remains rejected. No cross-lot separation |

56 distinct first-pass dies have at least one limit miss. All 56 are failures. The other 195 failures have no limit miss. Dropping the miss rows and keeping the rest of `VMIN` or `IDDQ` still uses the column the force rule reads, and the leftover gap is concentrated on L004.

Join rule, if a later audit reads the file again: one first-pass row per `(lot_id, wafer_id, die_id, attempt_id)`, 2,500 rows, no duplicate key, no missing first-pass die. Do not join on `die_id` alone.

## 8. Leakage rules

A future column is forbidden when any of these are true:

1. It has no lineage to a canonical V2 column.
2. It is fabricated.
3. It is written after first-pass disposition, or from that disposition.
4. Its generation reads the fail bit or `first_pass_fail`.
5. It uses a failure code, test outcome, primary failure, disposition, or retest outcome.
6. It uses `scenario_id`, `true_cause`, `injected_effect`, `ground_truth`, `generator_seed`, or `recoverable_fraction`.
7. Computing it requires the held-out lot’s labels.
8. It is a rename of a column this contract already rejected.

Correlation with failure is not itself leakage. A column that merely moves with the fail rate can still be rejected as `NOT_PREDICTIVE_ENOUGH` or `REJECTED_ALREADY_TESTED`.

## 9. Identity rules

The physical die is `(lot_id, wafer_id, die_id)`. That key is unique on the 2,500 first-pass rows.

`attempt_id` identifies the attempt. The ML row is the first-pass attempt, attempt number 1. `die_id` is never the join key by itself.

The target `y` is `first_pass_fail` for that physical die. `y` is stored beside `X`. It is not a column of `X`.

## 10. Retest rules

There are 60 retest attempts, 480 retest parametric rows, and 600 retest test rows. Retest parametric rows copy `die.measurements` from the first pass. They are not new draws.

A future view includes only attempt number 1. Retest pass or fail does not change `first_pass_fail` and does not enter `X`.

## 11. LOLO rules

The split remains leave-one-lot-out: five folds, one lot held out, 2,000 train rows and 500 test rows, no lot on both sides.

Any learned transform — scaling limits, radius quantiles, category levels, imputation, and isotonic calibration — is fit on the training lots only. The held-out lot’s labels are not used. A lot-relative timestamp may use that lot’s own timestamps, because those are not labels, and it must not use another lot’s timestamps or any fail bit.

## 12. Definition of a valid future ML feature

A future column may be added only when all of the following are true:

1. Lineage points at a canonical V2 field, or at a deterministic function of such fields.
2. The field is observable on the agent-visible tables. It is not hidden ground truth.
3. It exists before first-pass disposition.
4. Generation does not read the fail bit or `first_pass_fail`.
5. The fail bit is not assigned from this field. A limit check that forces FAIL disqualifies the field and every transform of it.
6. It does not use failure code, test outcome, primary failure, disposition, or retest outcome.
7. It does not use `scenario_id`, `true_cause`, `injected_effect`, or `ground_truth`.
8. It can be computed for a held-out lot without that lot’s labels.
9. It has a physical or data-generation meaning that can be stated in one sentence.
10. It is not one of the 16 current columns, and it is not a transform already classified `REJECTED_ALREADY_TESTED`.

The boundary is:

```text
Canonical V2
    ↓
ML view
    ↓
Feature matrix X
    +
Target y = first_pass_fail
```

`y` never enters `X`.

## 13. Missing-signal category

The missing category is a **legitimate pre-disposition measurement that disposition does not read**.

What V2 already stores, and why it does not fill that category:

- Coordinates, equipment ids, temperature, voltage, site, and timestamp are pre-disposition context. They are `NOT_PREDICTIVE_ENOUGH`.
- Electrical values exist as the eight parametric columns. Disposition reads their limit check, so they are not eligible.
- Test slots exist. They store outcomes, not measurements. GRU stays blocked.
- Equipment health is not a measurement. Only the equipment id is stored.
- Process state is not a separate observable. Where the generator shifts a measurement mean before the draw, that measurement is one of the parametric columns already rejected.

No other observable category in the current tables meets the definition in section 12.

Preserving the same first-pass outcomes matters. Changing `realize` so that today’s parameters no longer force FAIL would change who fails. That is not the same data. The enhancement has to add a measurement on these same dies, written before disposition, and leave the existing fail bit, tests, and first-pass outcomes untouched. This contract does not name that measurement and does not specify its formula.

## 14. Conditions required before ML training

Training stays blocked until every item below is true:

- V2’s current lots, wafers, dies, coordinates, equipment, environment, tests, existing measurements, and first-pass outcomes are unchanged.
- Any new column meets section 12, including the rule that disposition does not read it.
- The column is not a rename of a rejected parameter or of T001–T010 outcomes.
- The matrix is one first-pass row per `(lot_id, wafer_id, die_id)`, joined by `attempt_id`, with retests excluded.
- Leave-one-lot-out and fold-local fitting are unchanged.
- `yi_ml_v1` stays ACTIVE. A later model is CANDIDATE only. Production authorization stays false.
- If the new column is absent or fails the lineage gate, support remains `NEEDS_MORE_DATA`. Statistical findings are not relabeled as ML support.

## 15. Recommended next step

Do not build the ML view. Do not train.

The next authorized step, if one is requested, is a source-data design for one additional pre-disposition measurement on these same dies, with an explicit statement that `realize` will not read it when setting the fail bit. Until that design exists and the saved tables actually contain the column, there is no qualifying feature and no `yi_ml_v5`.
