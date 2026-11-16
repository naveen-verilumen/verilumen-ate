"""Phase 7 reporting. Presentation of Phase 1–6 results only."""

__all__ = [
    "EngineeringReport",
    "build_report_from_dir",
    "write_reports",
]


def __getattr__(name: str):
    if name == "EngineeringReport":
        from yield_improvement.reporting.contract import EngineeringReport

        return EngineeringReport
    if name == "build_report_from_dir":
        from yield_improvement.reporting.adapter import build_report_from_dir

        return build_report_from_dir
    if name == "write_reports":
        from yield_improvement.reporting.renderer import write_reports

        return write_reports
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
