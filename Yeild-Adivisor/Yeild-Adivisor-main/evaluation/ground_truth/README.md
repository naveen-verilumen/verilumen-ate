# FORBIDDEN TO AGENT RUNTIME

This directory holds **hidden** synthetic ground truth only.

The Yield Improvement Agent (`src/yield_agent/**`) must never read this path.

Allowed readers:

- `evaluation/` scoring scripts (future)
- pytest evaluation tests that load truth **after** the agent has written predictions

Forbidden in any file here from being copied into:

- `data/synthetic/agent_visible/`
- `data/processed/`
- analyze() inputs
