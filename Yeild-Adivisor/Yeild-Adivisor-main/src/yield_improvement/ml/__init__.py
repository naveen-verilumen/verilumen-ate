"""First-pass-failure ML layer. Predictive evidence only."""

__all__ = ["run_ml", "attach_ml_evidence", "MLResult"]


def __getattr__(name: str):
    if name == "run_ml":
        from yield_improvement.ml.pipeline import run_ml

        return run_ml
    if name == "attach_ml_evidence":
        from yield_improvement.ml.evidence import attach_ml_evidence

        return attach_ml_evidence
    if name == "MLResult":
        from yield_improvement.ml.contracts import MLResult

        return MLResult
    raise AttributeError(name)
