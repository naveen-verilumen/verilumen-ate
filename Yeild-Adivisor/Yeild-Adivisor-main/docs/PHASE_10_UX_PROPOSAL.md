# Phase 10 — UX / dashboard design proposal

**Status:** Design only. Not implemented. No production code, artifacts, or safety policy were changed in this phase.

**Active model (context only):** Logistic Regression / `yi_ml_v1` (unchanged).

This document proposes the **simplest useful engineer dashboard** for the Yield Improvement Agent. Numbers in wireframes are **placeholders**. Implementation must copy backend fields; it must not invent FPY, Pareto, scores, opportunity, or health.

---

## 1. UX objective

An engineer opens one dataset and, **without flipping through eight pages**, can answer:

1. What is first-pass yield?
2. Where is first-pass yield being lost?
3. Which statistical signals support that loss?
4. Which **unconfirmed** investigation hypotheses exist?
5. Does ML add secondary predictive support, and is the model healthy?
6. What opportunity is observed vs upper-bound vs plausible (and what must not be added)?
7. What should be investigated next?
8. What data is missing?
9. What production action is **not** authorized?

The agent remains **diagnostic and advisory**. The UI never implies a confirmed root cause, a guaranteed FPY gain, or a production change.

---

## 2. Target user

**Primary:** wafer-sort / yield engineer on a desktop or laptop, looking at one agent-visible dataset (lot window, synthetic holdout, or plant extract).

**Not:** executives, operators driving ATE, or a chatbot audience.

Job to be done:

> “Why am I losing first-pass yield, and what should I investigate next?”

---

## 3. User journey

```text
Open dataset (or load a persisted engineering report)
        ↓
See FPY, FPY loss, eligible dies, leading investigation candidate
        ↓
Scan one PRIMARY_FAILURE Pareto
        ↓
Skim statistical signals (summary)
        ↓
Read ranked UNCONFIRMED hypotheses
        ↓
Optionally expand ML / opportunity / health / gaps
        ↓
Follow Phase 6 investigation steps
        ↓
Leave with: what to check next, what is missing, what is forbidden
```

No login, no multi-app shell, no “ask the AI.” Dataset in → copy of existing analysis out.

---

## 4. Inspection findings (why the structure changes)

Already in the repo:

| Layer | Location | Role |
|-------|----------|------|
| Engineering report | `src/yield_improvement/reporting/` | Presentation contract for Phase 1–6 |
| Streamlit stub | `src/yield_improvement/dashboard/` | Consumes `EngineeringReport` only |
| CLI | `python -m yield_improvement report` / `dashboard` | Builds or displays that report |
| ML | `MLResult`, `artifacts/ml/yi_ml_v1/` | Predictive, `SECONDARY_SUPPORT` |
| Monitoring | `ModelHealthReport` | Advisory health; never retrains |
| Lifecycle | `artifacts/ml/registry/` | `active_version` pointer |

The **current Streamlit app is not the right UX to ship**. It is eight sidebar pages, repeats a loud safety banner on every page, dumps p-values in the default evidence table, omits ML and model health, and does not put “what to investigate next” on the first screen.

Keep:

- Streamlit (already optional, local, no new frontend stack)
- `EngineeringReport` as the Phase 1–6 source of truth
- Copy-only chart helpers in `dashboard/charts.py`

Change (next implementation phase, not this document):

- One scrolling page instead of eight pages
- Safety as a compact footer, not a red banner on every section
- Attach ML + health + registry via a **thin view-model**, without recalculating engines
- Summary → details expanders

That is a **redesign of the presentation**, not a redesign of FPY, detectors, hypotheses, opportunity, validation, ML, or lifecycle.

---

## 5. Page structure (recommended)

**One page**, optional in-page jump links: Overview · Loss · Evidence · Hypotheses · Investigate · More.

| Zone | On first paint? | Purpose |
|------|-----------------|--------|
| Header | yes | Dataset id, presentation status |
| Top summary | yes | FPY, FPY loss, eligible dies, leading investigation candidate |
| Where is yield lost? | yes | One PRIMARY_FAILURE Pareto |
| Evidence | yes (summary rows) | Statistical signals; details collapsed |
| Hypotheses | yes | Ranked UNCONFIRMED cards |
| Next investigation | yes | Phase 6 `validation_steps` only |
| ML insight | compact | Role, health, capture@10/20; metrics collapsed |
| Opportunity | compact | Observed / upper bound / plausible / overlap |
| Data quality | compact | Required / recommended / detector-specific gaps |
| Safety / authorization | footer | FORBIDDEN / not authorized / 0 |

**Dropped vs the user’s first sketch:** a separate “Validation” chapter. Phase 6 recommendations already sit on each hypothesis (`validation_recommendation`) and in `investigation_plan`. Splitting them out again duplicates the story.

**Dropped vs the current Streamlit stub:** dedicated FPY Loss, Validation, and Traceability pages. Traceability stays under an expander. ANY_FAIL Pareto stays under an expander so it is never mixed with PRIMARY_FAILURE.

---

## 6. ASCII wireframe

Placeholder numbers only. Implementation must substitute copied backend values or `Unavailable`.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ YIELD IMPROVEMENT AGENT            Dataset: <dataset_id>                 │
│ Advisory analysis · Status: COMPLETE | NEEDS_MORE_DATA | …               │
│ Active model: yi_ml_v1  (Logistic Regression)                            │
├──────────────────────────────────────────────────────────────────────────┤
│  FPY              FPY LOSS           ELIGIBLE DIES                       │
│  <fpy>            <fpy_loss>         <eligible_die_count>                │
│                                                                          │
│  Leading investigation candidate                                         │
│  <family.detail> · UNCONFIRMED · <evidence_tier>                         │
│  <hypothesis.statement>                                                  │
│  (Not a confirmed root cause.)                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ WHERE IS YIELD LOST?  (PRIMARY_FAILURE only)                             │
│                                                                          │
│  <failure_key>     ████████████  <share_of_fails> of fails               │
│                    <n_dies> dies · <percentage_of_eligible> of eligible  │
│  …                                                                       │
│  [expander] ANY_FAIL Pareto (not combined with PRIMARY_FAILURE)          │
├──────────────────────────────────────────────────────────────────────────┤
│ STATISTICAL SIGNALS                                                      │
│                                                                          │
│  Signal            Population     Effect              Status             │
│  <family.detail>   <detector>     <effect_size>       SIGNAL|…           │
│  …                                                                       │
│  [expander per row] method, n, p, adjusted p, gaps                       │
├──────────────────────────────────────────────────────────────────────────┤
│ INVESTIGATION HYPOTHESES  (status always UNCONFIRMED)                    │
│                                                                          │
│  ①  <statement>                                                          │
│      Evidence tier: STRONG_EVIDENCE   Score: <evidence_score> PRELIMINARY│
│      Affected: <affected_population>                                     │
│      Supported by: <supporting_detectors>  [+ ML if attached]            │
│      Conflicts: <conflicting_detectors or none>                          │
│      Validation: <validation_recommendation>                             │
│      [expander] coverage, gaps, limitations, steps                       │
│                                                                          │
│  ②  …                                                                    │
├──────────────────────────────────────────────────────────────────────────┤
│ NEXT INVESTIGATION                                                       │
│                                                                          │
│  1. <validation_steps[0]>                                                │
│  2. <validation_steps[1]>                                                │
│  …                                                                       │
│  If no_confident_hypothesis:                                             │
│  “No strong systematic signal was detected. Additional data or           │
│   investigation is required.”                                            │
├──────────────────────────────────────────────────────────────────────────┤
│ ML INSIGHT                                                               │
│  Model: logistic · Version: yi_ml_v1 · Role: SECONDARY_SUPPORT           │
│  Health: <overall_status>                                                │
│  Failure concentration: top-10% <capture10> · top-20% <capture20>        │
│  Top predictive features: <feature_importance[:k]>  (association only)   │
│  [expander] ROC-AUC, PR-AUC, Brier, calibration note, split_strategy     │
│  [expander] health dimensions: feature / prediction / target /           │
│             calibration / performance / data_quality                     │
├──────────────────────────────────────────────────────────────────────────┤
│ OPPORTUNITY  (analytical; not guaranteed recoverable yield)              │
│  Observed loss (overall)     <summary.observed_loss_rate>                │
│  Union upper bound           <overlap.union_upper_bound_rate>            │
│  Sum of individuals          <sum_of_individual_upper_bounds_rate>       │
│  Plausible                   Unavailable if plausible_unavailable        │
│  Do not add overlapping slices. Safety-eligible production: 0            │
├──────────────────────────────────────────────────────────────────────────┤
│ DATA QUALITY                                                             │
│  Required gaps: <data_gaps.required or none recorded>                    │
│  Recommended / detector-specific: collapsed                              │
├──────────────────────────────────────────────────────────────────────────┤
│ AUTHORIZATION                                                            │
│  production_action: FORBIDDEN · production_authorized: NO                │
│  safety_eligible_production: 0 · invoked_agents: []                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Section-by-section explanation

### Header

Show `dataset_id` and a **presentation status** derived only from existing flags (see §10). Show `active_model_version` from the lifecycle registry when present, else `yi_ml_v1` from ML config/artifact. Do not infer a champion from metrics.

### Top summary

Four facts, then one sentence:

| UI label | Source |
|----------|--------|
| FPY | `EngineeringReport.fpy_summary.fpy` (rate → percent display) |
| FPY loss | `fpy_summary.fpy_loss` |
| Eligible dies | `fpy_summary.eligible_die_count` |
| Leading investigation candidate | Rank-1 `hypotheses[]` → `family.detail`, `statement`, `evidence_tier`, `status=UNCONFIRMED` |

If `no_confident_hypothesis` or `no_actionable_recommendation`, the fourth cell is **not** a fake top hypothesis. It shows the no-signal copy in §12.

“Primary failure category” on the summary is the **top PRIMARY_FAILURE Pareto row** (`failure_key` / `taxonomy_code`), labeled as observed loss attribution — not as a cause.

### Where is yield lost?

One horizontal bar list from `loss_summary.primary_failure`:

- label: `failure_key` (show `taxonomy_code` if present)
- dies: `affected_die_count`
- share of fails: `share_of_fails`
- share of eligible (FPY-loss contribution): `percentage_of_eligible`

Click/expand a bar → hypotheses whose `family.detail` or supporting detectors match that taxonomy, plus the detector evidence row. No independent join math: only display-time filtering of already-linked report objects.

ANY_FAIL (`loss_summary.any_fail`) is an expander with the existing caption that modes are never combined.

### Statistical evidence

Default columns (no p-values until expand):

| UI | Field |
|----|--------|
| Signal | `family`.`detail` if present, else `detector` |
| Detector | `detector` |
| Status | `status` (`SIGNAL` / `NO_SIGNAL` / `INSUFFICIENT_DATA`) |
| Effect | `effect_size` + `effect_size_metric` |
| Coverage proxy | `sample_size` (do not invent a % if coverage is absent on the detector row) |

Hypothesis-level `data_coverage` is shown on hypothesis cards, not invented for detectors.

Expanded: `method`, `p_value`, `adjusted_p_value`, `data_gaps`. Ordinal `confidence` exists on `DetectorResult` but is **not** currently copied onto `ReportEvidenceFinding`. Do not display it until the view-model copies that existing detector field. Prefer not adding it in v1 of this dashboard.

### Hypotheses

One card per `ReportHypothesis`, ordered by `rank`.

Always show:

- `statement` (associative: “Yield loss is associated with …”)
- `status` = `UNCONFIRMED`
- `evidence_tier`, `evidence_score` with caption that the score is PRELIMINARY and not P(cause)
- `affected_population`
- `supporting_detectors` / `conflicting_detectors`
- ML attachment: if a hypothesis `evidence` item (from compose) has `source=ml`, show “ML predictive evidence (SECONDARY_SUPPORT)” — copy, do not rescore
- `validation_recommendation` (`INVESTIGATE` / `REVIEW` / `MONITOR` / `NEEDS_MORE_DATA` / `REJECTED`)
- first investigation step

Never label `HIGH` confidence or `STRONG_EVIDENCE` as a root cause. `not_a_root_cause` is always true.

S15: `SPATIAL.EDGE` and `PROCESS.DRIFT` remain two cards. Overlap counts belong in Opportunity, not a merged “EDGE+DRIFT root cause.”

S09: use the identity statement “Yield loss is associated with measurements concentrating near a test limit” plus `near_limit_notice`. Forbidden: increase/relax/change limit.

### Next investigation

Copy `investigation_plan` in rank order. Each item’s `steps` are Phase 6 `validation_steps` (engineering checks). If the plan is empty (`no_actionable_recommendation`), show the no-signal block. Do not generate extra bullets in the UI.

### ML insight

Purpose: “Is ML adding useful secondary evidence?” not “how fancy is the model?”

Default:

- architecture/name: `MLResult.model_name` (logistic) / display “Logistic Regression”
- version: `MLResult.model_version` or registry `active_version`
- role: `SECONDARY_SUPPORT` / `independence: false`
- health: `ModelHealthReport.overall_status` or `Unavailable` if no health report
- capture: `metrics.failure_capture_at_top_10_percent` and `_20_percent` (diagnostic concentration, not recovered yield)
- top features: `feature_importance` names + “predictive association only”

Collapsed: ROC-AUC, PR-AUC, Brier, calibration `brier_raw` / `brier_calibrated`, `split_strategy`.

Health expander: dimension `status` for feature, prediction, target, calibration, performance, data quality. Recommendations stay in `{CONTINUE_MONITORING, REVIEW_MODEL, COLLECT_MORE_DATA, INVESTIGATE_DRIFT, CONSIDER_RETRAINING}`. `NEEDS_RETRAINING` does not offer a one-click retrain.

If health is `DEGRADED` / `NEEDS_RETRAINING` / `INSUFFICIENT_DATA`, keep statistical hypotheses visible and mark ML as reduced trust (already `ML_FLAGGED` on compose).

### Opportunity

Overall strip from `OpportunityBundle.summary` via report overlap/opportunities:

- Observed loss: `fpy_summary.fpy_loss` (same measurement as FPY loss; do not invent a second overall)
- Union upper bound: `overlap.union_upper_bound_rate`
- Sum of individuals: `overlap.sum_of_individual_upper_bounds_rate` with `sum_exceeds_observed`
- Plausible: per-item `plausible_unavailable` → “Not estimable”; never treat as promised gain

Caption (existing text): opportunity is analytical, not guaranteed recoverable yield; overlapping populations must not be summed; safety-eligible production is 0.

### Data quality

`data_gaps.required` / `recommended` / `detector_specific`. Missing stays missing. Sequence censoring uses `sequence_censoring_notice`. FPY policy notes (`fpy_summary.policy_notes`) stay in an expander (retest ≠ first-pass, rework excluded, etc.).

### Authorization footer

Copy only:

- `production_action = FORBIDDEN`
- `production_authorized = false`
- `safety_eligible_production_count = 0`
- `safety_eligible_production_rate = 0.0`
- `invoked_agents = []`

Visually secondary (caption / muted bar). Not `st.error` on every section.

---

## 8. Data source for every displayed metric

| UI element | Exact source | If missing |
|------------|--------------|------------|
| Dataset id | `EngineeringReport.dataset_id` | do not open |
| FPY | `fpy_summary.fpy` | `Unavailable` / INSUFFICIENT_DATA |
| FPY loss | `fpy_summary.fpy_loss` | `Unavailable` |
| Eligible / pass / fail / excluded | `fpy_summary.*_count` | show 0 only if the report says 0 |
| Pareto bars | `loss_summary.primary_failure[]` | note `primary_unavailable_note` |
| ANY_FAIL | `loss_summary.any_fail[]` | hide expander |
| Detector rows | `evidence_findings[]` | empty list |
| Hypothesis cards | `hypotheses[]` | no-signal copy |
| Evidence tier / score | `evidence_tier`, `evidence_score`, `score_status` | n/a if no hyp |
| Supporting / conflicting | `supporting_detectors`, `conflicting_detectors` | “none” |
| Validation rec | `validation_recommendation` | `Unavailable` |
| Investigation steps | `investigation_plan[].steps` | no-signal copy |
| Observed/upper/plausible | `opportunities[]` + `overlap` | `Not estimable` / Unavailable |
| Near-limit notice | `near_limit_notice` | omit |
| Sequence notice | `sequence_censoring_notice` | omit |
| Data gaps | `data_gaps` | “none recorded” |
| Safety | report production_* fields | still FORBIDDEN |
| ML name/version/metrics | `MLResult` or `artifacts/ml/yi_ml_v1/metrics.json` + `metadata.json` | ML section `Unavailable` |
| Feature ranks | `MLResult.feature_importance` | omit list |
| Capture@k | `MLMetrics.failure_capture_at_top_*` | Unavailable |
| Model health | `ModelHealthReport.overall_status` | Unavailable (do not infer HEALTHY) |
| Active version | registry `active_version` | `yi_ml_v1` from artifact metadata |

Display formatting only: multiply rates by 100 for `%` strings (`dashboard/formatting.py` already does this).

---

## 9. Backend → UI map

```text
die_attempts.csv (+ optional test_results, parametric)
        ↓  existing engines (unchanged)
FpyResult, DetectorBundle, HypothesisBundle,
OpportunityBundle, ValidationBundle
        ↓  reporting.adapter.build_report  (copy)
EngineeringReport  [persist via `report` CLI]
        ↓
optional: MLResult (persist=False or artifact metrics)
optional: ModelHealthReport (monitor CLI JSON)
optional: registry.json active_version
        ↓  DashboardViewModel (NEW, thin; mapping only)
Streamlit one-page
```

**Do not** have the UI call `calculate_fpy`, detectors, `compose`, `estimate_opportunities`, or `select_and_train` except through the existing adapter used to *build* the report offline. Preferred runtime: load persisted `*_engineering_report.json` plus optional ML/health JSON.

If ML/health files are absent, show those sections as Unavailable. Do not run a silent training pass from the dashboard.

---

## 10. Dashboard states

Presentation status is a **view mapping** of flags already on the report / health object:

| State | When (existing flags) | First-screen behavior |
|-------|----------------------|------------------------|
| **COMPLETE** | `fpy` present; not `no_actionable_recommendation`; no required gaps forcing fail-closed | Full page |
| **NEEDS_MORE_DATA** | any `validation_recommendation == NEEDS_MORE_DATA` or `data_gaps.required` nonempty, but FPY still computed | Show FPY + gaps; hypotheses still UNCONFIRMED |
| **INSUFFICIENT_DATA** | `fpy_summary.fpy is None` or FPY pipeline `INVALID` | Do not draw a fake Pareto; say insufficient |
| **ML_DEGRADED** | health `DEGRADED` \| `NEEDS_RETRAINING` \| `INSUFFICIENT_DATA` | Stats/hypotheses unchanged; ML marked reduced |
| **NO_CONFIDENT_HYPOTHESIS** | `hypotheses.no_confident_hypothesis` or `no_actionable_recommendation` | No fake #1 hypothesis; explicit no-signal copy |

These labels are UI-only. They must not be written back into engines or the registry.

---

## 11. Safety presentation

- Footer, always visible after scroll, not a modal and not a red wall.
- Exact backend enumerations: `FORBIDDEN`, `false`, `0`, `0.0`.
- No control widgets (no “apply,” “deploy,” “retrain now,” “activate model”).
- Lifecycle stays CLI (`retrain` / `model approve|activate`). The dashboard may *display* `ACTIVE` version and health; it must not change them.

---

## 12. Scenario handling (S01 / S09 / S11 / S15 / S16)

The UI does not know `scenario_id` (hidden GT). It reacts to **outputs** those scenarios produce.

| Scenario (eval only) | What the UI will show from outputs |
|----------------------|-------------------------------------|
| **S01 / S16** | `no_confident_hypothesis` / `no_actionable_notice`. Copy: “No strong systematic signal was detected.” List detector statuses (mostly `NO_SIGNAL` / `INSUFFICIENT_DATA`), available FPY, remaining gaps. No invented hypothesis. |
| **S09** | Hypothesis `TEST.LIMIT_SENSITIVITY`, `near_limit_notice`. Never “increase/relax/change limit.” |
| **S11** | `TEST.SEQUENCE` if composed; `sequence_censoring_notice` when present. No later-test features. |
| **S15** | Separate cards `SPATIAL.EDGE` and `PROCESS.DRIFT`. Overlap shown as overlapping populations, not `EDGE_AND_DRIFT`. |

---

## 13. What should NOT be displayed

- “Root cause,” “confirmed cause,” “the root cause is”
- “You will gain X%,” “guaranteed improvement,” “recovered yield,” “FPY can improve by”
- Limit-change verbs (`increase limit`, `SET_LIMIT`, candidate/new limit)
- ATE / recipe / equipment write actions
- `APPROVED_FOR_PRODUCTION`
- A single opaque “model score” or “health score”
- Champion chosen by highest ROC-AUC
- Combined EDGE+DRIFT causal hypothesis
- Default-visible p-value / FDR tables (keep behind expand)
- Default-visible full die-id lists (`affected_die_ids` can be huge)
- Chatbot / generative investigation text
- One-click retrain, approve, or activate
- React/Next marketing chrome, 3D charts, animated gauges

---

## 14. Recommended technology

**Keep Streamlit** (`pyproject.toml` extra `dashboard`, existing `python -m yield_improvement dashboard`).

Why:

- Already wired; optional dependency; local `streamlit run`
- Adequate for one Pareto, expanders, and tables
- Does not require a JS build or a new security surface
- Matches “simplest technology that is interactive”

Why not React/Next/etc.: appearance only; no existing SPA; would duplicate the report adapter.

Streamlit constraints (accept them): limited visual polish, default widgets look utilitarian — that fits an engineering tool. Implement custom HTML/CSS only if the one-page layout cannot be achieved with `st.metric`, expanders, and a simple bar list.

---

## 15. Visual design (for the later implementation)

- Light background, system/sans typography, tight vertical rhythm
- One Pareto; no extra “FPY vs loss” vanity chart
- Semantic color **plus text**: green HEALTHY / SIGNAL, amber MONITOR / WARNING / NEEDS_MORE_DATA, red DEGRADED / FAIL / REJECTED, gray Unavailable
- Cards for hypotheses only; not a card for every KPI
- Desktop/laptop first; no mobile-first nav

---

## 16. Implementation plan (next phase — not this task)

1. Add a **DashboardViewModel** that reads `EngineeringReport` + optional ML/health/registry JSON and exposes the fields in §8. No formulas.
2. Replace eight-page `dashboard/app.py` with one-page render matching this wireframe.
3. Move safety to the footer; keep phrase validators.
4. Pareto from `primary_failure_pareto_rows` only on the main canvas.
5. Evidence summary table; details in expanders.
6. Hypothesis cards using `statement`, `UNCONFIRMED`, tiers, detectors, validation rec.
7. Investigation block from `investigation_plan`.
8. ML/health sections with Unavailable fallback.
9. State banners from §10, including S01/S16 copy.
10. Tests: presentation-only (no new FPY numbers); forbidden phrases; S09/S15/S16; dashboard does not call `select_and_train` / `activate_candidate`.
11. Do not touch `artifacts/ml/yi_ml_v1/`.

---

## 17. Final review question

**What is the simplest dashboard that makes this agent genuinely useful to an engineer?**

A **single page** that copies FPY and FPY loss, one primary-failure Pareto, ranked **UNCONFIRMED** hypotheses with their Phase 6 next steps, and a quiet “ML is secondary / health is X / production is forbidden” strip — and that **refuses to invent a cause** when the backend says there is no confident hypothesis.

That is enough. More pages, more charts, and a chatbot would hide the answer.

### Recommendation

**REDESIGN** the existing Streamlit presentation (one page, ML+health attached, quieter safety), then **IMPLEMENT** that redesign in a later phase.

**Do not implement the current eight-page stub as the product UI.**  
**Do not implement this redesign in Phase 10.**
