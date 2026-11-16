# Yield Improvement V2 Predictive Signal Investigation

This is an investigation of where observable association with `first_pass_fail` sits in Yield Improvement V2. It does not retrain `yi_ml_v2`, does not change the 16-feature contract, and does not activate a model.

Labels used below:

- **FACT**: counted from the agent-visible files or from the saved feature definition.
- **PREDICTIVE ASSOCIATION**: a ranking or rate difference. Not a root cause.
- **LIMITATION**: a reason that association may fail under leave-one-lot-out, or a reason a column is not a clean model input.
- **HYPOTHESIS**: a proposed mechanism that this phase did not refit.
- **EVALUATION-ONLY INFORMATION**: read from `evaluation/ground_truth/synthetic_v2/yi_synthetic_v2.json` after the observable measurements. Not a production feature and not production evidence.

Univariate ROC-AUC below is direction-invariant: the reported value is at least 0.5. A value near 0.50 is no better than an uninformative score. These AUCs are not the pooled logistic model.

## 1. Executive summary

**FACT.** L004 has 500 eligible dies and 97 of the 251 first-pass failures (rate 0.194). Its wafer rates rise from 0.06 on W01 to 0.45 on W05. Inside that lot, `timestamp_epoch` ranks failures with AUC 0.748. The other 15 contract features stay near AUC 0.50–0.54 on L004.

**LIMITATION.** The same timestamp, with its sign taken from the other four lots, ranks L004 at AUC 0.252. The within-lot pattern is real. It does not transfer, because the other lots do not share that slope and the lot clocks do not overlap.

**PREDICTIVE ASSOCIATION.** A wafer-border indicator that is not in the contract separates L002 (0.167 on the border versus 0.059 inside, AUC 0.640) and L005 (0.117 versus 0.041, AUC 0.638). `spatial_region` overlaps only 325 of 900 border dies (36%) and does not reproduce that split.

**PREDICTIVE ASSOCIATION.** On the parametric file, read separately and not joined into the ML matrix, VMIN ranks L004 failures at AUC 0.728 and IDDQ at 0.671. Both means rise from W01 to W05. CONTACT_RESISTANCE ranks L002 at 0.608 and L003 at 0.638, and does not rank L004 (AUC 0.507). These are attempt measurements. They are stronger than temperature, voltage, site, and the current spatial features. This investigation does not add them to the contract.

**FACT.** Voltage, site, and prober show no useful association. Temperature spans about 18 °C to 89 °C, and the hot group (293 dies at or above 50 °C) fails at 0.113 against 0.099 for the rest.

## 2. Current ML baseline

**FACT.** Saved candidate `artifacts/ml/yi_ml_v2/`, logistic regression, 2,500 rows, 251 positives, 16 features, five leave-one-lot-out folds. Pooled calibrated out-of-fold ROC-AUC 0.4592, PR-AUC 0.0909, Brier 0.1006. A constant score of 0.1004 has Brier 0.0903. State remains CANDIDATE. `yi_ml_v1` remains ACTIVE. Production authorization remains false.

The baseline says the joint 16-feature model does not beat the base rate. The sections below separate that result by signal family.

## 3. L004 investigation

**FACT.**

| Item | Value |
| --- | --- |
| Eligible dies | 500 |
| First-pass failures | 97 |
| First-pass passes | 403 |
| Failure rate | 0.194 |
| Clock | 2026-11-07 08:00:00Z through 21:14:15Z |

Failure rate by wafer, which is also the chronological order inside the lot:

| Wafer | Dies | Failures | Rate |
| --- | --- | --- | --- |
| W01 | 100 | 6 | 0.06 |
| W02 | 100 | 9 | 0.09 |
| W03 | 100 | 11 | 0.11 |
| W04 | 100 | 26 | 0.26 |
| W05 | 100 | 45 | 0.45 |

Failure rate by equal time quartiles on that same day:

| Quartile | Dies | Failures | Rate |
| --- | --- | --- | --- |
| First | 125 | 6 | 0.048 |
| Second | 125 | 15 | 0.120 |
| Third | 125 | 22 | 0.176 |
| Fourth | 125 | 54 | 0.432 |

**PREDICTIVE ASSOCIATION.** Within L004, contract-feature AUCs and pass versus fail means:

| Feature | Within-L004 AUC | Pass mean | Fail mean |
| --- | --- | --- | --- |
| `timestamp_epoch` | 0.748 | 539,660 | 552,895 |
| `probe_fail_rate` | 0.536 | 0.100 | 0.101 |
| `temperature_c` | 0.533 | 33.06 | 34.92 |
| `voltage_v` | 0.526 | 0.801 | 0.802 |
| `die_y` / `normalized_y` | 0.525 | 5.45 / 0.495 | 5.70 / 0.522 |
| `tester_fail_rate` | 0.521 | 0.102 | 0.101 |
| `radial_distance` / `edge_distance` | 0.518 | 8.26 / 5.88 | 8.47 / 5.67 |
| `site` | 0.503 | 0.499 | 0.505 |
| `die_x` / `normalized_x` | 0.502 | 5.50 / 0.500 | 5.48 / 0.498 |

Category rates inside L004:

| Feature | Rates |
| --- | --- |
| `spatial_region` | CENTER 0.160 (100), EDGE 0.229 (105), OTHER 0.193 (295) |
| `tester_id` | T01 0.183 (235), T02 0.212 (156), T03 0.193 (109) |
| `probe_card_id` | PC01 0.186, PC02 0.173, PC03 0.226 |
| `prober_id` | PR01 0.182, PR02 0.207 |

**FACT.** The only contract feature that separates L004 failures is time. Spatial, equipment, and environment rates inside L004 sit in a narrow band around 0.19.

**PREDICTIVE ASSOCIATION.** The observed L004 pattern is temporal within the lot. It is not a spatial border pattern (border rate 0.217 versus interior 0.181) and not an equipment split (testers 0.183–0.212).

**LIMITATION.** That temporal association is not available from the other lots. See section 6. Calling the pattern a root cause is not supported.

## 4. 16-feature audit

All 16 features have zero missing values on the 2,500 eligible dies. In-sample AUC uses the full population and, for a category, that category's own failure rate. It describes association. It is not a held-out score. `tester_fail_rate` and `probe_fail_rate` are means of the label, so their in-sample AUC repeats the ID they are computed from.

| Feature | Type | Source | Cardinality | In-sample AUC | Within-L004 AUC | Redundant with | LOLO concern | Useful signal in this contract |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `die_x` | float | attempt `x` | 10 (1–10) | 0.517 | 0.502 | `normalized_x` exactly | Stable grid | No |
| `die_y` | float | attempt `y` | 10 (1–10) | 0.507 | 0.525 | `normalized_y` exactly | Stable grid | No |
| `normalized_x` | float | min-max of `x` | 10 | 0.517 | 0.502 | `die_x` | None beyond the duplicate | No |
| `normalized_y` | float | min-max of `y` | 10 | 0.507 | 0.525 | `die_y` | None beyond the duplicate | No |
| `radial_distance` | float | `hypot(x, y)` | 52 | 0.518 | 0.518 | Shares geometry with `x` and `y` (correlation 0.693 each) | Stable | Weak |
| `edge_distance` | float | `radius_max - radial_distance` | 52 | 0.518 | 0.518 | Exact negative of `radial_distance` | Stable | No extra signal |
| `spatial_region` | category | radius quantiles 5.80 and 10.77 | 3 | 0.534 | rates 0.16–0.23 | Coarse copy of radius | Quantiles stable; definition misses the border | Weak, and the wrong geometry |
| `timestamp_epoch` | float | attempt `timestamp` minus fit minimum | 2,500 | 0.559 | 0.748 | Wafer order inside a lot | Held-out lot is outside the training clock; L004 sign reverses | Yes inside L004 only |
| `temperature_c` | float | attempt `temperature_c` | 2,142 | 0.519 | 0.533 | None | Sign is small | No |
| `voltage_v` | float | attempt `voltage_v` | 469 | 0.508 | 0.526 | None | Held-out AUCs all below 0.50 | No |
| `site` | float | attempt `site` | 2 | 0.501 | 0.503 | Related to `x` parity, correlation 0.174 | No | No |
| `tester_id` | category | attempt `tester_id` | 3 | 0.535 | rates 0.183–0.212 | Same grouping as `tester_fail_rate` | Levels exist in every lot; L003-only gap transfers only partly | Modest, and not on L004 |
| `probe_card_id` | category | attempt `probe_card_id` | 3 | 0.535 | rates 0.173–0.226 | Same grouping as `probe_fail_rate` | Levels exist in every lot | Modest on L005 only |
| `prober_id` | category | attempt `prober_id` | 2 | 0.518 | rates 0.182–0.207 | None | Levels exist in every lot | No |
| `tester_fail_rate` | float | training-fold mean of the label by tester | 3 | 0.535 | 0.521 | `tester_id` | Uses labels; a lot-specific tester gap is missing when that lot is held out | No independent signal |
| `probe_fail_rate` | float | training-fold mean of the label by probe card | 3 | 0.535 | 0.536 | `probe_card_id` | Same label-aggregate limitation | No independent signal |

**FACT.** Six of the sixteen columns are duplicates or label aggregates of another column: the two normalized coordinates, `edge_distance`, and the two fail-rate columns.

## 5. Spatial investigation

**FACT.** Correlations on the 2,500-row feature matrix:

| Pair | Correlation |
| --- | --- |
| `die_x`, `normalized_x` | +1 |
| `die_y`, `normalized_y` | +1 |
| `radial_distance`, `edge_distance` | −1 |
| `die_x`, `radial_distance` | +0.693 |
| `die_y`, `radial_distance` | +0.693 |

**FACT.** Generator border is `x` in {1, 10} or `y` in {1, 10}: 900 dies. `spatial_region = EDGE` is radius at or above 10.77: overlap 325 dies (36%). Generator center is the middle of the grid: 400 dies. `spatial_region = CENTER` is radius at or below 5.80: overlap 25 dies (6%). Coordinate (1, 1) is on the border and is labeled CENTER. Coordinate (5, 5) is in the grid center and is labeled OTHER.

**PREDICTIVE ASSOCIATION.** Failure rates:

| Partition | Rate | Within-lot border AUC |
| --- | --- | --- |
| Generator border / interior | 0.131 / 0.083 | L002 0.640, L005 0.638, L003 0.547, L004 0.526, L001 0.514 |
| ML EDGE / CENTER / OTHER | 0.124 / 0.102 / 0.092 | In-sample region AUC 0.534 |

L002 border versus interior rates are 0.167 (180 dies) versus 0.059 (320 dies). L004 border versus interior rates are 0.217 versus 0.181.

The four answers in the question:

- **A. Redundant.** **FACT** for `normalized_x`, `normalized_y`, and `edge_distance`. They add no information.
- **B. Incorrect geometry.** **FACT.** `spatial_region` is distance from the origin, not the wafer border or the grid center.
- **C. Useful signal, represented poorly.** **PREDICTIVE ASSOCIATION.** The border split is large on L002 and L005. The contract features do not carry it (within-lot radial AUC about 0.52–0.58).
- **D. Little spatial signal.** Rejected for L002 and L005. Accepted for L004, where the border gap is 0.036.

**HYPOTHESIS.** A later leave-one-lot-out run that replaces the radius labels with the border indicator would move L002 more than L004. This phase did not run that model.

## 6. Temporal investigation

**FACT.** Each lot occupies one calendar day, in order, with no shared timestamps.

| Lot | First first-pass stamp | Last first-pass stamp | Within-lot timestamp AUC | Direction of the better score |
| --- | --- | --- | --- | --- |
| L001 | 2026-11-01 08:00:00Z | 2026-11-01 21:14:15Z | 0.502 | later slightly higher |
| L002 | 2026-11-03 08:00:00Z | 2026-11-03 21:14:15Z | 0.543 | earlier slightly higher |
| L003 | 2026-11-05 08:00:00Z | 2026-11-05 21:14:15Z | 0.512 | earlier slightly higher |
| L004 | 2026-11-07 08:00:00Z | 2026-11-07 21:14:15Z | 0.748 | later higher |
| L005 | 2026-11-09 08:00:00Z | 2026-11-09 21:14:15Z | 0.511 | earlier slightly higher |

**FACT.** Held-out lot timestamps fall outside the training range. The days do not overlap, so every test lot is either before or after every training die. `timestamp_epoch` subtracts the training minimum, which makes a held-out earlier lot negative and a held-out later lot a large positive extrapolation.

**PREDICTIVE ASSOCIATION.** L004 is the only lot whose failures move strongly with time. The other four within-lot AUCs are 0.50–0.54.

**LIMITATION.** Choosing the timestamp sign from the other lots and applying it to L004 produces AUC 0.252. The feature sees the L004 order only when L004 is inside the fit. Under the required split, L004 is the test lot for that pattern, and the training lots do not contain the same slope.

**HYPOTHESIS.** The positive in-sample timestamp coefficient on the saved all-data model is dominated by L004. That coefficient is not evidence the feature will rank a future lot.

## 7. Equipment investigation

**FACT.** T01, T02, T03, PC01, PC02, PC03, PR01, and PR02 each appear in every lot. Site is 250/250 in every lot. No held-out lot introduces an unseen equipment level. These columns do not encode lot identity by a private category.

Overall failure rates:

| Level | Dies | Failure rate |
| --- | --- | --- |
| T01 / T02 / T03 | 1,052 / 847 / 601 | 0.115 / 0.089 / 0.092 |
| PC01 / PC02 / PC03 | 814 / 856 / 830 | 0.103 / 0.085 / 0.113 |
| PR01 / PR02 | 1,244 / 1,256 | 0.094 / 0.107 |
| site 0 / 1 | 1,250 / 1,250 | 0.100 / 0.101 |

**PREDICTIVE ASSOCIATION.** Rates computed on the other four lots, then applied to the held-out lot (not a trained model):

| Feature | Strongest held-out lot | AUC | L004 AUC |
| --- | --- | --- | --- |
| `tester_id` | L003 | 0.605 | 0.521 |
| `probe_card_id` | L005 | 0.608 | 0.536 |
| `prober_id` | L003 | 0.532 | 0.520 |

L003 tester rates are T01 0.114, T02 0.036, T03 0.061. That gap is visible in the attempt table. The other lots still have a milder T01 elevation, which is why a rate learned without L003 retains AUC 0.605. L004's testers are all near 0.19, so the same feature does not explain L004.

**LIMITATION.** `tester_fail_rate` and `probe_fail_rate` are the label means of `tester_id` and `probe_card_id`. They are usable only to the extent those IDs repeat, and they cannot invent a gap that exists only in the held-out lot.

**PREDICTIVE ASSOCIATION.** This is an equipment-level rate difference. It is not a confirmed equipment root cause.

## 8. Environment investigation

**FACT.** `temperature_c` on first-pass attempts runs from 17.942 to 89.443 (mean 32.021). `voltage_v` runs from 0.7669 to 0.8310 (standard deviation about 0.010 around 0.80).

**PREDICTIVE ASSOCIATION.**

| Lot | Temperature AUC | Voltage AUC |
| --- | --- | --- |
| L001 | 0.557 | 0.523 |
| L002 | 0.503 | 0.518 |
| L003 | 0.513 | 0.533 |
| L004 | 0.533 | 0.526 |
| L005 | 0.522 | 0.555 |

Dies at or above 50 °C: 293, failure rate 0.113. The remaining dies: failure rate 0.099.

**FACT.** L004's temperature and voltage ranges match the other lots. The wide temperature range does not line up with the failures. The voltage range is a few tens of millivolts and does not separate pass from fail.

**LIMITATION.** Held-out univariate voltage AUCs are all below 0.50. There is no environment signal here for a later model to recover from these two columns.

## 9. Independent parametric signal investigation

**FACT.** `parametric_measurements.csv` was aggregated to the 2,500 first-pass attempts and scored against `first_pass_fail`. It was not merged into the ML feature builder. Limit-fail counts in the dataset documentation remain IDDQ 29, VMIN 28, VMAX 1, and 0 for the other five parameters. The AUCs below are shifts in the continuous value, not those rare limit breaches. CONTACT_RESISTANCE never crosses 2.5 ohm (maximum 2.260).

| Parameter | In-sample AUC | L004 AUC | L004 pass mean | L004 fail mean | Notes by lot |
| --- | --- | --- | --- | --- | --- |
| VMIN | 0.632 | 0.728 | 0.682 | 0.767 | L004 wafer means 0.619, 0.641, 0.708, 0.746, 0.780 |
| IDDQ | 0.606 | 0.671 | 36.83 | 42.22 | L004 wafer means 31.57, 35.86, 37.86, 40.02, 44.05 |
| CONTACT_RESISTANCE | 0.538 | 0.507 | 1.095 | 1.110 | L002 0.608, L003 0.638 |
| ON_RESISTANCE | 0.524 | 0.514 | 8.44 | 8.53 | All lots near 0.51–0.56 |
| VMAX | 0.522 | 0.548 | 1.183 | 1.176 | No lot above 0.55 |
| SUPPLY_CURRENT | 0.522 | 0.536 | 77.78 | 76.97 | No L004 wafer story |
| VDD | 0.521 | 0.570 | 0.799 | 0.803 | Small |
| INTERCONNECT_RESISTANCE | 0.515 | 0.569 | 4.21 | 4.04 | Not monotone with the L004 wafers |

**PREDICTIVE ASSOCIATION.** VMIN and IDDQ move with the same L004 wafer order as the failure rate. A sign chosen without L004 still scores L004 at 0.728 for VMIN and 0.671 for IDDQ, because the other lots have a weak association in the same direction. CONTACT_RESISTANCE tracks L002 and L003 and does not track L004.

**LIMITATION.** These values are stored on the first-pass attempt. They are not pre-test coordinates. They are excluded from the current contract on purpose. A continuous association is not a proposal to add the columns, and it is not a root cause.

**HYPOTHESIS.** Part of the reason the 16-feature model sits near the base rate is that the L004 shift and the L002/L003 contact shift are in this file rather than in the contract. A controlled contrast would measure that. This phase did not fit one.

## 10. Observable-signal comparison

No overall model ranking and no causal conclusion.

| Family | Observed evidence | Strength | LOLO concern | Lots | Available before the outcome is known | Future ML consideration | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A. Spatial | Border rate gap; contract region overlaps 36% of border dies | Strong on L002 and L005 for the border definition; weak for the current features | Border definition is stable across lots; current region is the wrong function of the same coordinates | L002, L005 | Yes. `x` and `y` are on the die | Worth a geometry experiment. Not worth keeping the duplicate columns | Current `spatial_region` is not that border |
| B. Temporal | L004 rate 0.06 to 0.45 by wafer; within-lot AUC 0.748 | Strong inside L004; absent elsewhere | Held-out clocks are outside training; training sign reverses L004 to AUC 0.252 | L004 only | The timestamp is known as the die is tested. The slope is not known from other lots | Do not expect the current column to fix held-out L004 | Lot clocks do not overlap |
| C. Equipment | T01 0.115 versus T02 0.089; L003 T01 0.114 versus T02 0.036; transfer AUC 0.605 | Modest | IDs repeat, so categories transfer; a gap that exists in only one lot transfers only through the milder gaps in the other lots | L003, mildly elsewhere | Yes. IDs are on the attempt | Optional contrast. Not an L004 explanation | Not a root cause. Fail-rate columns duplicate the IDs |
| D. Environment | Hot versus cool 0.113 versus 0.099; voltage AUC at or below 0.55 | Absent | Voltage sign does not survive the split | None | Yes | No | Wide temperature range, little rate difference |
| E. Parametric | VMIN and IDDQ rise across L004 wafers; contact resistance ranks L002 and L003 | Stronger than the contract on those lots | VMIN and IDDQ keep their sign on held-out L004. Several other parameters flip | L004 for VMIN/IDDQ; L002 and L003 for contact resistance | No. They are attempt measurements, not pre-test fields | A separate offline contrast only. Not an automatic contract change | Excluded today; close to the test that defines the fail |
| F. No meaningful signal | Site, prober, voltage, normalized duplicates, L001 generally | Absent | None | L001 is near chance on the contract features | — | Dropping duplicates is a control, not a fix | — |

## 11. Hidden-ground-truth offline validation

**EVALUATION-ONLY INFORMATION.** The offline file assigns L001 NONE, L002 SPATIAL.EDGE, L003 EQUIPMENT.DEGRADATION, L004 PROCESS.DRIFT, and L005 WEAK. Injection magnitudes are not copied here. None of these fields are in the ML matrix.

What is observable without that file, and how it lines up:

| Offline family | Observable counterpart | Represented in the 16 features? |
| --- | --- | --- |
| L001 NONE | Within-lot AUCs near 0.50 | Nothing to represent |
| L002 SPATIAL.EDGE | Border 0.167 versus interior 0.059 | The coordinates are present. The border is not the feature the contract builds. Overlap 36% |
| L003 EQUIPMENT.DEGRADATION | T01 0.114 versus T02 0.036; contact resistance AUC 0.638 | `tester_id` is present and partly transfers (AUC 0.605). Contact resistance is outside the contract |
| L004 PROCESS.DRIFT | Wafer rates 0.06 to 0.45; VMIN and IDDQ rise with the same wafers | `timestamp_epoch` matches inside the lot and reverses under leave-one-lot-out. VMIN and IDDQ are outside the contract |
| L005 WEAK | Border 0.117 versus interior 0.041, smaller than L002 | Same geometry gap as L002. The current region feature does not encode it |

**EVALUATION-ONLY INFORMATION.** The scenario structure is present in observable columns. The current contract represents the L004 time order only inside that lot, represents the equipment ID but not the contact-resistance shift, and does not represent the border. The hidden file was not used to compute the rates in sections 3–9.

## 12. Data and feature limitations

- **LIMITATION.** Leave-one-lot-out cannot learn a slope that exists in only the held-out lot. L004 time is that case.
- **LIMITATION.** `timestamp_epoch` extrapolates because lot clocks are disjoint.
- **LIMITATION.** Three spatial columns duplicate three others, and `spatial_region` uses the wrong geometry.
- **LIMITATION.** `tester_fail_rate` and `probe_fail_rate` are functions of the label.
- **LIMITATION.** Parametric association was measured outside the training matrix. It is not a license to join those columns.
- **LIMITATION.** Univariate AUC is not the logistic model's pooled score. A feature can rank one lot and still leave the pooled model below the base rate.
- **FACT.** Out-of-fold probability vectors for `yi_ml_v2` are still not stored. This investigation did not refit them.

## 13. What can and cannot be concluded

Can be concluded:

- **FACT.** The 16-feature contract contains one L004 separator, `timestamp_epoch`, and that separator does not keep its direction when L004 is held out.
- **FACT.** Exact duplicates are `normalized_x`, `normalized_y`, and `edge_distance`.
- **FACT.** `spatial_region` is not the wafer border.
- **PREDICTIVE ASSOCIATION.** Border membership, VMIN, IDDQ, and contact resistance carry lot-specific association that the current contract misses or mis-encodes.
- **PREDICTIVE ASSOCIATION.** Temperature, voltage, site, and prober do not.

Cannot be concluded:

- A root cause for L004, L002, or L003.
- That adding VMIN or IDDQ would make a calibrated leave-one-lot-out model beat the base rate.
- That changing `spatial_region` would do so either. That is a hypothesis for a later run.
- Any change to production authorization.

## 14. Recommended controlled experiment candidates

Not run in this phase. Each one would be a new candidate, same seed, same five lot folds, and would not replace `yi_ml_v1` or activate `yi_ml_v2`.

1. Replace radius-quantile `spatial_region` with the wafer-border indicator. Compare L002 and L005 fold metrics with the saved logistic baseline. Expect little change on L004.
2. Drop `normalized_x`, `normalized_y`, and `edge_distance` as a redundancy control. Expect little AUC change.
3. Keep timestamp in the contract. Add a negative control that scores L004 only from the other lots' time slope, which this investigation already places at AUC 0.252. Do not remove the column until that control is reviewed.
4. Offline parametric contrast, separate from `yi_ml_v2`: VMIN, IDDQ, and CONTACT_RESISTANCE only, same folds, still not activated. Use it to measure the cost of the current exclusion, not to change the exclusion by default.

## 15. No retraining and no activation

No logistic model was fit. No other model was fit. `artifacts/ml/yi_ml_v2/` and `artifacts/ml/yi_ml_v1/` were not modified. The registry was not modified. Production authorization was not changed. No other agent was invoked. The feature contract remains the same 16 names.
