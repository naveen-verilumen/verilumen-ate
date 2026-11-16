"""sklearn model factories. Fit preprocessing on training rows only."""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from yield_improvement.ml.config import MLAppConfig


def make_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    transformers = []
    if numeric:
        transformers.append(("num", numeric_pipe, numeric))
    if categorical:
        transformers.append(("cat", categorical_pipe, categorical))
    return ColumnTransformer(transformers=transformers, remainder="drop")


def make_model(name: str, cfg: MLAppConfig, seed: int, numeric: list[str], categorical: list[str]) -> Pipeline:
    pre = make_preprocessor(numeric, categorical)
    if name == "logistic":
        clf = LogisticRegression(
            class_weight=cfg.models.logistic.class_weight,
            max_iter=cfg.models.logistic.max_iter,
            random_state=seed,
            solver="lbfgs",
        )
    elif name == "random_forest":
        clf = RandomForestClassifier(
            n_estimators=cfg.models.random_forest.n_estimators,
            min_samples_leaf=cfg.models.random_forest.min_samples_leaf,
            class_weight=cfg.models.random_forest.class_weight,
            max_depth=cfg.models.random_forest.max_depth,
            random_state=seed,
            n_jobs=1,
        )
    elif name == "hist_gbm":
        clf = HistGradientBoostingClassifier(
            max_depth=cfg.models.hist_gbm.max_depth,
            learning_rate=cfg.models.hist_gbm.learning_rate,
            max_iter=cfg.models.hist_gbm.max_iter,
            min_samples_leaf=cfg.models.hist_gbm.min_samples_leaf,
            random_state=seed,
        )
    else:
        raise ValueError(name)
    return Pipeline([("pre", pre), ("clf", clf)])


MODEL_ORDER = ("logistic", "random_forest", "hist_gbm")
SIMPLICITY = {"logistic": 0, "random_forest": 1, "hist_gbm": 2}
