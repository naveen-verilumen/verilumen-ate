"""Baseline die population with realistic noise (not a planted cause)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from yield_improvement.synthetic.config import Profile, SyntheticConfig


def _parse_start(text: str) -> datetime:
    raw = text.replace("Z", "+00:00")
    ts = datetime.fromisoformat(raw)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def weighted_choice(rng: random.Random, items: list[str], weights: list[float]) -> str:
    draw = rng.random()
    acc = 0.0
    for item, weight in zip(items, weights, strict=True):
        acc += weight
        if draw <= acc:
            return item
    return items[-1]


@dataclass
class DieState:
    lot_id: str
    wafer_id: str
    die_id: str
    lot_index: int
    wafer_index_in_lot: int
    x: float
    y: float
    r: float
    tester_id: str
    probe_card_id: str
    site: int
    temperature_c: float
    fail_p: float
    timestamp: datetime
    failed: bool = False
    failure_code: str | None = None
    fail_test_ids: list[str] = field(default_factory=list)
    sequence_by_test: dict[str, int] = field(default_factory=dict)
    needs_retest: bool = False
    measurements: dict[str, float] = field(default_factory=dict)
    parametric_fail: bool = False


def wafer_grid(profile: Profile) -> list[tuple[float, float]]:
    side = profile.grid_side
    half = (side - 1) / 2.0
    coords: list[tuple[float, float]] = []
    for iy in range(side):
        for ix in range(side):
            x = ix - half
            y = iy - half
            r = math.hypot(x, y)
            if r <= profile.wafer_radius + 1e-9:
                coords.append((x, y))
    if len(coords) < profile.n_dies_per_wafer:
        raise ValueError("wafer_radius too small for n_dies_per_wafer")
    coords.sort(key=lambda p: (math.hypot(p[0], p[1]), p[0], p[1]))
    return coords[: profile.n_dies_per_wafer]


def radius_quantile(radii: list[float], q: float) -> float:
    ordered = sorted(radii)
    if not ordered:
        return 0.0
    idx = int(clip(q, 0.0, 1.0) * (len(ordered) - 1))
    return ordered[idx]


def build_baseline(cfg: SyntheticConfig, rng: random.Random, profile: Profile) -> list[DieState]:
    coords = wafer_grid(profile)
    start = _parse_start(cfg.time.start)
    lot_effects = [rng.gauss(0.0, cfg.baseline.lot_effect_sd) for _ in range(profile.n_lots)]
    tester_effects = {
        t: rng.gauss(0.0, cfg.baseline.tester_effect_sd) for t in cfg.testers
    }
    dies: list[DieState] = []
    for lot_i in range(profile.n_lots):
        lot_id = f"L{lot_i + 1:03d}"
        for w_i in range(profile.n_wafers_per_lot):
            wafer_id = f"W{w_i + 1:02d}"
            wafer_eff = rng.gauss(0.0, cfg.baseline.wafer_effect_sd)
            for d_i, (x, y) in enumerate(coords):
                die_id = f"D{d_i + 1:03d}"
                tester = weighted_choice(rng, cfg.testers, cfg.tester_weights)
                card = rng.choice(cfg.probe_cards)
                # Temperature not tied 1:1 to tester/lot: hash-like mix of indices.
                temp = cfg.temperatures_c[(lot_i + w_i + d_i + hash_int(rng, 3)) % len(cfg.temperatures_c)]
                site = rng.choice(cfg.sites)
                die_noise = rng.gauss(0.0, cfg.baseline.die_noise_sd)
                p = clip(
                    cfg.baseline.p_fail
                    + lot_effects[lot_i]
                    + wafer_eff
                    + tester_effects[tester]
                    + die_noise,
                    0.001,
                    0.85,
                )
                ts = start + timedelta(
                    days=cfg.time.days_per_lot * lot_i,
                    hours=cfg.time.hours_per_wafer * w_i,
                    seconds=cfg.time.seconds_per_die * d_i,
                )
                seq = {t.test_id: t.sequence_index for t in cfg.tests}
                dies.append(
                    DieState(
                        lot_id=lot_id,
                        wafer_id=wafer_id,
                        die_id=die_id,
                        lot_index=lot_i,
                        wafer_index_in_lot=w_i,
                        x=x,
                        y=y,
                        r=math.hypot(x, y),
                        tester_id=tester,
                        probe_card_id=card,
                        site=site,
                        temperature_c=float(temp),
                        fail_p=p,
                        timestamp=ts,
                        sequence_by_test=seq,
                    )
                )
    return dies


def hash_int(rng: random.Random, modulo: int) -> int:
    return rng.randrange(modulo)
