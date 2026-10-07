"""Statistics with the standard library only: percentiles, concentration, bootstrap CIs (seeded, so reports are
deterministic), binomial / Wilson, Fisher's exact test, Mann-Whitney U, a Cochran-Armitage trend test (one- or
two-sided, with the slope's interval), and (WP-11) chi-square independence, two proportions, a bootstrap difference
and sample sizes."""
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
    score rises (one-sided); `increasing` the other side; `two-sided` either (WP-11: X2's rule goes in both
    directions). Returns z, p, the fitted slope per score unit (least squares on proportions) and its 95% interval
    (`slope_ci95`, from the groups' own binomial variances), and both one-sided p values (`p_decreasing`,
    `p_increasing`)."""
    g = [(s, k, n) for s, k, n in groups if n > 0]
    if len(g) < 2:
        return None
    N = sum(n for _, _, n in g)
    K = sum(k for _, k, _ in g)
    p = K / N
    sbar = sum(s * n for s, _, n in g) / N
    t = sum(k * (s - sbar) for s, k, _ in g)
    var = p * (1 - p) * sum(n * (s - sbar) ** 2 for s, _, n in g)
    sxx = sum(n * (s - sbar) ** 2 for s, _, n in g)
    if var <= 0 or sxx <= 0:
        return {"z": 0, "p": 1.0, "slope": 0, "slope_ci95": None, "p_decreasing": 1.0, "p_increasing": 1.0}
    z = t / math.sqrt(var)
    p_dec, p_inc = _norm_sf(-z), _norm_sf(z)
    pval = {"decreasing": p_dec, "increasing": p_inc}.get(alternative, min(1.0, 2 * _norm_sf(abs(z))))
    slope = sum(n * (s - sbar) * (k / n - p) for s, k, n in g) / sxx
    se = math.sqrt(sum(n * (s - sbar) ** 2 * (k / n) * (1 - k / n) for s, k, n in g)) / sxx
    return {"z": _clean(z), "p": _clean(pval), "slope": _clean(slope), "slope_ci95": [_clean(slope - 1.959964 * se), _clean(slope + 1.959964 * se)],
            "p_decreasing": _clean(p_dec), "p_increasing": _clean(p_inc)}


def _chi2_sf(chi: float, df: int) -> float:
    """Upper tail of the chi-square distribution (Wilson-Hilferty)."""
    k = max(1, df)
    if chi <= 0:
        return 1.0
    z = ((chi / k) ** (1 / 3) - (1 - 2 / (9 * k))) / math.sqrt(2 / (9 * k))
    return _norm_sf(z)


def chi_square_independence(table: dict) -> dict | None:
    """Independence of rows and columns of {row: {col: count}} (chi-square, p by Wilson-Hilferty): e.g. an experiment's
    arm against the band or the trigger kind. None when it has fewer than two rows or columns with counts."""
    rows = {r: {c: v for c, v in cols.items() if v} for r, cols in table.items()}
    rows = {r: c for r, c in rows.items() if c}
    cols = sorted({c for cs in rows.values() for c in cs}, key=str)
    if len(rows) < 2 or len(cols) < 2:
        return None
    rt = {r: sum(cs.values()) for r, cs in rows.items()}
    ct = {c: sum(cs.get(c, 0) for cs in rows.values()) for c in cols}
    n = sum(rt.values())
    chi = 0.0
    for r, cs in rows.items():
        for c in cols:
            e = rt[r] * ct[c] / n
            chi += (cs.get(c, 0) - e) ** 2 / e
    df = (len(rows) - 1) * (len(cols) - 1)
    return {"chi2": _clean(chi), "df": df, "p": _clean(_chi2_sf(chi, df)), "n": n}


def two_proportions(k1: int, n1: int, k2: int, n2: int) -> dict | None:
    """Arm 1 against arm 2: the difference of proportions with its 95% interval (unpooled), the pooled z test's
    two-sided p and both one-sided p (`p_less`: arm 1's proportion is lower), and Fisher's exact two-sided p."""
    if not n1 or not n2:
        return None
    p1, p2 = k1 / n1, k2 / n2
    pp = (k1 + k2) / (n1 + n2)
    se0 = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z = (p1 - p2) / se0 if se0 > 0 else 0.0
    return {"diff": _clean(p1 - p2), "ci95": [_clean(p1 - p2 - 1.959964 * se), _clean(p1 - p2 + 1.959964 * se)], "z": _clean(z),
            "p_two": _clean(min(1.0, 2 * _norm_sf(abs(z)))), "p_less": _clean(1 - _norm_sf(z)), "p_greater": _clean(_norm_sf(z)),
            "fisher_p": _clean(fisher_exact(k1, n1 - k1, k2, n2 - k2)), "rel": _clean(p1 / p2 - 1) if p2 > 0 else None}


def bootstrap_diff_ci(xs: list, ys: list, n: int = 2000, alpha: float = 0.05, seed: int = 0):
    """95% bootstrap interval of mean(xs) - mean(ys) (seeded: deterministic)."""
    if not xs or not ys:
        return None
    rng = random.Random(seed)
    a, b = len(xs), len(ys)
    vals = sorted(sum(xs[rng.randrange(a)] for _ in range(a)) / a - sum(ys[rng.randrange(b)] for _ in range(b)) / b for _ in range(n))
    return [_clean(vals[int(alpha / 2 * n)]), _clean(vals[min(n - 1, int((1 - alpha / 2) * n))])]


Z_975, Z_95, Z_80 = 1.959964, 1.644854, 0.841621


def n_per_arm(p1: float, p2: float, two_sided: bool = True) -> int | None:
    """Sends per arm to tell proportions p1 and p2 apart (alpha 0.05, power 80%; normal approximation)."""
    if p1 == p2 or not (0 < p1 < 1) or not (0 < p2 < 1):
        return None
    za = Z_975 if two_sided else Z_95
    pb = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pb * (1 - pb)) + Z_80 * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(num / (p1 - p2) ** 2))


def mde_rel(p0: float, n: int, two_sided: bool = True):
    """The smallest relative change of a proportion p0 that n sends per arm detect (alpha 0.05, power 80%), upward."""
    if not n or not (0 < p0 < 1):
        return None
    lo, hi = 0.0, 50.0
    for _ in range(60):
        mid = (lo + hi) / 2
        p1 = min(0.999999, p0 * (1 + mid))
        need = n_per_arm(p1, p0, two_sided)
        if need is not None and need <= n:
            hi = mid
        else:
            lo = mid
    return _clean(round(hi, 4))


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
