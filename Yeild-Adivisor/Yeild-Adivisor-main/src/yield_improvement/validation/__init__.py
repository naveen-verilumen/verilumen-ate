"""Phase 1 data-quality helpers plus Phase 6 advisory validation."""

from yield_improvement.validation.quality import collect_quality_issues

__all__ = [
    "collect_quality_issues",
    "validate_from_dir",
    "validate_opportunities",
]


def __getattr__(name: str):
    # Lazy: validator imports compose; composer → pipeline → this package.
    if name in {"validate_from_dir", "validate_opportunities"}:
        from yield_improvement.validation.validator import (
            validate_from_dir,
            validate_opportunities,
        )

        return validate_from_dir if name == "validate_from_dir" else validate_opportunities
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
