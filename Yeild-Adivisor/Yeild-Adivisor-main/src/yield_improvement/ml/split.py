"""Lot-grouped splits. Dies from the same lot never cross the train/test boundary."""

from __future__ import annotations

import numpy as np
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

from yield_improvement.ml.config import MLAppConfig


def make_splits(groups: np.ndarray, cfg: MLAppConfig):
    unique = np.unique(groups)
    n_lots = int(unique.size)
    if n_lots < 2:
        raise ValueError("Need at least two lots for group-aware evaluation")
    if n_lots <= cfg.split.max_lolo_lots:
        splitter = LeaveOneGroupOut()
        strategy = "leave_one_lot_out"
        splits = list(splitter.split(np.zeros(len(groups)), groups=groups))
    else:
        k = min(cfg.split.fallback_group_kfold_splits, n_lots)
        splitter = GroupKFold(n_splits=k)
        strategy = f"group_kfold_{k}"
        splits = list(splitter.split(np.zeros(len(groups)), groups=groups))
    for train_idx, test_idx in splits:
        train_lots = set(groups[train_idx])
        test_lots = set(groups[test_idx])
        if train_lots & test_lots:
            raise ValueError("lot leakage across train/test")
    return strategy, splits
