# ML View Architecture Review

Review only. No code was changed. No dataset was generated or edited. No model was trained. `yi_ml_v1` stays ACTIVE. Production authorization stays false.

## 1. Executive conclusion

**APPROVED_WITH_CONDITIONS.**

One canonical `yi_synthetic_v2` dataset, with a statistical view and a separate ML view of that same content, is a sound architecture. It keeps one manufacturing world and lets each consumer use a shape that matches its job.

The approval stops at the architecture. A new view does not repair the feature-audit verdict: **B. Insufficient representation.** Reshaping fields that are already in the 16-column contract, or renaming a measurement that forces FAIL, does not create a legitimate predictive feature. Training a candidate after the view exists is not authorized by this review. `yi_ml_v5` is not justified on the current tables.

## 2. Proposed architecture

`yi_synthetic_v2` remains the only source of truth: the same lots, wafers, dies, coordinates, equipment, environment, tests, parametric measurements, first-pass outcomes, and failure records.

```text
yi_synthetic_v2 canonical tables
        │
        ├──────────────────────────────┐
        ▼                              ▼
 Statistical view                  ML view
 (current tables and               (deterministic projection
  yield calculations)               of pre-outcome fields)
        │                              │
        ▼                              ▼
 Statistical evidence              ML model, if a later
                                   leakage-clean column exists
        │                              │
        └──────────────┬───────────────┘
                       ▼
                 Evidence layer
                       ▼
               Hypothesis engine
                       ▼
              Opportunity engine
                       ▼
                   Dashboard
```

If the ML view has no leakage-clean signal, or the model fails the constant-rate checks, the ML branch is `NEEDS_MORE_DATA`. Statistical evidence may still be reported. It must not be labeled ML support.

The current code is already close to this split. Statistical analysis reads `die_attempts.csv`, test results, and `calculate_fpy`. ML reads `load_ml_dataset` and `FeatureBuilder` in `src/yield_improvement/ml/features.py`. The two outputs meet in `src/yield_improvement/hypotheses/composer.py` and `src/yield_improvement/ml/evidence.py`.

## 3. Why same-source/separate-view may be appropriate

Statistical yield analysis needs attempt rows, test slots, dispositions, and population counts. A supervised model needs one row per physical die, a target held outside the matrix, and columns that exist before that target is assigned.

Those are different shapes of one set of facts. A view can normalize coordinates, classify the same grid as border or inner, or encode equipment, without creating a second lot of wafers. The underlying dies stay `(lot_id, wafer_id, die_id)`.

A view cannot change generation semantics. If a column is written from the fail bit, or the fail bit is written from the column, a new name does not make it a pre-outcome feature.

## 4. Comparison of Option A, B, and C

### Option A — one dataset, one representation

Both the statistical engine and the model read the same row shape.

Properties: one lineage, no second copy to drift, simple joins.

Risks: the statistical tables include disposition, failure codes, and test outcomes. Putting that shape in front of the model makes leakage the default. Stripping those columns until the table is also a good statistical table forces one shape onto two jobs. The current 16-column contract is already a narrowed form of A, and every evaluated model stayed below prevalence 0.1004.

### Option B — one canonical dataset, separate views

The tables stay canonical. Statistics keep their rows. ML gets a deterministic projection.

Properties: same lots, wafers, dies, coordinates, equipment, measurements, and first-pass outcomes. Each consumer can drop fields the other needs. Identity and leave-one-lot-out stay defined on the canonical keys. Hidden ground truth never has to enter the ML view.

Risks: a view can silently reintroduce a denied column under a new name. Fold-local scaling can use the held-out lot if it is fit on the full frame. A view that only renames the current contract can be mistaken for new evidence. Two views can drift if either one is regenerated from a different seed.

### Option C — two independently generated datasets

One synthetic world for statistics and another for ML.

Properties: the ML world could be drawn so that measurements never set the fail bit, which would make supervised learning easier to interpret.

Risks: it is a different manufacturing world. Lots, wafers, spatial gaps, equipment, and first-pass outcomes would no longer be the same facts. A hypothesis from one world would not be evidence about the other. This breaks the requirement that the agent investigate `yi_synthetic_v2`.

Option B is the one that matches the requirement. Option A is too coarse for leakage control. Option C optimizes model convenience by abandoning the source of truth. The choice is not based on the benchmark scores. Those scores only show that the current projection is weak. They do not make a second world valid.

## 5. Data lineage

Generation order in `src/yield_improvement/synthetic/v2_generator.py` is fixed:

```text
build_population
    coordinates, equipment, temperature, voltage, site, timestamp, fail_p
        ↓
realize
    optional mean shift, then parameter draw
        ↓
    fail bit from fail_p
        ↓
    if that draw was a pass and a parameter is outside its limit, force the fail bit
        ↓
build_tables
    disposition, failure code, and T001–T010 outcomes written from that bit
        ↓
first_pass_fail
    first-attempt disposition from calculate_fpy
```

An ML column is allowed only when its lineage ends before the fail bit is read, and the fail bit is not assigned from that column. `first_pass_fail` stays the target, not a feature. `attempt_id` is the join key for the first-pass attempt. Retest rows are a later copy of the same draw and stay out of the first-pass matrix.

## 6. Leakage considerations

These transforms do not change meaning and do not read the fail bit:

- `normalized_x` / `normalized_y` from `x` and `y`
- radial distance and edge distance from the same coordinates
- border/inner from the observed 1–10 grid bounds
- equipment identifiers, temperature, voltage, and site as stored on the attempt
- a lot-relative timestamp scaled only by timestamps in that lot

They were already evaluated. `yi_ml_v2` is the 16-column logistic baseline (calibrated PR-AUC 0.0909). `yi_ml_v3_spatial` replaces the radius category with border/inner (PR-AUC 0.0939). `yi_ml_v4` adds lot-relative time (PR-AUC 0.0894). The architecture benchmark’s other families sit between PR-AUC 0.0898 and 0.0965. Prevalence is 0.1004. Calibrated ROC-AUC values are below 0.50. A new view that only repeats these transforms is not new information.

These stay out of the feature matrix:

- `first_pass_fail`, attempt `pass_fail`, disposition, failure code, primary failure
- `test_pass_fail`, `is_first_fail`, `sbin`, `hbin`
- parametric `pass_fail`
- retest outcome
- `scenario_id`, `true_cause`, `injected_effect`, `ground_truth`, `generator_seed`, `recoverable_fraction`
- `tester_fail_rate` and `probe_fail_rate` as if they were pre-disposition sensors. They are means of the training labels. Leave-one-lot-out keeps the held-out die’s label out of the fit. That does not make them measurements taken before disposition.

`timestamp_epoch` is pre-disposition, but its pooled ROC of 0.559 is the L004 within-lot gradient (within-lot ROC 0.748). The other lots sit near 0.50. A view may include it. It is not a five-lot signal.

GRU stays `BLOCKED_LEAKAGE_RISK`. T001–T010 rows contain identity, slot id, sequence index, a repeated timestamp, and the outcome. The outcome was written from the fail bit. On all 2,500 first-pass dies, any slot FAIL matches the attempt FAIL.

## 7. Parametric-data implications

`VMIN`, `VMAX`, `IDDQ`, `SUPPLY_CURRENT`, `CONTACT_RESISTANCE`, `INTERCONNECT_RESISTANCE`, `ON_RESISTANCE`, and `VDD` are drawn before `die.failed` is set. The draw does not read the fail bit. Immediately afterward, a limit miss forces `die.failed = True`.

On the saved first-pass rows the force rule fires as follows. Every limit miss is an attempt FAIL. No first-pass pass has a limit miss.

- VMIN: 28 misses, all attempt FAIL
- VMAX: 1 miss, attempt FAIL
- IDDQ: 29 misses, all attempt FAIL
- the other five parameters: 0 misses

56 distinct dies have at least one limit miss. The other 195 failures have none.

`VMIN`, `VMAX`, and `IDDQ` cannot enter an ML view, including under names such as `VMIN_margin` or a normalized copy. The fail bit is a function of the limit check on that value. Renaming does not remove the function.

The other five parameters did not force a label on this file, and the same force path exists in code. Their observed separation does not hold across L001–L005. `CONTACT_RESISTANCE` is the largest of them (pooled ROC 0.538) and is below 0.50 on L001. They are not a reason to train. The parametric `pass_fail` column is the limit result and stays denied.

The default loader already drops these eight names. `load_ml_dataset` keeps only the V1 parameter names, which are absent from the V2 file. The ML frame has no parametric columns. That absence should remain until a future measurement is recorded before disposition and is not read back to set the fail bit.

## 8. Physical identity implications

The physical die is `(lot_id, wafer_id, die_id)`. On the 2,500 first-pass rows that key is unique. `die_id` has 100 values and 25 rows each, so a `die_id`-only join crosses lots and wafers.

`attempt_id` identifies the attempt. The first-pass ML row uses attempt number 1. The 60 retest attempts, 480 retest parametric rows, and 600 retest test rows reuse the first-pass measurement. They must not be joined into the first-pass matrix.

Leave-one-lot-out stays the split: one lot held out, 2,000 train and 500 test, no shared lot. Scaling, encodings, and calibration are fit on the training lots only.

## 9. Statistical-view responsibilities

The statistical view keeps the canonical tables. It owns first-pass yield, population comparisons, spatial and equipment groupings, and the hypothesis inputs that do not depend on a model score.

It may report a real rate gap, including the border-versus-inner gap that is strong on L002 and absent on L001. It must not describe that gap as ML support. It must not read hidden ground truth into an agent-facing finding. It does not gain authority to change ATE limits, recipes, equipment, or production authorization when the ML branch is empty.

## 10. ML-view responsibilities

The ML view, when one is built, is a deterministic projection:

- one row per first-pass physical die
- features whose lineage passes section 5
- target `first_pass_fail` stored beside the matrix, not inside it
- no second dataset and no fabricated measurements
- no test-slot sequence until a per-step measurement exists that is not the outcome

The view’s job is leakage control and a stable matrix. It is not a promise that the matrix will rank failures. The existing projection already failed that test across logistic regression, random forest, extra trees, histogram gradient boosting, XGBoost, LightGBM, and a small MLP.

## 11. ML dependency implications

Making ML a required evidence layer is sound only if the layer fails closed.

```text
V2 canonical data
    ├─ statistical view → statistical evidence
    └─ ML view → model → ML evidence, or NEEDS_MORE_DATA
              both meet at the evidence layer
              → hypothesis → opportunity → dashboard
```

`NEEDS_MORE_DATA` is already the path in `attach_ml_evidence` when support is insufficient: the finding is not marked ML-supported. That behavior should stay. The statistical engine must not fill the gap by relabeling a rate comparison as ML evidence.

ML remains secondary to safety. It does not change test limits, recipes, equipment settings, or production programs. Production authorization stays false. `yi_ml_v1` stays the active artifact until a later human lifecycle step, which this review does not take.

## 12. Risks

- Treating Option B as permission to train on a renamed copy of the current contract.
- Admitting `VMIN`, `IDDQ`, or `VMAX` through a margin or normalized alias.
- Building a GRU on T001–T010 outcomes.
- Joining on `die_id` alone, or folding retest rows into the first-pass label.
- Fitting scalers or calibration on the held-out lot.
- Calling a statistical finding ML-supported while support is `NEEDS_MORE_DATA`.
- Generating a second synthetic world so that a model score rises. That is Option C, and it is rejected.
- Reading `scenario_id` or hidden ground truth into the matrix because the view is “for ML.”

## 13. Conditions that must be satisfied before implementation

- V2 bytes stay unchanged. No second synthetic world is generated.
- Every ML column has a written lineage to a canonical column and a generation step that does not read the fail bit.
- No renamed copy of a limit-forced parameter, test outcome, failure code, primary failure, disposition, retest outcome, `scenario_id`, or hidden ground truth.
- `first_pass_fail` stays outside the matrix. Leave-one-lot-out stays the split. Fold-local scaling does not use the held-out lot.
- A column already shown to be weak — coordinates, radius region, border/inner, timestamp, temperature, voltage, site, equipment — is not a reason to train.
- Training a candidate happens only after a leakage-free column exists that this audit has not already rejected. That column is not in the current tables.
- `yi_ml_v1` stays ACTIVE. Any future model is CANDIDATE only. Production authorization stays false.
- If ML is mandatory, missing or invalid ML evidence remains `NEEDS_MORE_DATA` and is not replaced by statistical wording.

## 14. Recommended next step

Do not implement the view yet. Do not train `yi_ml_v5`.

The next authorized step, if one is requested, is a column-lineage contract for a future view, not a model. A useful measurement has to be recorded before disposition and must not be read back to set the fail bit, the test outcome, or the failure code. Until that exists, ML support on V2 stays `NEEDS_MORE_DATA`, and the statistical and ML branches stay separate at the evidence layer.
