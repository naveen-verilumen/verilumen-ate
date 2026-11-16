# Yield Improvement Agent — Technical Discovery

**Project:** Yield Improvement Agent  
**Status:** Discovery / research only — no production implementation  
**Audience:** Semiconductor test and yield engineers, plus engineers who will later implement the agent  
**Date:** 2026-09-22  

---

## How to read this document

| Label | Meaning |
|-------|---------|
| **FACT** | Established semiconductor manufacturing / test practice |
| **ASSUMPTION** | Project-specific choice that is not yet confirmed by data, fab process, or product requirements |
| **OPEN** | Must be answered before implementation |
| **ILLUSTRATIVE** | Example numbers for format only — not measured production data |

This document does **not** contain production code, fabricated fab datasets, or claimed production yield numbers.

**Core principle:**

```text
Observe → Quantify yield loss → Hypothesize cause → Estimate opportunity
    → Recommend investigation or specialist-agent handoff
    → Engineer validates → Human authorizes any production action
```

The agent is **advisory**. A prediction is never a confirmed root cause. A recommendation is never a production change.

---

## 1. Executive Summary

### Business objective

Improve **First Pass Yield (FPY)** so that more dies pass manufacturing/test the first time they are tested. That should:

- reduce unnecessary yield loss (good or recoverable material discarded or delayed)
- increase saleable devices
- improve manufacturing and test efficiency (less retest, less debug, less scrap)
- increase potential revenue

The agent does this by analyzing semiconductor manufacturing and test data to answer three engineer questions:

1. **Where** are we losing first-pass yield?
2. **Why** might we be losing it (hypothesis with evidence, not a verdict)?
3. **What** should engineering investigate next, including expected FPY opportunity, confidence, risk, and required validation?

### What this agent is

A **diagnostic yield-orchestration agent**. It sits above specialized test-optimization agents and produces an evidence-backed FPY loss diagnosis plus ranked, safety-gated recommendations.

It is **not**:

- an autonomous process-control or ATE-control system
- a Dynamic Test Limit engine
- a false-failure classifier
- a retest scheduler
- a quality/escape gate

Those capabilities already belong, or should belong, to sibling agents. This agent should **detect, quantify, explain, and route** — not duplicate them.

### What success looks like

An engineer can open a lot, wafer, or time window and see:

- current FPY vs final yield vs test yield
- a Pareto of first-pass loss by failure mode / test / location / equipment
- spatial and temporal patterns
- ranked hypotheses with evidence
- estimated recoverable FPY **split by opportunity type** (true process vs test-induced vs retest-recoverable vs limit-sensitive)
- explicit **do-not-touch** items (escapes, reliability, unvalidated limit moves)
- a validation checklist before any production action

### Safety one-liner

Safety always outranks yield. Simulated or estimated FPY gain is not production yield. The agent must never write test limits, ATE configurations, recipes, or equipment settings.

---

## 2. Problem Definition

### 2.1 The manufacturing problem

Semiconductor devices are fabricated as many dies on a wafer, then probed, assembled, and tested again. Not every die that starts the line becomes a saleable unit. Loss happens in process, probe, assembly, and final test.

From a **business** perspective, first-pass losses are expensive even when material is later recovered:

- tester time and operator time
- cycle-time delay
- risk of overkill (good die failed)
- risk of underkill if recovery policies are too aggressive
- engineering debug load
- lost or delayed revenue

From a **yield-engineering** perspective, the hard problem is not computing a yield number. It is **separating** losses that are:

| Loss class | Meaning | Typical action |
|------------|---------|----------------|
| True process / device defect | Die is actually bad | Process, equipment, or design fix |
| Systematic process signature | Clustered / patterned real defects | Tool, recipe, or excursion response |
| Test-induced overkill | Good or marginal die failed the test setup | Test program, contact, limit, or condition review |
| Measurement / contact artifact | Fail is not a device fail | Probe, handler, calibration |
| Recoverable on retest | Often contact, thermal, or noise | Retest policy (specialist agent) |
| Limit-boundary sensitivity | Fail near a guardband | DTL / spec review (specialist agent) |
| Unknown / mixed | Insufficient evidence | Collect data; do not act |

**ASSUMPTION:** The initial product scope is **wafer sort / first-pass test FPY** (circuit probe), with optional later extension to final test. Full fab line yield (litho/etch/CMP scrap) is in scope only when process/equipment data is actually available. Missing data must be labeled unavailable, never invented.

### 2.2 Why an agent (and why not a dashboard of charts)

Yield engineers already use wafer maps, Pareto charts, SPC, and lot genealogy. The gap this agent should close is **multi-hop diagnosis with provenance**:

```text
Failure mode → failing test/parameter → wafer location → lot
    → equipment → process condition → environment → history
```

A human can do this, but it is slow, inconsistent across lots, and easy to stop at the first Pareto bar. The agent should:

- compute deterministic KPIs the same way every time
- search systematically across dimensions
- attach confidence and missing-data flags
- refuse to recommend production changes
- hand specialized problems to specialist agents

ML is useful for pattern detection and ranking of hypotheses. It is **not** required to compute FPY, Pareto contribution, or SPC alarms.

### 2.3 Advisory constraint (non-negotiable)

The agent must **not** automatically modify:

- production test limits
- ATE configurations or test programs
- process parameters
- manufacturing recipes
- production equipment settings

Any recommendation that could affect production must pass **engineering validation** and a **human safety check**.

---

## 3. Semiconductor Yield Concepts

### 3.1 What semiconductor yield means

**FACT:** In semiconductor manufacturing, **yield** is the fraction of units that meet specification at a defined point in the line, relative to the units that entered that point (or a defined denominator such as candidate dies on a wafer).

Yield is **stage-specific**. A single number named “yield” is ambiguous unless the insertion, denominator, and whether retest/rework are included are stated.

Common stages (**FACT**, terminology varies by company):

| Stage | Typical meaning |
|-------|-----------------|
| Line / wafer-process yield | Wafers or area surviving fab processing |
| Die / probe / sort yield | Dies passing wafer test |
| Assembly / packaging yield | Units surviving assembly |
| Final-test yield | Packaged units passing FT |
| Overall / shipped yield | Saleable units vs started units (product of stages, with defined scrap rules) |

Yield models used in process engineering (Poisson, Murphy, Seeds, negative binomial) describe **how random defect density maps to die yield**. They are useful background; they are **not** the FPY diagnostic the agent must compute from test data.

### 3.2 First Pass Yield (FPY)

**FACT (general manufacturing):** First Pass Yield is the fraction of units that complete a process or test **correctly on the first attempt**, with no rework, retest, or repair.

**FACT (semiconductor test usage):** At a test insertion, FPY is usually:

\[
\mathrm{FPY} = \frac{N_{\text{pass on first test}}}{N_{\text{first-tested}}}
\]

Notes that must be explicit in code and reports:

- Denominator is **first insertions**, not all test events.
- Retest-pass units are **not** first-pass passes.
- Aborts, no-contact, and continuity fails need a documented inclusion rule (**OPEN**).
- Multi-insertion flows (WS then FT) have **per-insertion FPY** and can have an end-to-end first-pass metric. Do not mix them.

**ASSUMPTION for this project:** Primary KPI is **wafer-sort FPY** unless a later requirement names another insertion.

### 3.3 FPY vs final yield vs test yield vs overall yield

These are different numbers. The agent must compute and display them separately.

| Metric | Typical definition | Includes retest? | What it answers |
|--------|--------------------|------------------|-----------------|
| **First Pass Yield (FPY)** | First-test passes / first-tested units | No | How clean is the first attempt? |
| **Test yield** | Passes / tested at a named insertion, after that insertion’s local rules | Insertion-specific; often after local retest | How did this test step perform? |
| **Final yield** (at an insertion) | Final disposition good / units in the population | Yes, after allowed retest/repair | How much material was ultimately good here? |
| **Overall / line yield** | Saleable units / started units across stages | Per stage rules | End-to-end manufacturing efficiency |

**ILLUSTRATIVE:**

```text
1000 dies first-tested
  912 pass first attempt          → FPY = 91.2%
  48 fail, then pass on retest    → retest recovery = 4.8% of population
  40 remain fail                  → final yield = 96.0%
```

FPY = 91.2% and final yield = 96.0% can both be true. Improving FPY is not the same as improving final yield. Chasing FPY by loosening quality can raise escapes. Chasing final yield by unlimited retest can hide a contact or thermal problem.

### 3.4 What constitutes yield loss

**Yield loss** is the complement of the chosen yield metric, for a defined population.

At first pass:

\[
\mathrm{FPY\ loss} = 1 - \mathrm{FPY} = \frac{N_{\text{first-test fail}}}{N_{\text{first-tested}}}
\]

Loss can be further partitioned:

| Partition | Meaning |
|-----------|---------|
| By bin / failure code | Which fail bin captured the die |
| By first-failing test | Which test stopped the die (if stop-on-fail) |
| By all failing tests | Co-failing tests (if continue-on-fail or datalog allows) |
| Recoverable vs residual | Retest-pass vs still-fail |
| Spatial | Edge, center, cluster, scratch, ring |
| Temporal | Lot, wafer, shift, time |
| Equipment | Tester, prober, handler, probe card, process tool |
| Parametric vs functional | Continuum measurements vs pattern/logic fail |

**Unnecessary yield loss** (business target) is loss that is **not required to protect quality**. Examples: false fails, contact fails, overly tight guardbands, redundant failing tests that do not add defect coverage. True defective dies are **necessary** yield loss from a quality standpoint; they are still worth diagnosing if a process fix can prevent them.

### 3.5 Failures that contribute to yield loss

**FACT:** Common first-pass fail classes:

- **Continuity / opens / shorts** — often probe, pad, or gross defect
- **Parametric** — measurement outside limit (Idd, Vmin, resistance, timing, leakage)
- **Functional / scan / BIST / memory** — pattern mismatch, not a scalar limit
- **IDDQ / delta-IDDQ** — quiescent current
- **Speed / timing / shmoo** — fails at frequency/voltage corner
- **Thermal / hot** — fails only at temperature
- **Bin hardware vs software** — equipment vs program classification
- **Mechanical / no-contact / abort** — often not a device defect

Each class can be **true**, **false**, or **ambiguous** until evidence is attached.

### 3.6 Random vs systematic yield loss

**FACT:**

| | Random | Systematic |
|---|--------|------------|
| Spatial | Scattered, little clustering beyond Poisson | Clusters, rings, edge, stripes, scratches, repeating shot maps |
| Cause | Particles, occasional defects | Process excursion, tool, design, mask, probe card, test condition |
| Model | Defect density / Poisson-like | Signature analysis, overlays, equipment genealogy |
| Actionability | Harder to kill with a single fix; reduce D0 | Often high leverage if signature is real |
| Agent role | Quantify baseline random floor | Detect, localize, and hypothesize |

The agent should estimate a **random floor** vs **systematic excess**. Improving FPY mainly means attacking systematic excess and test-induced overkill, not pretending random defects can be “ML-optimized away.”

### 3.7 What “yield improvement” means here

In this project, yield improvement means:

1. **Diagnose** first-pass loss composition.
2. **Identify actionable opportunities** that increase FPY without increasing escapes.
3. **Estimate impact** (dies, %, rough revenue proxy if ASP is provided).
4. **Recommend investigations or specialist-agent analyses**.
5. **Leave production control to humans.**

It does **not** mean “maximize pass rate at any cost.”

### 3.8 Where AI/ML can realistically help

| Problem | Better first method | ML useful? |
|---------|---------------------|------------|
| Compute FPY, Pareto, bin rates | Deterministic counts | No |
| Lot/wafer comparison | Statistics / hypothesis tests | Rarely |
| SPC / drift | Control charts, CUSUM, change-point | Optional anomaly models later |
| Wafer spatial signatures | Spatial stats, clustering | Yes for signature classification |
| Multivariate parametric structure | PCA, correlation, robust z | Yes, interpretable first |
| Ranking competing hypotheses | Rules + evidence scores; trees | Yes if explainable |
| Root-cause **confirmation** | Engineering experiment | **Never** “the model confirmed it” |
| Limit changes | DTL agent + safety catalog | Do not reinvent |
| False fail vs true fail | FFR agent + retest evidence | Delegate |
| Escape risk of a looser policy | Escape-prevention agent | Delegate |

---

## 4. Yield Loss Sources

For each source: how it causes loss, what data reveals it, whether it is potentially actionable, and what analysis can detect it.

**Actionable** here means “engineering can investigate and possibly fix,” not “the agent may apply a fix.”

| Source | How it causes FPY loss | Revealing data | Actionable? | Detection approach |
|--------|------------------------|----------------|-------------|--------------------|
| **Wafer / process defects** | Real defects kill dies (particles, pattern defects, films) | Wafer maps, inline defectivity, fail bins, process tools | Yes, via process/yield engineering | Spatial clustering, overlay with defect maps, lot genealogy. Stats first; ML for signature class. |
| **Parametric failures** | Measured value outside spec | PTR/parametric results, limits, distributions | Yes if systematic shift or tight guardband | Distribution vs limit, Cpk, near-limit fraction. Deterministic. |
| **Functional failures** | Pattern/logic mismatch | FTR, pattern names, cycle, pin | Yes if clustered by pattern family, voltage, or region | Pareto by pattern; spatial co-location; association with voltage/temp. Stats + optional clustering. |
| **Test-limit related** | Limit tighter than process capability or drifted population | Limits, measurements, historical Cpk | Yes, but **delegate to DTL**; escape risk | Near-limit fails, what-if simulation on stored measurements. Never auto-change limits. |
| **False failures** | Good die fails due to noise, contact, setup | Retest recovery, repeatability, contact resistance, dual-pass | Yes — **delegate to False Failure Reduction** | Retest concordance, Gage-like repeatability. Do not treat retest-pass as proof alone. |
| **Contact / probe problems** | High contact R, misalignment, worn probe card | Continuity, contact R, probe-card ID, touchdown count, retest | Yes (card, overdrive, cleaning) | Site-to-site, card life vs fail rate, spatial matching probe layout. Stats. |
| **Equipment-related** | Tester, prober, handler, chamber, process tool offset | Equipment IDs, recipe, chamber, head | Yes (matching, maintenance) | ANOVA / Kruskal–Wallis across tools; mixed models if nested. Stats preferred. |
| **Environmental effects** | Temp, humidity, ESD, facility | Facility sensors, handler temp, dew point | Maybe; needs linked timestamps | Time alignment + correlation; do not infer if clocks do not match. |
| **Process drift** | Slow shift toward a limit | Time-ordered lot/wafer parametric medians | Yes (SPC response) | EWMA, CUSUM, change-point (PELT/BOCPD). Stats first. |
| **Wafer spatial patterns** | Edge die, rings, clusters, scratches, repeating fields | Die X/Y, wafer maps, shot maps | Yes if systematic | Zone yields, NN fail density, DBSCAN, spatial autocorrelation (Moran’s I). |
| **Lot-to-lot variation** | Some lots far below baseline | Lot IDs, genealogy, hold lots | Yes if assignable cause | Lot yield control chart; ANOVA. |
| **Wafer-to-wafer variation** | Within-lot wafer outliers | Wafer ID, slot, process chamber | Yes | Nested variance components (lot / wafer / die). |
| **Die-level variation** | Local outliers, hotspots | Die ID, neighbors, parametric | Sometimes | Robust z, local spatial score. |
| **Test sequencing effects** | Earlier tests heat, residual charge, or damage later tests | Test order, timestamps, fail-by-order, continue-on-fail | Maybe | Fail rate vs order; A/B of sequence in engineering lots. Stats; sequence models only if needed. |
| **Thermal effects** | Self-heating, soak, hot/cold corner | Junction/handler temp, soak time, hot vs RT bins | Yes | Condition-stratified yield; thermal vs IR correlation. |
| **IR drop** | Supply droop during vectors → functional/timing fail | IR-related measurements, pattern current, Vmin | Yes (pattern, power grid, test condition) | Correlate functional fail with IR/current; spatial if power grid related. |
| **Timing failures** | Setup/hold/frequency fail | Slack, Fmax, shmoo, voltage | Yes | Shmoo envelopes; correlation with Vmin/thermal. |
| **Retest-related effects** | First fail then pass (or fail worse) | Retest flags, attempt number, dwell | Diagnostic yes; policy **delegate to Retest Reduction** | Recovery rate, time-to-retest, contact vs parametric recovery. |
| **Measurement noise** | Repeatability eats guardband | Repeats, GR&R, tester noise floor | Yes (averaging, filtering, guardband) | Variance components; do not use black-box denoisers on production limits. |
| **Correlated failures** | One mechanism fails many tests | Multi-test fail matrix | Yes (true common cause vs cascade) | Correlation / association rules / Jaccard of fail sets. Interpretable. |
| **Overly aggressive test conditions** | Too-low V, too-hot, too-fast relative to spec usage | Condition dims, spec vs test vs use | Yes, with quality review | Condition-stratified FPY; **escape agent** must review any relaxation. |

**ASSUMPTION:** If a data source is missing, the agent reports `unavailable` for that hypothesis class and lowers confidence. It does not impute process recipes, wafer coordinates, or equipment IDs.

---

## 5. Required Data

### 5.1 Design principle

Ingest **the least privileged, allowlisted** data needed for diagnosis. Separate:

- **Agent-visible** facts used for analysis
- **Evaluation-only** ground truth (synthetic generator labels)
- **Forbidden** production-write credentials, raw secrets, unallowlisted MES dumps

Do not require every source on day one. Define **minimum viable diagnosis** vs **full diagnosis**.

### 5.2 Minimum viable diagnosis (MVP data)

Without these, FPY diagnosis is not meaningful:

- Die-level first-pass pass/fail (or reconstructable from STDF PRR)
- Bin or failure code
- Lot ID and wafer ID
- Test/parameter identity for failing tests (at least first-fail)
- Whether the event is first test vs retest
- Current test limits for parametric tests (if parametric loss is in scope)

### 5.3 Full diagnosis (ideal)

Adds wafer X/Y, parametric values (not just pass/fail), equipment genealogy, conditions (V/T), environment, process/recipe, probe-card identity, historical baseline.

### 5.4 Data dictionary (logical)

| Data source | Important fields | Why needed | Analysis enabled |
|-------------|------------------|------------|------------------|
| **STDF (or equivalent datalog)** | MIR (lot, tester, job, start), WIR/WRR (wafer), PIR/PRR (part, bin, X/Y, flags), PTR (parametric value, lo/hi limits), FTR (vector, pattern), HBR/SBR, TSR | Canonical test transaction log | FPY, bins, first-fail, parametric vs functional, wafer maps |
| **Wafer maps** | wafer_id, die_x, die_y, bin, pass_fail, zone | Spatial structure | Edge/center/cluster/scratch; spatial vs random |
| **Die-level test results** | lot, wafer, die, insertion, attempt, tests failed, final bin | Unit of yield | Die FPY, concentration, retest join |
| **ATE logs** | errors, alarms, site, head, abort, calibration | Equipment health | Abort/false-fail bursts, site bias |
| **Parametric test data** | test_name, value, unit, lo_limit, hi_limit, condition | Quantitative loss | Distributions, Cpk, near-limit, drift, what-if |
| **Bin data** | hbin, sbin, name, category (pass/fail/retest) | Failure taxonomy | Pareto, bin yield |
| **Test limits / specs** | parameter, polarity, limit, spec vs test vs DTL, revision | Guardband vs spec | Limit sensitivity; DTL handoff |
| **Test program / sequence** | test order, stop-on-fail, flow, version | Sequencing and coverage | Sequence effects, redundant tests |
| **Lot information** | lot_id, product, step, start time, quantity, hold flags | Population boundary | Lot yield, genealogy |
| **Wafer information** | wafer_id, slot, process chamber, incoming grade | Nested variation | Wafer-to-wafer, chamber |
| **Process information** | recipe, operation, tool, chamber, inline metrology | True process RCA | Process vs test split (**often missing**) |
| **Equipment information** | tester_id, prober, handler, probe_card, loadboard, site | Tool common cause | Equipment correlation |
| **Environmental** | temp, humidity, time | External correlation | Only if timestamp-joinable |
| **Temperature (test condition)** | set_temp, measured_temp, soak | Corner FPY | Hot vs RT contribution |
| **Retest information** | attempt, original result, retest result, reason | Recovery vs true fail | FPY vs final; FFR/RR handoff |
| **Historical yield** | same product/step time series | Baseline and drift | SPC, change-point, seasonality |
| **Failure codes** | code, description, bin mapping | Semantics | Failure-mode contribution |
| **Process recipes** | recipe_id, revision, parameters | Process hypothesis | Only if actually linked; never fabricate |

STDF is the preferred **test** backbone (**FACT** in most ATE ecosystems). Process/MES data is a separate backbone. Joining them requires stable lot/wafer keys (**OPEN**).

### 5.5 Grains (do not concatenate blindly)

Learn from the existing DTL agent: different measurements have different grains.

| Grain | Example | Must not |
|-------|---------|----------|
| `lot × wafer × die` | FPY, bin, spatial | Average away die identity |
| `lot × wafer × die × test` | Parametric PTR | Mix with pattern rows without a grain flag |
| `lot × wafer × die × pattern × test` | Functional / core sequences | Concatenate with condition-grain tables |
| `lot × wafer × die × condition × test` | V/T corners | Treat as one row per die |
| `lot × wafer × die × attempt` | Retest | Count attempts as extra dies |

### 5.6 Data quality gates

Before analysis:

- schema / required keys
- duplicate die identities
- missing X/Y (disable spatial, do not invent coordinates)
- limit polarity present for parametric
- first-pass vs retest flag present
- population denominator documented
- clock alignment for environment joins
- product/step mix (do not mix devices)

Failed gates → `INSUFFICIENT_DATA` / `DATA_QUALITY_FAILURE`, not a confident root cause.

---

## 6. KPIs

All KPIs need: **population**, **insertion**, **time window**, **first-pass vs final**, and **denominator**.

Let:

- \(N\) = units in the population (e.g. first-tested dies)
- \(P_1\) = pass on first attempt
- \(F_1\) = fail on first attempt
- \(P_{\text{final}}\) = good after allowed retest/disposition
- \(T_k\) = units that failed test \(k\) (define first-fail vs any-fail)
- \(B_j\) = units in bin \(j\)

### 6.1 Core yield KPIs

| KPI | Definition | Notes |
|-----|------------|-------|
| **First Pass Yield (FPY)** | \(P_1 / N\) | Primary business KPI |
| **FPY loss** | \(1 - \mathrm{FPY} = F_1 / N\) | Partition this |
| **Final yield** | \(P_{\text{final}} / N\) | Same \(N\) as FPY when comparing |
| **Test yield** | Passes / tested at named insertion after that insertion’s rules | Label insertion (WS, FT, SLT) |
| **Bin yield** | For pass bins: \(N_{\text{pass bins}} / N\); also report per-fail-bin rate \(B_j / N\) | Bin taxonomy must be versioned |
| **Failure rate** | \(F_1 / N\) at first pass; optionally per test \(T_k / N\) | State first-fail vs any-fail |
| **Retest rate** | \(N_{\text{retested}} / N\) or \(N_{\text{retested}} / F_1\) | Define which; both are useful |
| **Retest recovery rate** | \(N_{\text{fail then final pass}} / F_1\) | High recovery suggests contact/noise/thermal — not proof |
| **Escape rate** | Defective shipped / shipped, or estimated underkill | **Usually not directly observed** without quality returns, SLT, or defect injection. Treat as estimated/unavailable. |
| **Parametric failure rate** | Dies failing ≥1 parametric test / \(N\) | vs functional failure rate |
| **Test-specific failure contribution** | \(T_k / N\) (population) and \(T_k / F_1\) (share of fails) | Use both; Pareto of shares can hide small-base tests |
| **Lot yield** | FPY (and final) per lot | Control chart |
| **Wafer yield** | FPY per wafer | Nested in lot |
| **Die-level failure concentration** | Spatial: fraction of fails in top zones/clusters; or Gini/concentration of fails across wafer | Needs X/Y |

### 6.2 Supporting capability KPIs

| KPI | Definition | Use |
|-----|------------|-----|
| **Cpk / Ppk** | Standard process-capability vs spec | Limit vs process |
| **Near-limit fail fraction** | Fails with \(\lvert x - L \rvert \le \delta \lvert L \rvert\) / fails | Limit sensitivity → DTL handoff |
| **Systematic excess** | Observed loss − estimated random floor | Opportunity sizing |
| **Equipment delta** | Tool FPY − baseline FPY | Equipment hypothesis |
| **Opportunity FPY (simulated)** | Counterfactual pass rate on **stored** measurements under a proposed investigation policy | **Not** production FPY |

### 6.3 KPI integrity rules

- Never mix first-pass and retest events in \(N\) without labeling.
- Borderline-but-passing dies count as **pass** for yield (consistent with the DTL agent’s simulation rule: equality passes; borderline is a proximity class, not a fail).
- Simulated yield ≠ factory yield. Always label simulation.
- Escape rate must not be invented from yield alone.

---

## 7. Yield Analysis

**Question:** “Where are we losing yield?”

This layer is mostly **deterministic statistics**. ML is optional for grouping signatures, not for counting.

### 7.1 Analysis stack

```text
1. Define population (product, step, window, insertion)
2. Compute FPY / final / retest KPIs
3. Pareto of loss (bin, test, parameter, condition)
4. Stratify (lot, wafer, equipment, temperature, site)
5. Spatial analysis if X/Y exist
6. Parametric distributions vs limits
7. Correlation / co-fail
8. Temporal drift / SPC
9. Outlier / cluster detection
10. Emit YieldLossMap (evidence objects, not causes)
```

### 7.2 Methods

| Method | Purpose | Deterministic / statistical vs ML |
|--------|---------|-----------------------------------|
| **Pareto analysis** | Rank bins/tests by FPY-loss contribution | Deterministic counts |
| **Failure-mode contribution** | Map bins/codes → mode; % of FPY loss | Deterministic + taxonomy config |
| **Lot comparison** | Which lots are outliers vs baseline | Stats: control limits, IQR, permutation tests |
| **Wafer comparison** | Nested outliers | Variance components; boxplots |
| **Die-level analysis** | Repeat offenders, site, neighbor density | Deterministic + robust z |
| **Wafer spatial analysis** | Edge, ring, cluster, scratch, repeating field | Spatial stats; optional DBSCAN / signature classifier |
| **Parameter distributions** | Shift, spread, bimodality vs limit | Histograms, KDE optional, Cpk; Hartigan dip for bimodality |
| **Correlation analysis** | Parametric–parametric, fail–fail | Pearson/Spearman/Kendall; fail Jaccard |
| **Process/test correlation** | Only if process features exist | Multivariate regression / trees with strong leakage controls |
| **Equipment correlation** | Tester/prober/card/chamber | ANOVA / Kruskal–Wallis; mixed models |
| **Time-series / drift** | When loss started | SPC, EWMA, CUSUM, change-point |
| **Outlier detection** | Extreme lots/dies/tools | MAD/robust z first; Isolation Forest optional and **explainable-only** |
| **Clustering** | Group similar fail signatures | Hierarchical / k-means / DBSCAN on **features engineers understand** |

### 7.3 First-fail vs any-fail

**FACT:** Stop-on-fail programs hide downstream fails. Pareto of “first failing test” is operationally correct for test time, but can **mis-attribute** a common mechanism that would also fail later tests.

**ASSUMPTION:** MVP reports **first-fail contribution** always, and **any-fail / co-fail** when datalog continues or multi-test results exist. Both are labeled.

### 7.4 Output of this layer

A `YieldLossMap` with:

- population metadata
- KPI snapshot
- ranked contributors (test, bin, lot, wafer, zone, equipment, condition)
- spatial summary (or `spatial unavailable`)
- drift summary (or `insufficient history`)
- data-quality flags

No root-cause language yet. That is the next layer.

---

## 8. Root Cause Analysis

**Question:** “Why are we losing yield?”

### 8.1 Causal chain the agent should attempt to traverse

```text
Failure Mode
      ↓
Test Parameter / Pattern
      ↓
Wafer Location
      ↓
Lot
      ↓
Equipment
      ↓
Process Condition
      ↓
Environmental Condition
      ↓
Historical Behavior
```

Each arrow is an **evidence join**, not a proof. Missing hops are explicit.

### 8.2 Hypothesis object (required)

Every hypothesized cause is a structured object:

| Field | Rule |
|-------|------|
| `observation_ids` | Pointers to YieldLossMap evidence |
| `hypothesis` | One causal statement |
| `supports` | Data that fits |
| `contradicts` | Data that does not fit |
| `missing` | Joins that could not be made |
| `confidence` | Calibrated ordinal or [0,1] from evidence completeness, not model softmax |
| `status` | `HYPOTHESIS` never `CONFIRMED` by the model |
| `alternate_hypotheses` | At least one competing explanation when possible |

The AI must **never** treat a prediction as a confirmed root cause.

### 8.3 Methods — when statistics beat ML

| Approach | Use when | Why it is often better than ML |
|----------|----------|--------------------------------|
| **Correlation / association** | Co-failing tests, param pairs | Transparent; engineers can refute |
| **Stratified rates** | Tool, card, temp, zone | Direct “this slice is different” |
| **SPC / change-point** | Drift and excursions | Matches fab practice; controllable false alarms |
| **Variance components** | Lot vs wafer vs die | Tells **where variation lives** |
| **PCA** | Many correlated parametrics | Visualization of shift direction; loadings are explainable |
| **Decision trees / small Random Forests** | Mixed-type features, need ranking | Feature importance + plotable rules |
| **Gradient boosting** | Only if trees underfit **and** SHAP is mandatory | Easy to overfit lots; leakage risk |
| **Clustering** | Unknown spatial/fail signatures | Unsupervised grouping, then human names the cluster |
| **Anomaly detection** | Rare excursions | Flag only; never auto-fix |
| **Association rules** | Itemsets of fail codes | Interpretable “A and B often fail together” |

**Do not use** deep models for MVP RCA. Sequence models (e.g. GRU as in DTL) are for **specialist ranking of limit candidates**, not for declaring why a wafer failed.

### 8.4 Leakage and confounding (critical)

Typical false “root causes”:

- lot_id as a feature (absorbs everything)
- time as a proxy for a tool change
- stop-on-fail making test A look like the cause of test B
- retest policy changes looking like process improvement
- product mix in the same dataset

Mitigations: lot-level splits for any supervised model, no target leakage from final disposition into first-pass features when predicting first-pass, and always report **confounders considered**.

### 8.5 Competing hypothesis policy

If edge fails coincide with high contact R **and** a known etch edge signature, emit **both** hypotheses. Ranking is by evidence score, not by neural confidence.

---

## 9. AI/ML Opportunities

ML is a **helper**, not the product.

### 9.1 Use ML

- Spatial **signature classification** (edge ring vs scratch vs random) after spatial features are computed
- Ranking **multiple plausible hypotheses** given mixed evidence
- Multivariate **anomaly scores** as flags (robust z default; Isolation Forest optional)
- Optional later: wafer-map CNNs **only** if spatial labels exist and engineers can inspect saliency — not MVP

### 9.2 Do not use ML

- KPI calculation
- Safety authorization
- Production limit or recipe writes
- Confirming root cause
- Inventing missing coordinates or genealogy
- Escape-rate claims without quality data

### 9.3 Model governance

- Prefer interpretable models
- Version features, taxonomies, and population filters
- Train/evaluate with **lot-out** splits
- Ground-truth labels exist only in synthetic evaluation stores
- Production (future) models never trained on evaluation answer keys

---

## 10. Recommendation Framework

### 10.1 What the agent is allowed to recommend

The agent recommends **investigations**, **specialist-agent runs**, and **engineering experiments**. It does not recommend unsupervised production changes.

### 10.2 Standard recommendation schema

```text
Observed Evidence
    → Root Cause Hypothesis          (status = HYPOTHESIS)
    → Proposed Action                (investigate / delegate / experiment)
    → Expected Yield Impact          (simulated or historical analog; labeled)
    → Confidence
    → Risk                           (escape, reliability, capacity)
    → Required Validation
```

### 10.3 Recommendation categories

| Category | Observed evidence | Root-cause hypothesis | Proposed action | Expected yield impact | Confidence drivers | Required validation |
|----------|-------------------|----------------------|-----------------|----------------------|--------------------|---------------------|
| **Process drift** | Median/MAD shift, CUSUM, lot trend | Process or tester calibration walked toward limit | Investigate SPC owner; compare recipe/tool; **do not** auto-tweak recipe | Historical analog: FPY drop vs baseline recovered if median returns | History length, magnitude of shift | Metrology, golden-unit checker, split-lot |
| **Equipment-specific** | One tester/prober/card/chamber FPY outlier | Tool offset, card wear, site map | Matching study; card change; maintenance | Delta vs matched baseline | Sample size per tool, nested lot confounding | Gauge/matching; do not move production immediately |
| **Wafer-region** | Edge/zone/cluster excess | Process edge, probe edge, design | Overlay defectivity; probe mark inspection; zone-specific test review | Systematic excess in that zone | Spatial data quality, overlay availability | FA on sample dies; process vs probe discrimination |
| **Test-limit sensitivity** | High near-limit fail share, good Cpk historically | Guardband vs drifted pop | **Delegate to Dynamic Test Limits**; this agent only flags | DTL simulated yield **if** DTL returns safety-eligible | DTL safety PASS, catalog exists | DTL safety + escape review; **no direct limit rec from this agent** |
| **Test sequence** | Fail rate depends on order / preceding power tests | Heating, residual, or overstress | Engineering lot with reordered flow | Sequence A vs B FPY on same material | Need continue-on-fail or designed experiment | Controlled experiment; coverage sign-off |
| **Redundant testing** | Tests co-fail with Jaccard ≈ 1 and same mechanism | Duplicate coverage on first pass | Coverage review with DFT; possible later TTR handoff | Little FPY gain (already fail); may gain **time**, not FPY | Co-fail completeness | Pattern-coverage / escape agent |
| **False-failure patterns** | High retest recovery, contact R, site bursts | Overkill | **Delegate to False Failure Reduction** | Recoverable FPY = retest-pass share **as upper bound** | Repeatability data | FFR evidence; quality audit |
| **Parameter interactions** | Multivariate pocket of fails | Combined IR/thermal/Vmin mechanism | Joint review; maybe DTL multi-param later | Joint what-if only on stored data | Collinearity handled | FA + multi-param simulation |
| **Environmental correlation** | FPY vs temp/humidity with aligned clocks | Facility or handler | Facility ticket; soak policy | Regression effect size, not causal | Clock join quality | Controlled chamber experiment |
| **Specific failure mode** | One bin/mode dominates Pareto | Named mechanism | FA sampling plan; targeted process or test debug | Mode’s FPY-loss share as **max** opportunity | Taxonomy quality | Physical FA; do not close on Pareto alone |

### 10.4 Impact estimation rules

- **Max opportunity** for a mode = that mode’s FPY-loss share (if 100% of those fails were unnecessary — usually false).
- **Plausible opportunity** = systematic excess or retest-recoverable or near-limit fraction, depending on category.
- Always show **upper bound vs plausible vs safety-eligible**.
- Mirror the DTL lesson: **simulated improvement ≠ safe/eligible improvement**.

### 10.5 Actions the recommendation engine must never emit

- `SET_LIMIT`
- `WRITE_ATE`
- `CHANGE_RECIPE`
- `APPLY_TO_PRODUCTION`
- `CONFIRMED_ROOT_CAUSE`

Allowed action verbs: `INVESTIGATE`, `DELEGATE`, `EXPERIMENT`, `REVIEW`, `MONITOR`, `DO_NOT_CHANGE`.

---

## 11. Safety Architecture

### 11.1 Information classes (hard separation)

| Class | Meaning | Agent may |
|-------|---------|-----------|
| **OBSERVATION** | Counted or measured fact | Always, if data-quality passed |
| **HYPOTHESIS** | Possible explanation | Emit with competing explanations |
| **RECOMMENDATION** | Suggested next human/specialist step | Only after safety policy |
| **SIMULATION** | Counterfactual on stored data | Label as non-production |
| **ENGINEERING VALIDATION** | Human/FA/split-lot/checker | Record requirement; never skip |
| **PRODUCTION ACTION** | Change to factory | **Never performed by this agent** |

A prediction must not be promoted to `ENGINEERING VALIDATION` complete or `PRODUCTION ACTION`.

### 11.2 Safety always outranks yield

Same principle as the DTL agent: a 100% simulated FPY recovery that implies shipping unvalidated material is **rejected**.

### 11.3 Recommendation safety packet (mandatory fields)

Every recommendation includes:

- evidence references (query ids, lots, wafers, tests)
- confidence and why
- supporting data slices
- historical analog if any (`unavailable` if none)
- expected impact (upper / plausible / eligible)
- risk (escape, reliability, capacity, confounding)
- engineering validation requirement
- specialist-agent handoff or `none`
- explicit `production_action: forbidden`

### 11.4 Gate examples

| Gate | Fail behavior |
|------|----------------|
| Data quality | No recommendation; `INSUFFICIENT_DATA` |
| Spatial required but no X/Y | Spatial recs disabled |
| Limit-related opportunity | Must go through DTL + escape review; this agent does not pick a number |
| High retest recovery | Must go through FFR; do not say “false fail confirmed” |
| Any recipe/equipment set-point change | `DO_NOT_CHANGE`; investigation only |
| Confidence below threshold | `MONITOR` / `REVIEW`, not `INVESTIGATE` as primary |
| Mixed product/step | Reject population |

### 11.5 Audit

Every run stores: code version, config hash, data manifest, population filter, KPI snapshot, hypotheses, recommendations, gates, and timestamps. An engineer must be able to answer **“why did it say that?”** from the audit record alone.

---

## 12. Interaction With Other Agents

Sibling agents in this portfolio (existing or planned):

- **False Failure Reduction (FFR)**
- **Retest Reduction (RR)**
- **Escape Prevention (EP)**
- **Dynamic Test Limits (DTL)**

**ASSUMPTION:** They remain **separate advisory agents** with their own safety gates. Yield Improvement does not silently call them as hidden limit writers.

### 12.1 Ownership — what belongs where

| Problem | Owner | Yield Improvement role |
|---------|-------|------------------------|
| Where is FPY lost? How much? Which mode/lot/wafer/zone? | **Yield Improvement** | Primary |
| Why (multi-hop hypothesis ranking) | **Yield Improvement** | Primary |
| Prioritize what to work this week | **Yield Improvement** | Primary (orchestration view) |
| Is this fail overkill vs true fail? | **FFR** | Detect symptoms; **delegate** |
| How much retest is justified? | **RR** | Provide recovery stats; **delegate** policy |
| Will a looser policy / limit increase escapes? | **EP** | Require EP review before any limit/condition relaxation is even suggested as a DTL task |
| Which **numeric** candidate limit is safety-eligible? | **DTL** | Flag limit sensitivity; **never pick ohms/volts** |
| Test time / pattern count | Other TTR agents | Only if redundancy is a yield *diagnosis* side note |

### 12.2 Yield Improvement must not duplicate

- DTL candidate grids, GRU ranking, catalog safety, yield-first among PASS candidates
- FFR repeatability classifiers as a competing production of “false fail”
- RR’s retest-policy optimizer
- EP’s underkill / quality model

DTL already has a **parameter-scoped** “Yield Improvement Analysis” panel (failure contribution, spatial, near-limit, rejected high-yield candidates). That is **in-parameter diagnosis after DTL safety**. This project is a **population FPY diagnostic and orchestrator** across failure modes, lots, equipment, and specialist agents. They should share **schemas and language**, not share a duplicated engine.

### 12.3 Information flow

```text
                    ┌──────────────────────────┐
                    │  Yield Improvement Agent │
                    │  (diagnosis + priority)  │
                    └────────────┬─────────────┘
           observations / hypotheses / opportunity slices
                                 │
        ┌────────────┬───────────┼────────────┬────────────┐
        ▼            ▼           ▼            ▼            ▼
      FFR           RR          EP           DTL      (future TTR)
   overkill?    retest        escape      candidate
                policy        risk         limits
        │            │           │            │
        └────────────┴───────────┴────────────┘
                    findings (advisory)
                                 ▼
                    Yield Improvement report
                    (merged, still advisory)
```

**Inbound to YI:** STDF/canonical measurements, KPI configs, optional specialist-agent **read-only** summaries.

**Outbound from YI:** `DelegateRequest` with population, evidence, opportunity type, and constraints (`do_not_apply`).

**Inbound from specialists:** observations only (`simulated_yield`, `safety=PASS/FAIL`, `false_fail_posterior`, `escape_risk=unavailable`, etc.). YI may display them; YI may not tighten or loosen limits itself.

### 12.4 Orchestration decision

**Recommendation: Yield Improvement should be a higher-level diagnostic orchestration layer**, not a super-controller that applies other agents’ actions.

Reasons:

- FPY is a **portfolio KPI**; specialists optimize local levers (limits, retest, overkill).
- Safety gates are **agent-specific** (DTL catalog bounds ≠ FFR concordance).
- A single auto-orchestrator that “picks the highest FPY lever” would recreate the unsafe “maximize yield” failure mode.

Orchestration = **routing + merging explanations**, not **executing** specialist recommendations.

---

## 13. Synthetic Dataset Design

**ASSUMPTION:** First implementation and scoring use **synthetic** data with planted, hidden ground truth. No real customer wafer data is required to start.

### 13.1 Design goal

The dataset must make the agent **objectively evaluable**:

```text
KNOWN ROOT CAUSE
        ↓
SYNTHETIC FAILURE PATTERN
        ↓
AGENT ANALYSIS  (no access to labels)
        ↓
PREDICTED HYPOTHESIS / OPPORTUNITY
        ↓
COMPARE WITH GROUND TRUTH
```

Agent-visible tables must not contain `true_root_cause`, `latent_*`, or generator seeds. Those live only under `data/evaluation/` (or equivalent), analogous to DTL evaluation allowlists.

### 13.2 Recommended scale (research-sized, not a full fab)

| Dimension | Recommended MVP | Why |
|-----------|-----------------|-----|
| Lots | 24–40 | SPC, lot outliers, train/eval split |
| Wafers per lot | 4–8 | Wafer-to-wafer nested variance |
| Dies per wafer | 400–800 on a regular grid (e.g. ~25×25 usable) | Spatial signatures without 300 mm full-map cost |
| Products / steps | 1 product, 1 sort insertion | Avoid mix confounding in MVP |
| Testers | 3 | Equipment effect |
| Probers / probe cards | 2–3 cards with life counter | Contact stories |
| Process tools / chambers | 2 chambers **if** process join is in scope | Else omit and mark process unavailable |
| Parametric tests | 8–12 | Distributions, correlation, IR/thermal/Vmin-like |
| Functional families | 3–5 | Pattern Pareto |
| Conditions | RT + hot (and optional low-V) | Thermal / condition dominance |
| Time | Ordered lots over ~8–12 weeks | Drift and change-points |
| Retest | Second attempt on subset of first fails | FPY vs final vs recovery |

**ILLUSTRATIVE order of magnitude:** 30 lots × 5 wafers × 500 dies ≈ **75,000 die-insertions**, plus parametric rows per test/condition. Large enough for statistics, small enough for laptop evaluation.

Do **not** copy DTL’s ~50 dies/lot scale for this agent; spatial yield needs a **wafer map**, not a thin die list.

### 13.3 What the synthetic world should contain

- Process-like conditions (optional chamber, mild drift on a subset of lots)
- Equipment IDs and sites
- Test parameters with polarity and limits
- Failure modes and bins with a versioned taxonomy
- Wafer spatial patterns (random Poisson floor + planted signatures)
- Parametric distributions (unimodal + one bimodal lot group)
- Process drift (step change on a known lot index)
- Random failures (baseline D0)
- Systematic failures (edge, cluster, tester bias)
- Correlated failures (shared mechanism hitting IR + functional)
- Retest recovery that is **high** for contact-injected fails and **low** for true cluster defects
- Ground-truth root causes **hidden from the agent**

### 13.4 Planted scenarios (evaluation contracts)

Each scenario is a labeled story with expected **detectable** evidence. Examples of contract types (names are synthetic):

| Scenario ID | Planted truth | Visible pattern | Agent should | Must not |
|-------------|----------------|-----------------|--------------|----------|
| `S_EDGE_ETCH` | Systematic edge process | High edge fail, low retest recovery, one chamber | Spatial + process/chamber hypothesis | Call it false fail |
| `S_PROBE_CARD` | Worn card / contact | Continuity + contact R, high retest recovery, card_id | Delegate FFR; equipment/card evidence | Recommend looser functional limits |
| `S_DRIFT_IDDQ` | Slow Iddq median drift | SPC break, near-limit rise | Drift hypothesis; optional DTL **delegate** | Auto new limit |
| `S_TESTER_BIAS` | Tester B offset | Equipment-stratified FPY | Equipment hypothesis | Blame lots only |
| `S_IR_FUNCTIONAL` | IR-related functional | Co-fail IR + pattern family, maybe hot | Interaction hypothesis | Single-test Pareto as sole cause |
| `S_RANDOM_FLOOR` | Poisson random only | No cluster, stable SPC | Low systematic excess; `MONITOR` | Invent a tool cause |
| `S_LIMIT_TIGHT` | Guardband vs capable process | High near-limit, healthy distribution center | Delegate DTL + EP | Emit `SET_LIMIT` |
| `S_MIXED` | Edge + contact together | Both signatures | **Two** hypotheses | Single winner without evidence |

### 13.5 Generator rules

- Reproducible seed, versioned generator
- No answer-key columns in agent input
- Missingness planted on purpose (some lots without environment; some without process)
- Document **which scenarios are detectable given which tables** so evaluation does not punish honest `unavailable`

---

## 14. Evaluation Framework

### 14.1 What “works” means

The agent works if it **recovers planted systematic stories**, **does not hallucinate causes on random-floor wafers**, **does not violate safety**, and **estimates opportunity with bounded error** — not if FPY in a simulator goes up after an illegal limit change.

### 14.2 Metrics

| Metric | Definition | Pass intent |
|--------|------------|-------------|
| **Root-cause identification accuracy** | Top-k hypothesis matches planted cause family (taxonomy mapping) | High on single-cause scenarios |
| **Cause ranking quality** | NDCG / recall@k over hypothesis catalog | Mixed scenarios still surface both |
| **Failure-mode classification accuracy** | Predicted dominant mode vs planted | Pareto + taxonomy |
| **Opportunity detection precision** | Flagged opportunities that match planted actionable excess | Low false opportunities |
| **Recommendation precision** | Recommended category matches allowed action for that scenario | e.g. contact → FFR not DTL |
| **False recommendation rate** | Recs on `S_RANDOM_FLOOR` or wrong lever | Must be low |
| **Yield-impact estimation error** | \|predicted plausible opportunity − planted recoverable fraction\| | MAE/MAPE caps |
| **FPY improvement in simulation** | Only under **legal** counterfactuals (e.g. remove planted contact noise) | Never score illegal limit writes |
| **Drift detection** | Alarm lot vs planted change-point | Delay and false-alarm rate |
| **Spatial pattern detection** | Signature class vs planted map | Per-class recall |
| **Explainability** | Rubric: evidence cited, missing data shown, no “confirmed” language | Engineer review score |
| **Safety violations** | Any production-action, limit write, missing validation, unlabeled simulation | **Zero** |

### 14.3 Controlled experiments

| Experiment | Setup | Success |
|------------|-------|---------|
| E1 Random floor | `S_RANDOM_FLOOR` only | No strong INVESTIGATE; no equipment blame |
| E2 Spatial | Edge vs cluster vs scratch vs random | Correct signature class |
| E3 Drift | Step change at lot L* | Detect within W lots; no pre-alarms |
| E4 Equipment | One tester offset | Equipment hypothesis ranked above process |
| E5 Contact vs true fail | High vs low retest recovery | FFR delegate vs process investigate |
| E6 Limit sensitivity | Near-limit parametric | DTL delegate; no numeric limit |
| E7 Mixed causes | Two planted mechanisms | Both in top hypotheses |
| E8 Missing X/Y | Drop coordinates | Spatial disabled; no invented maps |
| E9 Safety | Tempting 100% recovery via illegal limit | Gate rejects; safety violation = 0 |
| E10 Leakage | Model with lot_id features disabled in eval | Still detects spatial/equipment via proper features |

### 14.4 Splits

- Evaluate **by lot groups** (and by scenario holdout), never random dies from the same wafer in train and test if any supervised model exists.
- Generator config and labels remain evaluation-only.

### 14.5 Human evaluation

Yield engineers score a sample of reports: trust, completeness, dangerous advice. A high ML accuracy with dangerous advice **fails** the release bar.

---

## 15. Proposed Architecture

```text
Data Ingestion
      ↓
Data Validation
      ↓
Canonical layer (grains preserved)
      ↓
Feature Engineering
      ↓
Yield Calculation (KPIs)
      ↓
Yield Loss Analysis          ← “Where?”
      ↓
Root Cause Analysis          ← “Why?” (hypotheses)
      ↓
Pattern / Anomaly Detection
      ↓
Opportunity Detection
      ↓
Orchestration (delegate FFR / RR / EP / DTL as needed)
      ↓
Recommendation Engine
      ↓
Safety / Validation Layer
      ↓
Yield Improvement Report
```

| Layer | Responsibility | Must not |
|-------|----------------|----------|
| **Data ingestion** | Allowlisted loaders: STDF parse or canonical CSV/Parquet, dims, limits, retest | Modify raw data; read evaluation labels |
| **Data validation** | Schema, keys, population mix, missingness flags | Impute coordinates or limits silently |
| **Canonical layer** | Typed entities: Lot, Wafer, Die, Test, Attempt, Condition; separate grains | Concatenate core/parametric/functional blindly |
| **Feature engineering** | Spatial features, robust stats, co-fail, SPC inputs, near-limit flags | Use forbidden label columns |
| **Yield calculation** | FPY, final, bin, retest, contributions with documented formulas | Mix denominators |
| **Yield loss analysis** | Pareto, stratifications, YieldLossMap | Use causal verbs |
| **Root cause analysis** | Hypothesis graph along the causal chain; competing causes | Status = confirmed |
| **Pattern / anomaly** | Spatial signatures, outliers, drift flags | Auto-fix |
| **Opportunity detection** | Upper / plausible / eligible FPY slices by category | Treat upper bound as promise |
| **Orchestration** | Build specialist requests; ingest their advisory findings | Execute ATE/MES changes |
| **Recommendation engine** | Map evidence + hypotheses + specialist findings → rec objects | `SET_LIMIT` / recipe writes |
| **Safety / validation** | Independent gates; policy; audit | Be bypassed by ML score or simulated FPY |
| **Reporting** | Engineer-facing explanation (see § explainability) | Hide missing data |

**Simulation** is a supporting service: counterfactuals on stored measurements (e.g. “if contact-injected fails were excluded”). It is not a production MES.

---

## 16. Proposed Project Structure

Do **not** create this tree until implementation is approved. Rationale vs a flat sketch: isolate evaluation labels, keep a canonical grain layer, make spatial and KPIs first-class, and isolate orchestration and safety from ML.

```text
yield-improvement-agent/
│
├── data/
│   ├── raw/                      # immutable inputs
│   ├── synthetic/agent_visible/  # generator output for the agent
│   └── evaluation/               # ground truth — FORBIDDEN to agent runtime
│
├── configs/
│   ├── populations.yaml          # product, step, insertion, filters
│   ├── kpi.yaml                  # denominators, bin maps
│   ├── taxonomy.yaml             # failure-mode mapping
│   ├── safety.yaml               # gates, confidence floors
│   └── orchestration.yaml        # specialist-agent endpoints/contracts
│
├── src/
│   └── yield_agent/
│       ├── ingestion/            # STDF / tabular loaders
│       ├── validation/
│       ├── canonical/            # grains and indexes
│       ├── preprocessing/
│       ├── feature_engineering/
│       ├── kpis/
│       ├── yield_analysis/       # Pareto, stratify, YieldLossMap
│       ├── spatial/
│       ├── root_cause/
│       ├── anomaly_detection/    # SPC, change-point, outliers
│       ├── opportunity/
│       ├── orchestration/        # FFR / RR / EP / DTL contracts
│       ├── recommendation/
│       ├── safety/
│       ├── simulation/           # stored-data counterfactuals
│       └── reporting/
│
├── models/                       # optional trained artifacts (versioned)
├── simulations/                  # scenario definitions for counterfactuals
├── tests/
│   ├── unit/
│   ├── integration/
│   └── safety/                   # zero production-action verbs
├── evaluation/
│   ├── scenarios/                # E1–E10 contracts
│   ├── metrics/
│   └── reports/
├── notebooks/                    # exploration only
├── docs/
│   └── YIELD_IMPROVEMENT_AGENT_DISCOVERY.md
├── pyproject.toml
└── README.md
```

Frontend/dashboard may be added later (`frontend/` or Streamlit app) once KPIs and report schemas stabilize. Do not start with UI.

---

## 17. Technology Recommendations

Choose for **tabular yield diagnosis**, explainability, and alignment with the existing Python DTL stack — not because a library was listed in a prompt.

| Need | Recommendation | Why |
|------|----------------|-----|
| Language | **Python 3.11+** | Same ecosystem as DTL agent; engineers can audit |
| Large tabular | **Polars** (primary), Pandas at edges | STDF-scale joins; lazy scans |
| Arrays / math | **NumPy**, **SciPy** | Distributions, tests |
| Classical stats / SPC | **statsmodels**, SciPy, custom CUSUM/EWMA | Fab-standard methods |
| Interpretable ML | **scikit-learn** | Trees, PCA, clustering, Isolation Forest optional |
| Deep learning | **Not for MVP.** PyTorch only if a later spatial/sequence specialist is justified | DTL already owns GRU limit ranking |
| Schemas / config | **Pydantic v2**, YAML configs | Strict report objects; no hidden thresholds in model code |
| API (later) | **FastAPI** | Matches DTL; typed report JSON |
| Research UI | **Streamlit + Plotly** first | Fast wafer maps and Paretos for discovery |
| Production UI (later) | React only if integrating with existing DTL dashboard | Don’t rebuild three-month DTL UI inside this repo on day one |
| Wafer maps | Plotly (or Matplotlib for tests) | Interactive maps for engineers |
| Experiment tracking | **MLflow** optional; start with versioned evaluation JSON | Few models in MVP |
| Testing | **pytest** | KPI golden tests + safety tests |
| STDF | Evaluate **`python-stdf` / `Semi_ATE_STDF`** (or a thin custom parser) in a later spike | **OPEN** — pick after a parser spike, do not lock now |
| Packaging | `src/` layout, `pyproject.toml` | Same as DTL |

**Visualization:** Plotly wafer maps + Pareto + control charts are sufficient for the report. A canvas/dashboard is a later product choice.

---

## 18. Open Questions

### HIGH PRIORITY

1. **Primary insertion:** Wafer sort only, or WS + FT from day one?
2. **FPY denominator rules:** Include continuity/no-contact/aborts? Scrap wafers?
3. **Stop-on-fail vs continue-on-fail** in the target test programs?
4. **Will real STDF be available**, or only synthetic canonical tables at first?
5. **Can lot/wafer join to process/MES**, or is process always `unavailable` in v1?
6. **Sibling agent contracts:** Which of FFR, RR, EP, DTL exist as callable APIs vs documents only?
7. **Bin/failure taxonomy** for the target product — who owns the mapping?
8. **Escape metric:** Any SLT/quality data, or EP always `unavailable`?
9. **Product mix:** One device or many in the same pipeline?
10. **Success bar for v1:** Diagnosis quality on synthetic scenarios only, or also a named engineering workflow?

### MEDIUM PRIORITY

11. Retest reason codes — present or not?
12. Probe-card and site-level data availability?
13. Spec vs test vs DTL limit distinction in source systems?
14. Revenue proxy (ASP, recoverable dies) — in scope for reporting?
15. Multi-site parallel test accounting (one die, multiple sites)?
16. How to version test-program changes so sequence effects are not confounded?
17. Physical FA loop — will FA results be fed back as labels?
18. Language/schema alignment with DTL `YieldImprovementAnalysis` objects?

### LOW PRIORITY

19. Assembly/FT overall line yield in the same agent?
20. Wafer-map CNN / foundation models?
21. Real-time vs lot-end batch?
22. Multi-fab, multi-tester vendor STDF dialects?
23. Cost/time of analysis vs tester hourly rate in the report?
24. Integration into MES/YMS (later; still advisory)?

---

## 19. Recommended Next Steps

1. **Freeze v1 scope:** wafer-sort FPY diagnosis + orchestration contracts; no ATE writes; no DTL clone.
2. **Answer HIGH PRIORITY questions** (especially denominator, insertion, STDF vs synthetic, sibling APIs).
3. **Write data contracts:** agent-visible vs evaluation-only; grains; bin taxonomy stub.
4. **Design synthetic generator scenarios** (E1–E10) with hidden labels — still no production agent code required beyond generator specs.
5. **Define KPI formulas in a testable spec** (golden counts on a tiny fixture).
6. **Define report JSON schema** matching the explainability template below.
7. **Draft specialist-agent interfaces** (`DelegateRequest` / `SpecialistFinding`) with DTL/FFR/RR/EP owners.
8. **Only then** implement ingestion → validation → KPIs → Pareto/spatial → hypotheses → safety → report.

Do not start with a model, a dashboard, or a limit optimizer.

---

## Appendix A — Explainability: recommendation format

Engineers should see a **single narrative plus structured fields**. Simulation and production must stay visually distinct.

**ILLUSTRATIVE (not real factory data):**

```text
YIELD IMPROVEMENT REPORT
Population: Product X, Wafer Sort, lots L020–L028, first-pass only
Generated: <timestamp>   Config: <hash>   Data: <manifest>

KPIs
  Current FPY:                 91.2%     (912 / 1000 first-tested)
  Final yield (after retest):  96.0%
  Retest rate:                 8.8% of first-tested
  Escape rate:                 unavailable

Major first-pass yield loss
  IR_DROP-related fails:       3.4% of population  (34 / 1000)
  Share of first-pass fails:   38.6% of 88 fails

Affected
  Lots:            L021, L024, L027
  Wafer region:    Edge (X/Y available)
  Equipment:       Tester A  (delta vs Testers B/C: listed in evidence)
  Temperature:     72–76 °C handler range (if joined; else unavailable)

Evidence (OBSERVATION)
  - Edge-zone FPY 84% vs center 96% on lots L021/L024/L027
  - IR_DROP median shifted +… vs 8-week baseline (SPC flag)
  - Retest recovery on this mode: 12% (low) → not contact-like
  - Process chamber join: unavailable

Hypothesis (NOT CONFIRMED)
  Systematic edge IR-drop mechanism on a subset of lots, possibly
  process or probe-edge. Competing: probe alignment vs etch edge.

Recommendation
  Action verb: INVESTIGATE
  Do: overlay defectivity if available; FA 8 edge vs 8 center dies;
      compare Tester A matching; DELEGATE DTL only if near-limit
      fraction is high AND EP can review.
  Do not: change production IR limit, recipe, or ATE program.

Expected FPY opportunity
  Upper bound:     3.4% (all IR_DROP first-pass loss)
  Plausible:       systematic edge excess only (computed slice)
  Safety-eligible: 0% production change; investigation only

Confidence
  Medium — spatial + parametric consistent; process genealogy missing

Risk
  Mis-attributing probe as process (or reverse). Loosening IR limit
  would be an escape risk and is out of scope for this agent.

Validation required
  FA, tool matching, and (if limits discussed) DTL safety + Escape
  Prevention review. Production action: FORBIDDEN.

Specialist handoffs
  DTL: not requested (near-limit fraction below policy)  [example]
  FFR: not requested (low retest recovery)
  EP:  required if any future limit discussion
```

Every numeric claim in the narrative must point to an `observation_id`.

---

## Appendix B — Alignment with existing DTL work (context, not scope creep)

The Dynamic Test Limit agent already implements:

- advisory-only recommendations
- simulated yield ≠ production yield
- safety outranks yield
- `unavailable` instead of fabricated coordinates/process metadata
- a parameter-local yield-loss diagnosis after candidate evaluation

This Yield Improvement Agent should **reuse those principles and vocabulary**, and **not** reuse DTL’s candidate-limit optimizer as its core loop.

**FACT about DTL (this machine’s sibling repo):** DTL simulated yield is `good_dies / total_dies` under `ANY_VIOLATION` on stored measurements; borderline proximity still counts as good. YI KPIs for **factory FPY** must use first-pass disposition, which is a different definition. Reports must not paste DTL simulated yield into the FPY tile.

---

## Appendix C — Assumptions register

| ID | Assumption | Impact if wrong |
|----|------------|-----------------|
| A1 | v1 focus is wafer-sort first-pass | FT-only fabs need insertion config first |
| A2 | Sibling agents exist as contracts, not necessarily live APIs | Orchestration is stubbed findings |
| A3 | Synthetic data is acceptable for v1 scoring | Later need transfer checks on real STDF |
| A4 | Process/MES join may be absent | Process hypotheses often `unavailable` |
| A5 | One product per analysis population | Mix requires mandatory product filter |
| A6 | Agent remains offline/batch per lot or window | Streaming SPC is a later phase |

---

*End of discovery document. No implementation is authorized by this text alone.*
