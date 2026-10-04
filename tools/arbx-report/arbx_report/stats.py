"""Statistics with the standard library only: percentiles, concentration, bootstrap CIs (seeded, so reports are
deterministic), binomial / Wilson, Fisher's exact test, Mann-Whitney U, and a one-sided Cochran-Armitage trend test."""
from __future__ import annotations

import math
import random


def quantile(xs: list, q: float):
    """Linear interpolation between order statistics (numpy's default). None for an empty list."""
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    v = s[lo] + (s[hi] - s[lo]) * (pos - lo)
    return _clean(v)


def _clean(v):
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 2 ** 53:
            return int(v)
        return round(v, 6)
    return v


def pct(xs: list, window: str = "segment") -> dict:
    """{window, n, p50, p90, p99} (MEASUREMENT §2.2 percentile shape)."""
    return {"window": window, "n": len(xs), "p50": quantile(xs, 0.5), "p90": quantile(xs, 0.9), "p99": quantile(xs, 0.99)}


def quantile_counts(counts: dict, q: float):
    """Quantile of a {value: count} histogram, same interpolation as `quantile` (exact, bounded memory)."""
    n = sum(counts.values())
    if not n:
        return None
    keys = sorted(counts)
    pos = q * (n - 1)
    lo_i = int(math.floor(pos))
    frac = pos - lo_i

    def nth(i):
        c = 0
        for k in keys:
            c += counts[k]
            if i < c:
                return k
        return keys[-1]

    a = nth(lo_i)
    b = nth(min(lo_i + 1, n - 1))
    return _clean(a + (b - a) * frac)


def pct_counts(counts: dict, window: str = "segment") -> dict:
    return {"window": window, "n": sum(counts.values()), "p50": quantile_counts(counts, 0.5),
            "p90": quantile_counts(counts, 0.9), "p99": quantile_counts(counts, 0.99)}


def money_summary(values: list) -> dict:
    """Totals beside medians and concentration (§6.2 rule 10): a single jackpot is flagged when the top-1 share of
    the gross positive total exceeds 50%."""
    n = len(values)
    tot = sum(values)
    pos = [v for v in values if v > 0]
    top1 = max(pos) if pos else None
    share = (top1 / sum(pos)) if pos and sum(pos) > 0 else None
    return {"n": n, "total": tot, "median": quantile(values, 0.5), "mean": _clean(tot / n) if n else None,
            "top1": top1, "top1_share": _clean(share) if share is not None else None,
            "jackpot_flag": bool(share is not None and share > 0.5)}


def bootstrap_ci(xs: list, stat=lambda v: sum(v) / len(v), n: int = 2000, alpha: float = 0.05, seed: int = 0):
    if not xs:
        return None
    rng = random.Random(seed)
    m = len(xs)
    vals = sorted(stat([xs[rng.randrange(m)] for _ in range(m)]) for _ in range(n))
    return [_clean(vals[int(alpha / 2 * n)]), _clean(vals[min(n - 1, int((1 - alpha / 2) * n))])]


def wilson(k: int, n: int, z: float = 1.959964) -> list | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [_clean(max(0.0, c - h)), _clean(min(1.0, c + h))]


def _lchoose(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def binom_pmf(k, n, p):
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    return math.exp(_lchoose(n, k) + k * math.log(p) + (n - k) * math.log(1 - p))


def binom_test(k: int, n: int, p: float, alternative: str = "two-sided") -> float:
    if n == 0:
        return 1.0
    if alternative == "less":
        return min(1.0, sum(binom_pmf(i, n, p) for i in range(0, k + 1)))
    if alternative == "greater":
        return min(1.0, sum(binom_pmf(i, n, p) for i in range(k, n + 1)))
    pk = binom_pmf(k, n, p)
    return min(1.0, sum(x for x in (binom_pmf(i, n, p) for i in range(n + 1)) if x <= pk * (1 + 1e-7)))


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]]."""
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2

    def p_of(x):
        return math.exp(_lchoose(r1, x) + _lchoose(r2, c1 - x) - _lchoose(n, c1))

    lo, hi = max(0, c1 - r2), min(r1, c1)
    p0 = p_of(a)
    return min(1.0, sum(p_of(x) for x in range(lo, hi + 1) if p_of(x) <= p0 * (1 + 1e-7)))


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def mann_whitney(x: list, y: list, alternative: str = "two-sided") -> dict | None:
    """U test with tie correction and normal approximation (fine for n >= 20 per arm)."""
    if not x or not y:
        return None
    allv = sorted([(v, 0) for v in x] + [(v, 1) for v in y])
    ranks = [0.0] * len(allv)
    i = 0
    ties = 0.0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    n1, n2 = len(x), len(y)
    r1 = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    n = n1 + n2
    sigma = math.sqrt(n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1)))) if n > 1 else 0
    if sigma == 0:
        return {"u": _clean(u1), "z": 0, "p": 1.0}
    z = (u1 - mu) / sigma
    if alternative == "greater":
        p = _norm_sf(z)
    elif alternative == "less":
        p = 1 - _norm_sf(z)
    else:
        p = 2 * _norm_sf(abs(z))
    return {"u": _clean(u1), "z": _clean(z), "p": _clean(min(1.0, p))}


def cochran_armitage(groups: list, alternative: str = "decreasing") -> dict | None:
    """Trend in proportions over ordered groups [(score, successes, n)]. `decreasing`: the proportion falls as the
    score rises (one-sided). Returns z, p and the fitted slope per score unit (least squares on proportions)."""
    g = [(s, k, n) for s, k, n in groups if n > 0]
    if len(g) < 2:
        return None
    N = sum(n for _, _, n in g)
    K = sum(k for _, k, _ in g)
    p = K / N
    sbar = sum(s * n for s, _, n in g) / N
    t = sum(k * (s - sbar) for s, k, _ in g)
    var = p * (1 - p) * sum(n * (s - sbar) ** 2 for s, _, n in g)
    if var <= 0:
        return {"z": 0, "p": 1.0, "slope": 0}
    z = t / math.sqrt(var)
    pval = _norm_sf(-z) if alternative == "decreasing" else _norm_sf(z)
    sxx = sum(n * (s - sbar) ** 2 for s, _, n in g)
    slope = sum(n * (s - sbar) * (k / n - p) for s, k, n in g) / sxx
    return {"z": _clean(z), "p": _clean(pval), "slope": _clean(slope)}


def chi_square_balance(counts: dict, weights: dict) -> dict | None:
    """Randomization balance: observed arm counts against the configured weights (chi-square, p by Wilson-Hilferty)."""
    tot = sum(counts.values())
    wsum = sum(weights.values())
    if not tot or not wsum:
        return None
    chi = 0.0
    for arm, w in weights.items():
        e = tot * w / wsum
        if e > 0:
            chi += (counts.get(arm, 0) - e) ** 2 / e
    k = max(1, len(weights) - 1)
    z = ((chi / k) ** (1 / 3) - (1 - 2 / (9 * k))) / math.sqrt(2 / (9 * k))
    return {"chi2": _clean(chi), "df": k, "p": _clean(_norm_sf(z))}
