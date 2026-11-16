"""Streamlit dashboard. Presentation of EngineeringReport only."""

__all__ = ["main"]


def __getattr__(name: str):
    if name == "main":
        from yield_improvement.dashboard.app import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
