"""Pure-Python statistical helpers. No ML. No scipy dependency."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ProportionCompare:
    n1: int
    fails1: int
    n2: int
    fails2: int
    rate1: float
    rate2: float
    rate_diff: float
    risk_ratio: float | None
    odds_ratio: float | None
    cohens_h: float
    p_value: float
    method: str
    statistic: float | None


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_normal_p(z: float) -> float:
    return 2.0 * (1.0 - _phi(abs(z)))


def candidate(calibration_parameters: dict, key: str) -> float:
    spec = calibration_parameters[key]
    if isinstance(spec, dict) and "candidate" in spec:
        return spec["candidate"]
    raise KeyError(f"calibration parameter {key} has no candidate")


def benjamini_hochberg(p_values: list[float | None], q: float) -> list[float | None]:
    """Return BH-adjusted p-values (positive FDR control). None stays None."""
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None and math.isfinite(p)]
    m = len(indexed)
    adjusted: list[float | None] = [None] * len(p_values)
    if m == 0:
        return adjusted
    indexed.sort(key=lambda t: t[1])
    running = 1.0
    ranked: list[tuple[int, float]] = []
    for rank_from_end, (idx, p) in enumerate(reversed(indexed), start=0):
        k = m - rank_from_end
        running = min(running, p * m / k)
        ranked.append((idx, min(1.0, running)))
    for idx, value in ranked:
        adjusted[idx] = value
    return adjusted


def _cohens_h(p1: float, p2: float) -> float:
    p1 = min(1.0, max(0.0, p1))
    p2 = min(1.0, max(0.0, p2))
    return 2.0 * math.asin(math.sqrt(p1)) - 2.0 * math.asin(math.sqrt(p2))


def _binom_log(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """2×2 Fisher exact two-sided p-value (hypergeometric)."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    r1 = a + b
    c1 = a + c
    lo = max(0, r1 + c1 - n)
    hi = min(r1, c1)

    def table_p(aa: int) -> float:
        bb = r1 - aa
        cc = c1 - aa
        dd = n - aa - bb - cc
        if min(aa, bb, cc, dd) < 0:
            return 0.0
        return math.exp(
            _binom_log(r1, aa) + _binom_log(n - r1, c1 - aa) - _binom_log(n, c1)
        )

    p_obs = table_p(a)
    total = 0.0
    for aa in range(lo, hi + 1):
        p = table_p(aa)
        if p <= p_obs + 1e-15:
            total += p
    return min(1.0, max(0.0, total))


def chi_square_independence(rows: list[list[int]]) -> tuple[float, float]:
    """Return (stat, p) for an r×c table. df=(r-1)(c-1)."""
    r = len(rows)
    c = len(rows[0]) if rows else 0
    if r < 2 or c < 2:
        return 0.0, 1.0
    row_tot = [sum(row) for row in rows]
    col_tot = [sum(rows[i][j] for i in range(r)) for j in range(c)]
    n = sum(row_tot)
    if n == 0 or any(t == 0 for t in row_tot + col_tot):
        return 0.0, 1.0
    stat = 0.0
    for i in range(r):
        for j in range(c):
            expected = row_tot[i] * col_tot[j] / n
            if expected <= 0:
                continue
            diff = rows[i][j] - expected
            stat += diff * diff / expected
    df = (r - 1) * (c - 1)
    p = chi_square_sf(stat, df)
    return stat, p


def chi_square_sf(stat: float, df: int) -> float:
    """Upper tail of chi-square via regularized gamma Q."""
    if stat <= 0 or df <= 0:
        return 1.0
    return _gamma_q(df / 2.0, stat / 2.0)


def _gamma_q(a: float, x: float) -> float:
    """Regularized gamma Q(a,x) = 1 - P(a,x)."""
    if x < 0 or a <= 0:
        return 1.0
    if x < a + 1:
        return 1.0 - _gamma_p_series(a, x)
    return _gamma_q_contfrac(a, x)


def _gamma_p_series(a: float, x: float) -> float:
    eps = 1e-12
    term = 1.0 / a
    total = term
    for n in range(1, 200):
        term *= x / (a + n)
        total += term
        if abs(term) < abs(total) * eps:
            break
    log_p = math.log(total) + a * math.log(x) - x - math.lgamma(a)
    try:
        return math.exp(log_p)
    except OverflowError:
        return 0.0


def _gamma_q_contfrac(a: float, x: float) -> float:
    eps = 1e-12
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, 200):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    log_q = math.log(h) + a * math.log(x) - x - math.lgamma(a)
    try:
        return math.exp(log_q)
    except OverflowError:
        return 0.0


def compare_proportions(fails1: int, n1: int, fails2: int, n2: int) -> ProportionCompare:
    rate1 = (fails1 / n1) if n1 else 0.0
    rate2 = (fails2 / n2) if n2 else 0.0
    diff = rate1 - rate2
    rr = (rate1 / rate2) if rate2 > 0 else (float("inf") if rate1 > 0 else None)
    def _odds(f: int, n: int) -> float | None:
        p = n - f
        if p == 0 or f == 0:
            return None
        return f / p

    o1, o2 = _odds(fails1, n1), _odds(fails2, n2)
    oddsr = (o1 / o2) if (o1 is not None and o2 is not None and o2 != 0) else None
    h = _cohens_h(rate1, rate2)
    cells = [fails1, n1 - fails1, fails2, n2 - fails2]
    expected_small = False
    n = n1 + n2
    if n > 0 and n1 > 0 and n2 > 0:
        p = (fails1 + fails2) / n
        for exp in (n1 * p, n1 * (1 - p), n2 * p, n2 * (1 - p)):
            if exp < 5:
                expected_small = True
                break
    if min(n1, n2) == 0:
        return ProportionCompare(n1, fails1, n2, fails2, rate1, rate2, diff, rr, oddsr, h, 1.0, "none", None)
    if expected_small or min(cells) < 5:
        p = fisher_exact_two_sided(fails1, n1 - fails1, fails2, n2 - fails2)
        return ProportionCompare(n1, fails1, n2, fails2, rate1, rate2, diff, rr, oddsr, h, p, "fisher_exact", None)
    p_pool = (fails1 + fails2) / n
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return ProportionCompare(n1, fails1, n2, fails2, rate1, rate2, diff, rr, oddsr, h, 1.0, "two_proportion_z", 0.0)
    z = (rate1 - rate2) / se
    p = two_sided_normal_p(z)
    return ProportionCompare(n1, fails1, n2, fails2, rate1, rate2, diff, rr, oddsr, h, p, "two_proportion_z", z)


def ks_two_sample(x: list[float], y: list[float]) -> tuple[float, float]:
    """Two-sample KS statistic D and approximate two-sided p-value."""
    if not x or not y:
        return 0.0, 1.0
    sx = sorted(x)
    sy = sorted(y)
    n1, n2 = len(sx), len(sy)
    i = j = 0
    d = 0.0
    while i < n1 and j < n2:
        if sx[i] <= sy[j]:
            i += 1
        else:
            j += 1
        d = max(d, abs(i / n1 - j / n2))
    while i < n1:
        i += 1
        d = max(d, abs(i / n1 - j / n2))
    while j < n2:
        j += 1
        d = max(d, abs(i / n1 - j / n2))
    en = math.sqrt(n1 * n2 / (n1 + n2))
    lam = (en + 0.12 + 0.11 / en) * d
    p = 0.0
    for k in range(1, 80):
        p += (-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam)
    p = min(1.0, max(0.0, 2.0 * p))
    return d, p


def mann_kendall(values: list[float]) -> tuple[float, float]:
    """Mann-Kendall tau and two-sided normal p-value. No seasonal correction."""
    n = len(values)
    if n < 3:
        return 0.0, 1.0
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = values[j] - values[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if var_s <= 0:
        return 0.0, 1.0
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    tau = s / (n * (n - 1) / 2.0)
    return tau, two_sided_normal_p(z)


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    m = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[m]
    return 0.5 * (ordered[m - 1] + ordered[m])


def mad(values: list[float]) -> float:
    if not values:
        return 0.0
    med = median(values)
    return median([abs(v - med) for v in values])
