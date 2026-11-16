"""Canonical hypothesis identity and associative statements. Not causal claims."""

from __future__ import annotations

from yield_improvement.detectors.contract import DetectorResult

# Detector → taxonomy identity. Group labels (T03, L004) stay in affected_population,
# not in identity, so two testers still compose one EQUIPMENT.DEGRADATION hypothesis.
DETECTOR_IDENTITY: dict[str, tuple[str, str]] = {
    "spatial": ("SPATIAL", None),  # detail from detector (BORDER/INNER or EDGE/CENTER/RING)
    "equipment": ("EQUIPMENT", "DEGRADATION"),
    "temporal": ("PROCESS", "DRIFT"),
    "temperature": ("ENVIRONMENT", "TEMPERATURE"),
    "parametric": ("PARAMETRIC", "SHIFT"),
    "near_limit": ("TEST", "LIMIT_SENSITIVITY"),
    "sequence": ("TEST", "SEQUENCE"),
    "contact": ("CONTACT", "PROBE"),
    "lot": ("PROCESS", "LOT_VARIATION"),
    "wafer": ("PROCESS", "WAFER_VARIATION"),
    "correlation": ("CORRELATED", "FAILURES"),
}

# Nested grain: child detector is not an independent view of parent.
# Lot rate is the time grain of drift; wafer is nested in lot/spatial; etc.
CORRELATED_PARENTS: dict[str, tuple[str, ...]] = {
    "lot": ("temporal",),
    "wafer": ("temporal", "lot", "spatial"),
    "contact": ("equipment",),
    "near_limit": ("parametric",),
}

STATEMENTS: dict[tuple[str, str], str] = {
    ("SPATIAL", "BORDER"): "Yield loss is associated with dies on the outer grid boundary.",
    ("SPATIAL", "INNER"): "Yield loss is associated with dies inside the outer grid boundary.",
    ("SPATIAL", "EDGE"): "Yield loss is associated with wafer-edge location.",
    ("SPATIAL", "CENTER"): "Yield loss is associated with wafer-center location.",
    ("SPATIAL", "RING"): "Yield loss is associated with a radial ring on the wafer map.",
    ("EQUIPMENT", "DEGRADATION"): "Yield loss is associated with equipment identity.",
    ("PROCESS", "DRIFT"): "Yield loss is associated with temporal process drift.",
    ("ENVIRONMENT", "TEMPERATURE"): "Yield loss is associated with test temperature.",
    ("PARAMETRIC", "SHIFT"): "Yield loss is associated with a parametric distribution shift.",
    ("TEST", "LIMIT_SENSITIVITY"): "Yield loss is associated with measurements concentrating near a test limit.",
    ("TEST", "SEQUENCE"): "Yield loss is associated with test sequence / preceding-test state.",
    ("CONTACT", "PROBE"): "Yield loss is associated with probe/contact identity.",
    ("PROCESS", "LOT_VARIATION"): "Yield loss is associated with lot identity.",
    ("PROCESS", "WAFER_VARIATION"): "Yield loss is associated with wafer identity.",
    ("CORRELATED", "FAILURES"): "Two failure modes are statistically associated (association, not causation).",
}

VALIDATION: dict[str, list[str]] = {
    "SPATIAL": [
        "Confirm the map pattern on additional lots and wafers.",
        "Check wafer-map repeatability; do not change production limits.",
    ],
    "EQUIPMENT": [
        "Compare matched lots run on the associated equipment versus controls.",
        "Review maintenance / probe-card history; this is not a production action.",
    ],
    "PROCESS": [
        "Check process or recipe changes near the time window.",
        "Separate lot/wafer nesting from a true time trend on independent material.",
    ],
    "ENVIRONMENT": [
        "Repeat under matched temperature conditions across lots and equipment.",
    ],
    "PARAMETRIC": [
        "Confirm the distribution shift on an independent sample.",
    ],
    "TEST": [
        "If sequence-related, confirm under controlled execution (stop-on-fail censors later tests).",
        "If limit-related, review guardband with engineering; do not modify production test limits from this hypothesis.",
    ],
    "CONTACT": [
        "Compare probe cards / contact hardware on matched lots.",
    ],
    "CORRELATED": [
        "Confirm co-occurrence under continue-on-fail or designed pairing; stop-on-fail biases pairs.",
    ],
}


def identity_for(detector: str, result: DetectorResult) -> tuple[str, str] | None:
    if detector == "no_signal" or result.status != "SIGNAL":
        return None
    spec = DETECTOR_IDENTITY.get(detector)
    if spec is None:
        if result.hypothesis_family and result.hypothesis_detail:
            return (result.hypothesis_family, result.hypothesis_detail)
        return None
    family, detail = spec
    if family == "SPATIAL":
        if not result.hypothesis_detail:
            return None
        return (family, result.hypothesis_detail)
    return (family, detail)


def hypothesis_id(family: str, detail: str) -> str:
    return f"H-{family}.{detail}"


def statement_for(family: str, detail: str, affected: dict | None) -> str:
    base = STATEMENTS.get((family, detail), f"Yield loss is associated with {family}.{detail}.")
    label = None
    if affected:
        label = affected.get("label") or affected.get("group")
    if family == "EQUIPMENT" and label:
        return f"Yield loss is associated with equipment identity ({label})."
    if family == "CONTACT" and label:
        return f"Yield loss is associated with probe/contact identity ({label})."
    if family == "PROCESS" and detail == "LOT_VARIATION" and label:
        return f"Yield loss is associated with lot identity ({label})."
    if family == "PROCESS" and detail == "WAFER_VARIATION" and label:
        return f"Yield loss is associated with wafer identity ({label})."
    return base
