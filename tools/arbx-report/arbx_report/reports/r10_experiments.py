"""R10 Experiments (MEASUREMENT.md §6.4; thresholds are R §5's, fixed before the run).

Randomization balance first. X2 delay, X4 tip share, X5 BAM/Jito landing ratio, X8 discovery connection, X9 verifier
latency, and the margin arm. Arms come from `attempts.experiments` / `decisions.experiments`."""
from __future__ import annotations

from .. import stats
from . import incomplete, ratio, section

X2_SLOPE_PER_10MS = -0.05  # would-fail must fall by >= 5 points per 10 ms
X4_MAX_REL_DROP = 0.20
X5_MIN_RATIO, X5_MIN_ELIGIBLE = 0.5, 200
X8_P50_MS, X8_P90_MS = 1.0, 5.0
X9_P99_MS = 3.0


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _arms(seg, name: str) -> dict:
    out: dict = {}
    for a in seg.attempts:
        arm = (a.get("experiments") or {}).get(name)
        if arm is not None:
            out.setdefault(str(arm), []).append(a)
    return out


def _config(seg, name: str) -> dict | None:
    cfg = None
    for e in seg.jsonl("experiments"):
        if e.get("experiment") == name and e.get("event") == "config":
            cfg = e
    return cfg


def _would_fail(seg, a) -> bool:
    return any(v.get("outcome") == "would-fail" for v in seg.verdicts_by_attempt.get(a["attempt"], []))


def _landed(seg, a) -> bool:
    return (seg.outcomes.get(a["attempt"]) or {}).get("final") in ("landed_ok", "landed_fail")


def _net(seg, a):
    o = seg.outcomes.get(a["attempt"]) or {}
    lg = o.get("ledger") or {}
    return lg.get("trade_net", 0 if o.get("final") not in ("landed_ok", "landed_fail") else None)


def balance(seg, name: str) -> dict | None:
    arms = _arms(seg, name)
    cfg = _config(seg, name)
    counts = {k: len(v) for k, v in arms.items()}
    w = None
    if cfg and cfg.get("arms") and cfg.get("weights"):
        w = {str(a): float(x) for a, x in zip(cfg["arms"], cfg["weights"])}
    return {"counts": dict(sorted(counts.items())), "weights": w,
            "chi2": stats.chi_square_balance(counts, w) if w else None}


def x2(seg) -> dict:
    arms = _arms(seg, "x2_delay_ms")
    bands = sorted({str(a.get("band")) for v in arms.values() for a in v})
    out = {}
    for band in bands:
        groups = []
        for arm, rows in sorted(arms.items(), key=lambda kv: _num(kv[0]) or 0):
            rs = [a for a in rows if str(a.get("band")) == band]
            groups.append((_num(arm), sum(_would_fail(seg, a) for a in rs), len(rs)))
        t = stats.cochran_armitage(groups, "decreasing")
        per10 = (t["slope"] * 10) if t else None
        out[band] = {"arms": [{"delay_ms": g[0], "would_fail": g[1], "n": g[2], "rate": ratio(g[1], g[2])} for g in groups],
                     "trend": t, "slope_per_10ms": stats._clean(per10) if per10 is not None else None,
                     "go": bool(t and per10 is not None and per10 <= X2_SLOPE_PER_10MS and t["p"] < 0.05)}
    return out


def x4(seg) -> dict:
    arms = _arms(seg, "x4_share")
    if not arms:
        return {}
    base = max(arms, key=lambda k: (_num(k) or 0))
    res = {}
    base_rate = None
    for arm, rows in sorted(arms.items()):
        land = [1 if _landed(seg, a) else 0 for a in rows]
        nets = [n for n in (_net(seg, a) for a in rows) if n is not None]
        rate = ratio(sum(land), len(land))
        if arm == base:
            base_rate = rate
        res[arm] = {"n": len(rows), "land_rate": rate, "land_rate_ci95": stats.bootstrap_ci(land) if land else None,
                    "net_per_attempt": stats._clean(sum(nets) / len(nets)) if nets else None,
                    "net_ci95": stats.bootstrap_ci(nets) if nets else None}
    for arm, r in res.items():
        if arm != base and base_rate:
            drop = 1 - (r["land_rate"] or 0) / base_rate
            r["relative_land_drop_vs_" + base] = stats._clean(drop)
            r["go"] = drop < X4_MAX_REL_DROP
    return {"baseline": base, "arms": res}


def x5(seg) -> dict:
    k: dict = {"bam": [0, 0], "jito": [0, 0]}
    for a in seg.attempts:
        kind = (a.get("leader") or {}).get("kind")
        if kind in k:
            k[kind][1] += 1
            k[kind][0] += _landed(seg, a)
    rb, rj = ratio(*k["bam"]), ratio(*k["jito"])
    elig = k["bam"][1] + k["jito"][1]
    r = (rb / rj) if (rb is not None and rj) else None
    return {"bam": {"landed": k["bam"][0], "eligible": k["bam"][1], "rate": rb},
            "jito": {"landed": k["jito"][0], "eligible": k["jito"][1], "rate": rj},
            "ratio": stats._clean(r) if r is not None else None, "eligible": elig,
            "fisher_p": stats.fisher_exact(k["bam"][0], k["bam"][1] - k["bam"][0], k["jito"][0], k["jito"][1] - k["jito"][0]) if elig else None,
            "go": bool(r is not None and r >= X5_MIN_RATIO and elig >= X5_MIN_ELIGIBLE),
            "enough_data": elig >= X5_MIN_ELIGIBLE}


def x8(seg) -> dict:
    blocks = [e for e in seg.jsonl("experiments") if e.get("experiment") == "x8" and e.get("event") == "block_switch"]
    if not blocks:
        return {}
    lag = {"on": [], "off": []}
    commits = [c for c in seg.jsonl("commits") if not c.get("late") and c.get("lag_ms") is not None]
    for b in blocks:
        blk = b.get("block") or {}
        arm = "on" if str(blk.get("arm")) in ("on", "1", "true", "True") else "off"
        lo, hi = blk.get("from_ns"), blk.get("to_ns")
        for c in commits:
            t = c.get("t_resolved")
            if t is not None and lo is not None and hi is not None and lo <= t < hi:
                lag[arm].append(c["lag_ms"])
    p = {k: stats.pct(v) for k, v in lag.items()}
    mw = stats.mann_whitney(lag["on"], lag["off"], "greater")
    r429 = sum((x.get("rate_limited_delta") or 0) for x in seg.jsonl("discovery"))
    d50 = (p["on"]["p50"] - p["off"]["p50"]) if (p["on"]["p50"] is not None and p["off"]["p50"] is not None) else None
    d90 = (p["on"]["p90"] - p["off"]["p90"]) if (p["on"]["p90"] is not None and p["off"]["p90"] is not None) else None
    return {"lag_ms": p, "mann_whitney_on_greater": mw, "p50_increase_ms": stats._clean(d50) if d50 is not None else None,
            "p90_increase_ms": stats._clean(d90) if d90 is not None else None, "rate_limited": r429,
            "go": bool(d50 is not None and d90 is not None and d50 <= X8_P50_MS and d90 <= X8_P90_MS and r429 == 0)}


def x9(seg) -> dict:
    v = seg.jsonl("verify")
    if not v:
        return {}
    by: dict = {}
    for r in v:
        a = seg.attempts_by_id.get(r.get("attempt")) or {}
        rt = a.get("route") or {}
        key = f"{rt.get('buy_venue')}>{rt.get('sell_venue')}"
        if r.get("latency_us") is not None:
            by.setdefault(key, []).append(r["latency_us"] / 1000.0)
    out = {k: stats.pct(x) for k, x in sorted(by.items())}
    allv = [y for x in by.values() for y in x]
    p99 = stats.quantile(allv, 0.99)
    return {"latency_ms_by_route_class": out, "p99_ms": p99, "go": bool(p99 is not None and p99 <= X9_P99_MS)}


def margin(seg) -> dict:
    arms = _arms(seg, "margin")
    out = {}
    for arm, rows in sorted(arms.items()):
        nets = [n for n in (_net(seg, a) for a in rows) if n is not None]
        out[arm] = {"n": len(rows), "landed": sum(_landed(seg, a) for a in rows),
                    "net_per_attempt": stats._clean(sum(nets) / len(nets)) if nets else None,
                    "net_ci95": stats.bootstrap_ci(nets) if nets else None}
    return out


def run(seg, ctx: dict, which: str = "all") -> dict:
    sec = section("R10", "Experiments")
    d = sec["data"]
    names = sorted({k for a in seg.attempts for k in (a.get("experiments") or {})})
    if seg.legacy or (not names and not seg.has("experiments")):
        return incomplete(sec, "no experiment arms recorded (Stage 1, WP-11)")
    d["balance"] = {n: balance(seg, n) for n in names}
    for n, b in d["balance"].items():
        if b.get("chi2") and b["chi2"]["p"] is not None and b["chi2"]["p"] < 0.01:
            sec["caveats"].append(f"{n}: arm counts are unbalanced against the weights (p={b['chi2']['p']}); results suspect")
    fns = {"x2": x2, "x4": x4, "x5": x5, "x8": x8, "x9": x9, "margin": margin}
    for k, f in fns.items():
        if which in ("all", k):
            d[k] = f(seg)
    return sec
