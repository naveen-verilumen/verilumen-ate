# Evaluation harness (design only — no scorer implementation in this phase)

Ground truth lives ONLY under `evaluation/ground_truth/`.

```
        SYNTHETIC GENERATOR (future)
                │
        ┌───────┴────────┐
        ▼                ▼
  OBSERVABLE DATA    HIDDEN TRUTH
  data/synthetic/    evaluation/ground_truth/
  agent_visible/            │
        │                   │
        ▼                   │
  YIELD AGENT               │
  (no scenario_id,          │
   no planted_*,            │
   no true_*)               │
        │                   │
        ▼                   │
  PREDICTIONS JSON          │
        │                   │
        └────────┬──────────┘
                 ▼
         evaluation/metrics
         (future scoring)
```

V1 `invoked` for other agents is always `false`.
