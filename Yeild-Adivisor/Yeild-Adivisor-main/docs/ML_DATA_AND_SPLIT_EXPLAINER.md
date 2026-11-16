# ML data lineage and split explainer

This document traces **the code that actually runs**, then reports **the numbers on the dataset that produced `yi_ml_v1`**. It does not retrain the model and does not change the feature contract, LOLO split, or calibration.

Audience: ML engineers, wafer-sort / test engineers, and project managers.

---

## 1. What this model is answering

The Logistic Regression champion (`yi_ml_v1`) estimates:

> P(this **eligible unique die** fails on its **first pass**)

It is **predictive association**, not a root cause, not recovered yield, and not a production authorization.

---

## 2. Which dataset trained the current model

From `artifacts/ml/yi_ml_v1/metadata.json` (read-only):

| Field | Value |
|-------|--------|
| `analysis_id` | `ds_0b5542c71e1a13e0` |
| Path | `data/synthetic/agent_visible/ds_0b5542c71e1a13e0` |
| Synthetic scenario (hidden GT, not a model input) | **S02** (spatial EDGE) |
| `model_name` | `logistic` |
| `model_version` | `yi_ml_v1` |
| `split_strategy` | `leave_one_lot_out` |
| `n_samples` | 784 |
| `n_positives` | 207 |
| `n_features` | 16 |
| `trained_at` | 2026-09-23T10:25:04Z |

Different commands use that folder differently:

| Command | Dataset | Trains? | Writes `yi_ml_v1`? |
|---------|---------|---------|---------------------|
| `ml train <dir>` | the folder you pass | yes (in memory, then persist) | **refuses** if `model.pkl` already exists |
| `ml predict <dir>` | the folder you pass | no | no — loads the frozen champion |
| `ml evaluate <dir>` | the folder you pass | yes, `persist=False` | no |
| `ml run <dir>` | the folder you pass | yes | same persist guard as train |
| `ml explain-data <dir>` | the folder you pass | **no** | no |

The **persisted champion** is the S02 folder above. `ml evaluate` on S01–S16 trains a **fresh in-memory** model per folder for scoring; it does not replace `yi_ml_v1`.

---

## 3. Call chain (actual functions)

```text
python -m yield_improvement ml train <dataset_dir>
        │
        ▼
__main__._ml_main
        │
        ▼
ml.pipeline.run_ml
        │
        ├─ ml.dataset.load_ml_dataset
        │       ├─ ingestion.loader.load_die_attempts
        │       ├─ load_parametric_measurements (optional file)
        │       ├─ assert_source_has_no_hidden_labels
        │       └─ build_dataset
        │               └─ yield_analysis.fpy.calculate_fpy   ← eligibility + label
        │
        ├─ ml.train.select_and_train
        │       ├─ ml.split.make_splits                     ← LOLO
        │       ├─ _cv_oof  (per candidate model)
        │       │       ├─ features.fit_feature_builder     ← train lots only
        │       │       ├─ models.make_model                ← impute/scale/one-hot + classifier
        │       │       └─ predict_proba on held-out lot
        │       ├─ ProbabilityCalibrator (fold-local, then deployed)
        │       └─ pipeline.fit on ALL eligible dies         ← persisted champion only
        │
        ├─ ml.evaluation.compute_metrics                    ← calibrated OOF
        ├─ ml.evidence.build_ml_evidence                    ← SECONDARY_SUPPORT
        └─ save_artifact  (blocked when yi_ml_v1 already exists)
```

Predict:

```text
ml predict → load_artifact (pickle) → predict_frame
             FeatureBuilder.transform with frozen train-lot statistics
             pipeline.predict_proba
             deployed isotonic calibrator
```

---

## 4. Lineage (this champion dataset)

```text
ORIGINAL DATA
  data/synthetic/agent_visible/ds_0b5542c71e1a13e0/die_attempts.csv
  784 rows  |  columns include lot/wafer/die, x/y, tester, pass_fail, …
        │
        ▼
DATA LOADING   ml/dataset.py :: load_ml_dataset
  DieAttempt list; hidden-label column names fail closed
        │
        ▼
FILTERING      yield_analysis/fpy.py :: calculate_fpy
  REJECT rows dropped; part_class / rework / first-pass / disposition rules
  On this dataset: 0 exclusions, 0 REJECT rows
        │
        ▼
ELIGIBLE POPULATION
  784 unique dies = 784 first-pass attempts
        │
        ▼
TARGET CREATION   ml/dataset.py :: build_dataset
  first_pass_fail = 1 if first_pass_disposition == FAIL else 0
  207 positives, 577 negatives  (rate 0.2640)
        │
        ▼
FEATURE ENGINEERING   ml/features.py :: FeatureBuilder
  16 derived columns (see §8). Identifiers kept on the frame, not in X.
        │
        ▼
GROUPING KEY
  groups = lot_id   (L001 … L008)
        │
        ▼
LOLO SPLIT   ml/split.py :: LeaveOneGroupOut
  8 folds, 686 train dies / 98 test dies each
        │
        ▼
MODEL TRAINING   ml/train.py :: _cv_oof then full-data refit
  Fold models: train lots only
  Persisted LogisticRegression: all 784 dies (for later predict)
        │
        ▼
OOF PREDICTION
  784 scores; each die scored by a model that never trained on its lot
        │
        ▼
CALIBRATION   ml/calibration.py :: IsotonicRegression
  Fold-local for OOF metrics; full-OOF isotonic stored for predict()
        │
        ▼
METRICS   ml/evaluation.py :: compute_metrics(y, oof_cal)
  ROC-AUC 0.715, PR-AUC 0.438, Brier 0.170, capture@10 0.198, capture@20 0.372
        │
        ▼
ML SECONDARY EVIDENCE   ml/evidence.py
  role = SECONDARY_SUPPORT; independence = false
        │
        ▼
Hypothesis engine (compose) may attach that evidence; it cannot create a
hypothesis from ML alone when no statistical signal exists.
```

---

## 5. Modeling grain: rows vs dies

**One ML sample = one Phase-1 FPY-eligible unique die** `(lot_id, wafer_id, die_id)`.

It is **not** a raw CSV row in general, **not** die × every attempt, and **not** a `test_results` row.

On **this** champion file there happens to be exactly one attempt per die (784 rows = 784 dies), so row count equals sample count. The code still goes through unique-die FPY logic. A die with a retest would still be **one** ML sample, labeled from the first pass.

Example from the file:

| Stage | Example |
|-------|---------|
| Raw attempt | `E-L001-W01-D001-1` on die `D001`, lot `L001`, wafer `W01` |
| FPY eligible | that die’s first-pass attempt |
| ML row | `die_id=D001`, `lot_id=L001`, `first_pass_fail=0` (this row is PASS) |
| Features | `die_x=0`, `die_y=0`, `tester_id=T02`, … |
| Group | `L001` (fold 1 test set) |

Wafer IDs `W01` and `W02` **repeat in every lot**. There are **2** distinct `wafer_id` strings and **16** lot–wafer pairs. Splitting is by **lot**, not by wafer id string.

---

## 6. Target: `first_pass_fail`

Implemented in `fpy.resolve_disposition` + `fpy.calculate_fpy`, copied in `build_dataset`:

```text
first_pass_fail = 1
    if the die is FPY-eligible AND first-pass disposition is FAIL

first_pass_fail = 0
    if the die is FPY-eligible AND first-pass disposition is PASS

excluded (no ML row)
    if the die is not FPY-eligible
```

Disposition of the **first-pass attempt** (`fpy.py`):

1. If `abort_flag` and `abort_is_first_pass_fail` (true in `configs/fpy_policy.yaml`) → **FAIL**
2. Else if `pass_fail` is PASS or FAIL → use it
3. Else if `sbin` maps through `bin_map` → use that
4. Else → die excluded (`MISSING_DISPOSITION`)

`build_dataset` calls `calculate_fpy(..., test_results=None)`, so **per-test sequence does not define the label**.

| Topic | Rule |
|-------|------|
| Missing disposition | Excluded from FPY and ML |
| Abort | Counted as first-pass **FAIL** |
| Retest | Label stays first-pass; later pass cannot flip the ML target to 0 |
| Rework | Excluded |
| Engineering / calibration / QA | Excluded |
| `test_results.csv` | Loaded in `load_ml_dataset` only to exist; **not joined into X or y** |

On this dataset: 207 FAIL, 577 PASS.

---

## 7. Eligibility

Code: `calculate_fpy` (`src/yield_improvement/yield_analysis/fpy.py`), policy `configs/fpy_policy.yaml`.

| Condition | Included in ML? | Reason |
|-----------|-----------------|--------|
| Production | YES | Default eligible class |
| Engineering | NO | `excluded_part_classes` |
| Calibration | NO | `excluded_part_classes` |
| Rework (`part_class` or `is_rework`) | NO | excluded class / `REWORK` |
| QA_SAMPLE / UNKNOWN_NON_PRODUCTION | NO | excluded class |
| Missing `part_class` | YES as PRODUCTION | `treat_as: PRODUCTION` |
| Retest (later attempt of an eligible die) | Die included; label = first pass | later attempts ignored for y |
| Retest-only (no first-pass row) | NO | `RETEST_ONLY` |
| Missing disposition | NO | `MISSING_DISPOSITION` |
| Aborted first pass | YES as FAIL | `abort_is_first_pass_fail` |
| `record_status=REJECT` | NO | skipped before grouping |
| Missing identity / timestamp | NO | `MISSING_IDENTITY` / `MISSING_TIMESTAMP` |
| Ambiguous duplicate `attempt_id` | NO | `AMBIGUOUS_DUPLICATE` |

Counts on `ds_0b5542c71e1a13e0`:

| Step | Count |
|------|------:|
| Raw `die_attempts` rows | 784 |
| `record_status=REJECT` | 0 |
| Unique dies in source | 784 |
| FPY exclusions | **0** |
| Eligible = ML samples | **784** |

This synthetic champion lot is a clean production first-pass extract. The filters still exist for real data.

---

## 8. Features that reach Logistic Regression

Exact list from `artifacts/ml/yi_ml_v1/feature_list.json` (matches a current `FeatureBuilder` fit on this folder):

| Feature | Type | Source | Transformation | In model? |
|---------|------|--------|----------------|-----------|
| `die_x` | numeric | `x` | float | YES |
| `die_y` | numeric | `y` | float | YES |
| `normalized_x` | numeric | `x` | `(x - train_xmin) / train_xspan` | YES |
| `normalized_y` | numeric | `y` | same for y | YES |
| `radial_distance` | numeric | `x,y` | `hypot(x,y)` | YES |
| `edge_distance` | numeric | `x,y` | `train_radius_max - radius` | YES |
| `spatial_region` | categorical | `x,y` | EDGE if radius ≥ train 80th pct; CENTER if ≤ train 20th pct; else OTHER; missing → `__missing__` | YES |
| `timestamp_epoch` | numeric | `timestamp` | unix − train min unix | YES |
| `temperature_c` | numeric | `temperature_c` | float | YES |
| `voltage_v` | numeric | `voltage_v` | float | YES |
| `site` | numeric | `site` | float | YES |
| `tester_id` | categorical | `tester_id` | string; missing → `__missing__` | YES |
| `probe_card_id` | categorical | `probe_card_id` | same | YES |
| `prober_id` | categorical | `prober_id` | same | YES |
| `tester_fail_rate` | numeric | `tester_id` + **training** labels | train-lot mean fail rate by tester; unseen tester → train global mean | YES |
| `probe_fail_rate` | numeric | `probe_card_id` + **training** labels | same for probe card | YES |

Sklearn (`ml/models.py :: make_preprocessor`), **fit on the training fold only** during OOF:

- Numeric: median impute → `StandardScaler`
- Categorical: most-frequent impute → `OneHotEncoder(handle_unknown="ignore")`

Unknown categories at test time become all-zero one-hot columns. There is **no** other scaling.

`IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, `TEST_TIME_MS` are **allowed** derived names, but this dataset’s parametric file uses `IDDQ` and `VMIN`. Those names are **not** in `PARAM_NAMES`, so they never enter X. `parametric_measurements.csv` has 1568 rows and is unused by the champion feature contract.

---

## 9. Columns that do **not** reach the model

### On the ML frame but not in X (identity / join)

`lot_id`, `wafer_id`, `die_id`, `attempt_id`, plus raw `x`, `y`, `timestamp` after they have been transformed.

### On `die_attempts.csv` but never copied into the ML frame

Including: `pass_fail`, `disposition`, `sbin`, `hbin`, `failure_code`, `abort_flag`, `is_retest`, `is_rework`, `attempt_number`, `is_first_attempt`, `part_class`, `product_id`, `step_id`, `record_status`.

These are used for **eligibility and the label**, then dropped before `FeatureBuilder`.

### Forbidden / hidden (deny list + `SOURCE_FORBIDDEN`)

`scenario_id`, `true_cause`, `injected_effect`, `generator_seed`, `ground_truth`, `recoverable_fraction`, planted-cause fields, `first_pass_fail` as a **feature**, `test_pass_fail`, `sequence_index`, `is_first_fail`, …

They are **not present** on agent-visible CSVs. If they appeared, load fails closed (`LeakageError`).

| Why excluded | Examples |
|--------------|----------|
| Leakage (label / outcome / future tests) | `pass_fail`, `sbin`, sequence, retest, primary failure keys |
| Grouping only | `lot_id` |
| Identity only | `die_id`, `wafer_id` |
| Hidden GT | `scenario_id`, `true_cause`, `injected_effect` |
| Not in current contract | parametric `IDDQ` / `VMIN` |

---

## 10. Model input vs grouping variable

| Column | Model input? | Used for splitting? | Why |
|--------|--------------|---------------------|-----|
| `lot_id` | **NO** | **YES** | LOLO group (`configs/ml.yaml` `split.group_column`) |
| `wafer_id` | NO | NO | Identity; wafers of a held-out lot leave with that lot |
| `die_id` | NO | NO | Identity; one sample per die |
| `attempt_id` | NO | NO | Join key for first-pass attributes |
| `scenario_id` | NO | NO | Hidden GT; not on agent-visible tables |
| `true_cause` / `injected_effect` / `generator_seed` | NO | NO | Hidden GT |
| 16 champion features | YES | NO | The X matrix |

---

## 11. Leave-One-Lot-Out on **this** data

Lots: `L001` `L002` `L003` `L004` `L005` `L006` `L007` `L008`

`make_splits` uses sklearn `LeaveOneGroupOut` because 8 lots ≤ `max_lolo_lots` (12). If a future dataset had more than 12 lots, it would fall back to `GroupKFold` (k=5). That did **not** happen here.

| Fold | Training lots | Test lot | Train dies | Test dies | Train FAIL | Test FAIL |
|------|---------------|----------|------------|-----------|------------|-----------|
| 1 | L002–L008 | **L001** | 686 | 98 | 177 | 30 |
| 2 | L001, L003–L008 | **L002** | 686 | 98 | 184 | 23 |
| 3 | L001–L002, L004–L008 | **L003** | 686 | 98 | 183 | 24 |
| 4 | L001–L003, L005–L008 | **L004** | 686 | 98 | 179 | 28 |
| 5 | L001–L004, L006–L008 | **L005** | 686 | 98 | 180 | 27 |
| 6 | L001–L005, L007–L008 | **L006** | 686 | 98 | 185 | 22 |
| 7 | L001–L006, L008 | **L007** | 686 | 98 | 187 | 20 |
| 8 | L001–L007 | **L008** | 686 | 98 | 174 | 33 |

No train/test lot overlap on any fold. Every lot is the test lot **exactly once**. 8 × 98 = 784 OOF predictions.

### Why this is not random 80/20

Random row splits can put two dies from **the same lot** on both sides. Tester, time, and process effects that are lot-specific would leak into the test score. LOLO asks a factory question: **how does the model behave on a lot it has never trained on?**

---

## 12. One fold in detail (fold 1)

```text
Fold 1
  Test lot:        L001
  Training lots:   L002 L003 L004 L005 L006 L007 L008
  Training dies:   686   (177 FAIL / 509 PASS)
  Test dies:       98    (30 FAIL / 68 PASS)

  FeatureBuilder.fit(train frame, train labels)
      → x/y quantiles, tester_fail_rate, probe_fail_rate from L002–L008 only
  X_train = transform(train)     16 columns, then impute/scale/one-hot
  X_test  = transform(L001)      same frozen train statistics
  LogisticRegression.fit(X_train, y_train)
  p_raw[L001] = predict_proba(X_test)[:, 1]
```

The persisted champion is **not** this fold model. After all eight OOF passes, `pipeline.fit` runs on all 784 dies so `ml predict` has a single artifact. **Reported metrics still use the 784 OOF scores**, not the in-sample full-data scores.

---

## 13. All eight folds (visual)

```text
              L001  L002  L003  L004  L005  L006  L007  L008
Fold 1 TEST   TEST  TRAIN TRAIN TRAIN TRAIN TRAIN TRAIN TRAIN
Fold 2 TEST   TRAIN TEST  TRAIN TRAIN TRAIN TRAIN TRAIN TRAIN
Fold 3 TEST   TRAIN TRAIN TEST  TRAIN TRAIN TRAIN TRAIN TRAIN
Fold 4 TEST   TRAIN TRAIN TRAIN TEST  TRAIN TRAIN TRAIN TRAIN
Fold 5 TEST   TRAIN TRAIN TRAIN TRAIN TEST  TRAIN TRAIN TRAIN
Fold 6 TEST   TRAIN TRAIN TRAIN TRAIN TRAIN TEST  TRAIN TRAIN
Fold 7 TEST   TRAIN TRAIN TRAIN TRAIN TRAIN TRAIN TEST  TRAIN
Fold 8 TEST   TRAIN TRAIN TRAIN TRAIN TRAIN TRAIN TRAIN TEST
```

---

## 14. Calibration (actual nested behavior)

Method: **isotonic** (`sklearn.isotonic.IsotonicRegression`, clip out of bounds). Code: `ml/calibration.py`, wired in `ml/train.py`.

**OOF metrics (what `metadata.json` reports):**

```text
For each outer test lot T:
    raw OOF scores for the other lots  (already computed by models that held those lots out)
            │
            ▼
    IsotonicRegression.fit(oof_raw[other lots], y[other lots])
            │
            ▼
    p_cal[T] = isotonic.predict(oof_raw[T])
```

- The **classifier** that produced `oof_raw[T]` was trained **without** lot T.
- The **fold calibrator** is **not** fit on lot T’s labels.
- Second-order note (honest): `oof_raw` of the other lots were produced by models that **did** include T when those other lots were held out. Labels of T still do not fit T’s calibrator.

**Deployed calibrator** (pickle, used by `predict_dir`):

```text
ProbabilityCalibrator.fit(oof_raw_all, y_all)
```

That object is for **new** lots at predict time. It is **not** the vector `compute_metrics` uses.

If there are fewer than two classes or fewer than 10 scores, isotonic is skipped and raw probabilities are kept (`fitted=False`).

```text
Outer training lots
      │
      ├── FeatureBuilder + LogisticRegression  (no test lot)
      ▼
   raw P(fail) on unseen test lot
      │
      ├── isotonic fit on other lots' OOF raw + labels
      ▼
   calibrated P(fail) on unseen test lot
```

---

## 15. OOF predictions

```text
L001  →  model trained on L002–L008  →  98 scores
L002  →  model trained without L002  →  98 scores
…
L008  →  model trained on L001–L007  →  98 scores
                 │
                 ▼
        784 OOF raw scores
                 │
        fold-local isotonic
                 │
        784 OOF calibrated scores  ← metrics
```

They are out-of-fold because **the die’s lot was absent from that classifier’s training set**.

---

## 16. Final metrics — which scores?

`run_ml`:

```python
metrics = compute_metrics(y, trained.oof_cal if trained.calibrator.fitted else trained.oof_raw)
```

| Metric | Vector | Function |
|--------|--------|----------|
| ROC-AUC, PR-AUC | **calibrated** OOF probabilities | `sklearn` |
| Brier, log loss | **calibrated** OOF | `sklearn` |
| Precision, recall, F1, balanced accuracy | class = `(p_cal >= 0.5)` | `sklearn` |
| Capture @ top 10% / 20% | rank by **calibrated** OOF; fraction of all FAILs in that slice | `failure_capture_at_fraction` |
| Positive rate, n_samples, n_positives | labels only | 784 / 207 / 0.264 |

**Raw vs calibrated:**

- **Model comparison** inside `select_and_train` (`comparison[]` in `metrics.json`) uses **raw** OOF (`compute_metrics(y, oof)` before isotonic).
- **Champion `selected_metrics` / `metrics.json` top-level `metrics`** use **calibrated** OOF.

Do not mix those two tables. Capture-at-k is a **diagnostic concentration** statistic, not recovered FPY.

Champion calibrated OOF (from the artifact, not recomputed here):

| Metric | Value |
|--------|------:|
| ROC-AUC | 0.7153 |
| PR-AUC | 0.4377 |
| Brier | 0.1700 |
| log loss | 0.5282 |
| precision | 0.4902 |
| recall | 0.3623 |
| F1 | 0.4167 |
| capture @ 10% | 0.1981 |
| capture @ 20% | 0.3720 |

---

## 17. Phase 8B model comparison

`ml/benchmark.py` loads the **same** `MLDataset`, **same** `make_splits` folds, **same** target, and the **same** 16-name `ACTIVE_FEATURE_CONTRACT`. Logistic, Random Forest, HistGradientBoosting, and optional XGBoost/LightGBM therefore differ by **estimator**, not by split or features. That is why the bake-off is comparable. The benchmark **never writes** `artifacts/ml/yi_ml_v1`.

Training-time `MODEL_ORDER` in `ml/models.py` is only `(logistic, random_forest, hist_gbm)`. Extra GBDT libraries are evaluation-only.

---

## 18. Synthetic scenarios S01–S16

| | Training / scoring | Hidden ground truth |
|--|--------------------|---------------------|
| What the model sees | One agent-visible folder: `die_attempts.csv` (+ optional parametric) | **Nothing** |
| What `ml evaluate` sees after scoring | — | `evaluation/ml.py` joins `scenario_id` / expected signal **after** `run_ml_and_compose(..., persist=False)` |
| Champion | Trained on S02 folder `ds_0b5542c71e1a13e0` | S02 = planted EDGE; that string is not a feature |

S01–S16 are **separate directories**, not a `scenario_id` column. The model cannot use `true_cause` or `injected_effect`.

---

## 19. Leakage audit

| Check | Result | Evidence |
|-------|--------|----------|
| Lot leakage | **PASS** | `make_splits` rejects overlapping lot sets; all 8 folds overlap=`[]` |
| Wafer leakage | **NOT_APPLICABLE** | `wafer_id` is not a fold key; a held-out lot takes its wafers with it |
| Die leakage | **PASS** | One row per die; a die has one `lot_id` |
| Target leakage | **PASS** | `pass_fail` / disposition / sbin denied; y is not a FeatureBuilder column |
| Retest leakage | **PASS** | `is_retest` denied; y from first pass only |
| Future / sequence | **PASS** | `test_results` not joined into X |
| Scenario leakage | **PASS** | `scenario_id` forbidden; absent from agent-visible CSV |
| Hidden GT | **PASS** | `ml` package does not read hidden labels; fail-closed source check |
| Calibration | **PASS** | Fold isotonic not fit on the held-out lot’s **labels** |
| Preprocessing | **PASS** | `_cv_oof` fits `FeatureBuilder` + sklearn pipeline on `train_idx` only |

**Overall: PASS**

---

## 20. Data-flow diagram (implementation)

```text
Raw dataset  (die_attempts.csv, 784 rows)
         │
         ▼
Eligibility filter  (calculate_fpy)   → 784 eligible dies, 0 dropped
         │
         ▼
Die-level ML population
         │
         ├──────────────────┐
         ▼                  ▼
   FeatureBuilder        lot_id
   16 columns            LOLO grouping
         │                  │
         ▼                  ▼
   Feature matrix X      8 folds (LeaveOneGroupOut)
         │                  │
         └────────┬─────────┘
                  ▼
     Fold models (train lots only) → OOF raw P(fail)
                  │
                  ▼
     Fold-local isotonic → OOF calibrated P(fail)
                  │
                  ▼
     compute_metrics(y, oof_cal)
                  │
                  ▼
     SECONDARY_SUPPORT evidence
                  │
                  ▼
     Hypothesis compose (optional attach; no ML-only hypothesis)
                  │
                  ▼
     Full-data LogisticRegression + full-OOF isotonic
     saved as yi_ml_v1 for predict() only
```

---

## 21. What data reaches the final Logistic Regression pickle

Two different Logistic Regression objects exist conceptually:

1. **Eight fold models** — never persisted; produce OOF scores.
2. **Persisted champion** — `artifacts/ml/yi_ml_v1/model.pkl`:
   - `FeatureBuilder` statistics fit on **all 784** champion dies
   - `StandardScaler` / `OneHotEncoder` / `LogisticRegression(class_weight=balanced, max_iter=400, seed=7)` fit on **all 784**
   - Isotonic calibrator fit on **all 784 OOF raw** scores

`ml predict` uses (2). **Published metrics use (1) + fold-local isotonic.**

---

## 22. How to reprint this audit

```bash
python -m yield_improvement ml explain-data data/synthetic/agent_visible/ds_0b5542c71e1a13e0
```

Machine-readable copy: `evaluation/results/ml_data_split_audit.json`.

Neither command retrains or writes `artifacts/ml/yi_ml_v1/`.
