# Phase 10A — Node.js frontend

**Status:** Implemented as a presentation layer. Analytical engines, ML artifacts, and safety policy are unchanged.

The product UI is a **one-page React dashboard**. Streamlit is not used for this UI.

## UX objective

An engineer opens one dataset and can answer:

> Why is first-pass yield being lost, and what should I investigate next?

The UI never labels a hypothesis as a confirmed root cause, never treats opportunity as guaranteed recovered yield, and never authorizes production action.

## Frontend architecture

```text
frontend/
  src/
    main.tsx
    App.tsx
    pages/DashboardPage.tsx          one page
    components/                      header, KPIs, Pareto, evidence, hypotheses, ML, opportunity, investigation, quality, footer
    services/yieldImprovementApi.ts  typed fetch
    services/yieldImprovementViewModel.ts  presentation mapping only
    types/api.ts                     backend response types
    hooks/useDashboard.ts
    styles/index.css                 Tailwind
```

Data flow:

```text
Dataset
  → existing Python pipeline / persisted EngineeringReport
  → FastAPI read-only adapter (GET)
  → typed fetch
  → view-model (format / optional-field normalize)
  → React one-page
```

The frontend does **not** calculate FPY, Pareto, hypothesis scores, opportunity, statistical tests, ML inference, or model health.

## API integration

There was **no existing FastAPI app**. Phase 10A added a thin GET-only adapter:

| Method | Path | Source |
|--------|------|--------|
| GET | `/api/health` | liveness |
| GET | `/api/datasets` | agent-visible dataset dirs + persisted reports |
| GET | `/api/datasets/{id}/dashboard` | `EngineeringReport` + champion ML snapshot + optional health |
| GET | `/api/ml/active` | `artifacts/ml/yi_ml_v1` metadata/metrics + registry pointer |
| GET | `/api/datasets/{id}/health` | persisted `evaluation/monitoring/{id}_model_health.json` if present |

Python module: `src/yield_improvement/api/`

The dashboard payload **copies**:

- `EngineeringReport.to_public_dict()` (via `build_report_from_dir` or `reports/{id}_engineering_report.json`)
- champion `metrics.json` / `metadata.json` (no training, no overwrite)
- registry `active_version` / architecture / state
- persisted `ModelHealthReport` fields (`overall_status`, dimension status, recommendations)

If a field is missing, the UI shows `Unavailable`. It does not invent a substitute.

## View-model

`toDashboardViewModel` may:

- format rates as percent strings
- format counts with grouping separators
- map `logistic` → display label `Logistic Regression`
- derive **presentation status** from existing flags (`COMPLETE`, `NEEDS_MORE_DATA`, `INSUFFICIENT_DATA`, `ML_DEGRADED`, `NO_CONFIDENT_HYPOTHESIS`)
- flatten `investigation_plan[].steps` into a numbered list

It must not rank hypotheses, recompute Pareto, or score health.

## Component structure

One page, top to bottom:

1. Header — dataset, analysis status, timestamp
2. KPI summary — FPY, FPY loss, eligible dies
3. Leading investigation candidate (or no-signal copy)
4. PRIMARY_FAILURE Pareto + ML insight
5. Statistical evidence (details collapsed)
6. Hypothesis cards (`UNCONFIRMED`)
7. Opportunity (observed / upper bound / plausible)
8. Next investigation (Phase 6 steps only)
9. Data quality / notices (near-limit, sequence censoring)
10. Safety footer

## Backend dependencies

- Python 3.11+
- Optional extra: `pip install -e ".[api]"` (FastAPI + uvicorn)
- Existing reporting adapter (`build_report_from_dir`)
- Optional persisted reports under `reports/`
- Optional health JSON under `evaluation/monitoring/`
- Active model artifacts under `artifacts/ml/yi_ml_v1/` (read-only)

The adapter does not call `select_and_train`, `activate_candidate`, or monitoring `run_monitor`.

## Setup

From the repository root:

```bash
pip install -e ".[api]"
cd frontend
npm install
```

## Development commands

Terminal 1 — API:

```bash
python -m yield_improvement serve --host 127.0.0.1 --port 8000
```

Terminal 2 — UI (proxies `/api` to port 8000):

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`.

## Production build

```bash
cd frontend
npm run build
```

Output: `frontend/dist/`. Serve that static tree behind the FastAPI host, or any static file server, with `/api` reverse-proxied to `yield_improvement serve`.

## Tests

```bash
cd frontend
npm test
```

Python (includes the new GET-adapter tests; does not change Phase 1–9 analytical tests):

```bash
pytest
```

## Safety restrictions

The UI and API always present:

- production action: `FORBIDDEN`
- production authorized: `NO`
- safety-eligible production: `0`

There are no frontend controls to retrain, approve, activate, roll back, change limits, or write ATE/recipe/equipment settings.

## Scenario presentation

| Backend signal | UI |
|----------------|----|
| no hypotheses / `no_actionable_recommendation` | “No strong systematic signal was detected.” |
| `near_limit_notice` / `TEST.LIMIT_SENSITIVITY` | “Near-limit failure pattern detected.” Never increase/relax/change limit. |
| `sequence_censoring_notice` | shown as a data-quality notice |
| `SPATIAL.EDGE` and `PROCESS.DRIFT` | two cards; overlap is not a combined root cause |

## What this phase did not do

- No Streamlit changes to make Streamlit the product UI
- No analytical engine edits
- No ML retraining or activation
- No modification of `artifacts/ml/yi_ml_v1/`
- No other-agent invocation
