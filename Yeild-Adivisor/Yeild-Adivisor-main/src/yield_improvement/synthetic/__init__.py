"""Standalone synthetic dataset generator with hidden ground truth."""

from yield_improvement.synthetic.config import load_synthetic_config
from yield_improvement.synthetic.generator import generate_core_scenarios, generate_dataset
from yield_improvement.synthetic.scenarios import CORE_SCENARIOS

__all__ = [
    "CORE_SCENARIOS",
    "generate_core_scenarios",
    "generate_dataset",
    "load_synthetic_config",
]
