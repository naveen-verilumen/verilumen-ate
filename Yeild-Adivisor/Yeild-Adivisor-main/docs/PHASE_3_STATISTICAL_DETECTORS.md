# Phase 3 — Statistical yield-loss detectors

**Status:** Implemented. Evidence only. No ML, hypothesis ranking, recommendations, opportunity engine, dashboard, API, or production actions.

Companion: `docs/SYNTHETIC_DATA_DESIGN.md`. Calibration: `configs/calibration.yaml` (`status: TO_BE_CALIBRATED`).

```text
OBSERVABLE DATA
      ↓
STATISTICAL EVIDENCE  (DetectorResult)
      ↓
(not implemented) hypothesis ranking
```

Every detector sets `not_a_root_cause: true`. There is no `confirmed_root_cause` field.

---

## Architecture

```text
src/yield_improvement/detectors/
├── contract.py      DetectorResult / DetectorBundle
├── stats.py         two-proportion, Fisher, KS, Mann–Kendall, BH FDR
├── population.py    first-pass eligible DieView (via FPY engine)
├── spatial.py
├── equipment.py
├── temporal.py
├── temperature.py
├── parametric.py
├── near_limit.py
├── sequence.py
├── contact.py
├── lot.py
├── wafer.py
├── correlation.py
├── no_signal.py
└── runner.py        collect outputs, apply BH, do not rank

src/yield_improvement/evaluation/   # joins hidden truth AFTER detectors run
```

CLI (agent-visible directory only):

```text
python -m yield_improvement detect data/synthetic/agent_visible/<dataset_id>
```

---

## Common contract

| Field | Meaning |
|-------|---------|
| `status` | `SIGNAL` \| `NO_SIGNAL` \| `INSUFFICIENT_DATA` |
| `hypothesis_family` / `detail` | Candidate family, not a confirmed cause |
| `effect_size` + `effect_size_metric` | Rate difference, KS D, Jaccard, or Mann–Kendall τ |
| `p_value` | Raw |
| `adjusted_p_value` | Benjamini–Hochberg over all hypotheses in the run |
| `correction_method` | `benjamini_hochberg` |
| `confidence` | `INSUFFICIENT` \| `LOW` \| `MEDIUM` |
| `data_gaps` | Missing fields or below-n samples |

`INSUFFICIENT_DATA` covers both unavailable fields and sample sizes below `calibration.yaml` candidates. Missing X/Y, tester, probe card, sequence, limits, or parametric tables are **not invented**.

---

## Methods and effect sizes

| Detector | Method | Effect size | Missing data |
|----------|--------|-------------|--------------|
| spatial | Region (EDGE/CENTER/RING via radius quantiles) vs complement, two-proportion or Fisher; NN fail density supporting | fail-rate difference | no X/Y |
| equipment | tester_id vs rest | fail-rate difference | no tester_id |
| temporal | first vs last lot third + Mann–Kendall on lot rates; EWMA trace only | fail-rate difference / τ | < `n_min_temporal_lots` |
| temperature | temperature group vs rest; reports lot/tester mix | fail-rate difference | no temperature |
| parametric | KS lot vs complement + PSI | KS D (guard `ks_d_min`) | no parametric table |
| near_limit | δ-band vs far + measurement mass near limit | fail-rate difference / mass | no limits |
| sequence | P(later fail \| earlier fail) vs pass, `sequence_index` only | fail-rate difference | no sequence / stop-on-fail censoring |
| contact | probe_card_id vs rest | fail-rate difference | no probe_card_id |
| lot | lot vs rest | fail-rate difference | n < `n_min_lot` |
| wafer | wafer vs rest | fail-rate difference | sparse wafers skipped |
| correlation | 2×2 Fisher / Jaccard on **both-executed** tests | Jaccard | stop-on-fail / no pairs |
| no_signal | Rule: SIGNAL iff no other systematic SIGNAL | n/a | no eligible dies |

SIGNAL requires calibrated **p (then BH q)** and **effect size**. Large-n tiny shifts are not enough.

Isolation Forest remains `isolation_forest_enabled: false`.

---

## Thresholds

All numeric gates are `parameters.*.candidate` in `configs/calibration.yaml` with `status: TO_BE_CALIBRATED`. They are **not** factory SLAs. Including: `n_min_*`, `significance_level_alpha` (0.05), `fdr_q` (0.10), `min_effect_size_fpy_delta` (0.02), spatial quantiles, `near_limit_delta`, `ks_d_min`, `ewma_lambda`.

---

## Multiple testing

All hypothesis p-values in one `run_detectors` call are one family. Benjamini–Hochberg at `fdr_q` is applied in the runner. A detector that was SIGNAL on raw α is **demoted** to `NO_SIGNAL` if its winning hypothesis fails FDR + effect-size. The runner does not promote new signals after FDR.

---

## Evaluation

`yield_improvement.evaluation` reads `evaluation/ground_truth/synthetic/RUN_SUMMARY.json` **only after** `run_detectors_on_dir` on `data/synthetic/agent_visible/`. Detector modules do not import that package and do not contain `scenario_id` / `true_cause`.

Machine-readable table: `evaluation/results/detectors_phase3.json`.

S01 and S16 are negative controls. S15 checks spatial EDGE **and** temporal DRIFT independently.

---

## Assumptions and limitations

- First-pass eligible dies only (same FPY engine as Phase 1).
- Two-proportion z-test assumes approximate iid; spatial correlation violates that — Fisher used when expected cells < 5; still labeled weak iid.
- Lot order is chronological by earliest timestamp.
- Stop-on-fail writes later tests as `NOT_EXECUTED`, which censors sequence and co-fail pairs. S11 often returns `INSUFFICIENT_DATA`. That is correct given the visible table, not a reason to invent order from CSV row order.
- Lot/wafer detectors often fire when drift or a few bad lots exist; they report **association**, not a unique cause.
- Near-limit never emits a candidate limit. `safety_eligible_production` remains 0.
- No ranking among detectors in this phase.

---

## Recommended next phase

Hypothesis composition: rank competing `DetectorResult` packets with calibration, keep dual-cause hypotheses uncollapsed, still advisory, still no ATE writes.
