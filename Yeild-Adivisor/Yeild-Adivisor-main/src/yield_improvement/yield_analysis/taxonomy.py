"""Taxonomy mapping from failure_code / bin. Never guess FAMILY from similar strings."""

from __future__ import annotations

from yield_improvement.config.loader import AppConfig


def map_taxonomy(
    config: AppConfig,
    *,
    failure_code: str | None = None,
    sbin: int | None = None,
    hbin: int | None = None,
) -> str:
    unmapped = config.bin_map.unmapped_behavior
    if failure_code:
        mapped = config.bin_map.failure_code_map.get(failure_code)
        if mapped:
            return mapped
        return unmapped.unknown_failure_code
    if sbin is not None:
        row = config.bin_map.sbin_by_number().get(sbin)
        if row is not None:
            return row.taxonomy_code or "UNKNOWN.UNSPECIFIED"
        return unmapped.unknown_sbin
    if hbin is not None:
        row = config.bin_map.hbin_by_number().get(hbin)
        if row is not None:
            return row.taxonomy_code or "UNKNOWN.UNSPECIFIED"
        return unmapped.unknown_sbin
    return "UNKNOWN.UNSPECIFIED"


def split_taxonomy(config: AppConfig, code: str) -> tuple[str, str]:
    return config.taxonomy.split(code)


def sbin_disposition(config: AppConfig, sbin: int | None) -> str | None:
    if sbin is None:
        return None
    row = config.bin_map.sbin_by_number().get(sbin)
    if row is None:
        return None
    return row.disposition
