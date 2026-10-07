"""R10 Experiments (MEASUREMENT.md §6.4; PLAN WP-11; thresholds are R §5's, fixed before the run).

The arms of WP-11's experiments run side by side in one live run, assigned per decision by hash (src/experiments.rs).
`arbx-report experiments <segment or campaign dir> [x2|x4|size|margin|x5|x8|x9|all]` reports, for each experiment:

- the randomization's balance: arm counts against the weights over every decision (decisions.jsonl `experiments`, the
  assignment) and over the sends (attempts.jsonl `experiments`, the arms that applied: a treatment may change the
  funnel), and the bands and trigger kinds per arm (chi-square independence; the size arm moves the bands by design);
- per arm: attempts, landed, the land rate and the win rate with Wilson 95% intervals, net per attempt (bootstrap 95%),
  net per win, wins, tips / gross, failed fees, the meme and common wins (the owner's Stage 0 rule, by the route's mint:
  `tokens.py`), and the arm's net per hour were the whole run on it (its net over its weight's share of the hours);
- each arm against its control (the configured value when the run's config.toml shows it, else the first arm): the
  differences in win rate and land rate (two proportions, Fisher) and in net per attempt (bootstrap), the smallest
  change the sends so far can detect, and the sends per arm a +-30% / +-50% change in the win rate needs;
- with two experiments or more, the factorial's cells.

Money comes from the ledger (ledger.jsonl), never from status counters: an attempt's net is its signatures' ledger
lines (`trade_net`), across the campaign's segments, leaving out `dup` lines and `pre_run` lines (transactions from
before a segment's stream); an attempt that did not land nets 0; a landing without a ledger line is counted apart, not
as 0. X2: the would-fail rate against the delay, a two-sided trend test with the slope's interval (go "speed matters"
when would-fail rises >= 5 points per 10 ms added, go "adopt the delay" when it falls as much, one-sided p < 0.05).
X5, X8, X9 as before."""
from __future__ import annotations

import os

from .. import stats, tokens
from . import incomplete, ratio, section

X2_SLOPE_PER_10MS = 0.05  # would-fail changes by >= 5 points per 10 ms (either way: speed matters, or the delay helps)
X4_MAX_REL_DROP = 0.20
X5_MIN_RATIO, X5_MIN_ELIGIBLE = 0.5, 200
X8_P50_MS, X8_P90_MS = 1.0, 5.0
X9_P99_MS = 3.0

# the experiments' record keys (decisions / attempts `experiments`) and their experiments.jsonl names
KEYS = {"x2": "x2_delay_ms", "x4": "x4_share", "size": "size_max_sol", "margin": "margin"}
NAMES = {v: k for k, v in KEYS.items()}
LANDED = ("landed_ok", "landed_fail")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _label(v) -> str:
    """an arm's label: the configured value as the records print it (0.1, 0.35, 2000, 0.05)"""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _arm(r: dict, key: str):
    v = (r.get("experiments") or {}).get(key)
    return None if v is None else _label(v)


def _segs(seg) -> list:
    return list(seg.segments) if hasattr(seg, "segments") else [seg]


def _configs(segs) -> dict:
    """{key: the last `config` line of experiments.jsonl} (matched by `key` or by `experiment`)"""
    out: dict = {}
    for s in segs:
        for e in s.jsonl("experiments"):
            if e.get("event") != "config":
                continue
            k = e.get("key") or KEYS.get(e.get("experiment")) or e.get("experiment")
            out[k] = e
    return out


def _run_config(segs) -> dict | None:
    """the run's frozen config (config.toml beside the records), when this Python reads TOML"""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return None
    for s in segs:
        p = os.path.join(s.dir, "config.toml")
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    return tomllib.load(f)
            except (OSError, ValueError):
                return None
    return None


def _control(key: str, arms: list, cfg: dict | None, conf: dict | None) -> tuple:
    """(the control arm's label, why): the configured value when the run's config shows it, else the first arm"""
    labels = [_label(a) for a in arms]
    if not labels:
        return None, "no arm"
    cur = None
    if key == "x2_delay_ms":
        cur = 0
    elif cfg is not None:
        if key == "x4_share":
            shares = (cfg.get("tips") or {}).get("shares")
            mb = ((conf or {}).get("scope") or {}).get("max_band", 2)
            if isinstance(shares, list) and shares[:mb + 1] and len(set(shares[:mb + 1])) == 1:
                cur = shares[0]
        elif key == "margin":
            cur = (cfg.get("send_policy") or {}).get("margin_floor", 1)
    if cur is not None:
        for lab, a in zip(labels, arms):
            if _num(a) is not None and abs(_num(a) - float(cur)) < 1e-12:
                return lab, "no delay" if key == "x2_delay_ms" else "the configured value (the run's config.toml)"
    return labels[0], "the first arm configured"


# ------------------------------------------------------------------------------------------------ rows

def _rows(segs) -> tuple:
    """One row per sent attempt across the segments (would-sends apart), with its money from the ledger. Returns
    (rows, would_sends, notes)"""
    ledger: dict = {}
    pre_run_sigs: set = set()
    for s in segs:
        for r in s.ledger:
            ledger.setdefault(r.get("sig"), r)
        for r in s.ledger_pre_run:
            pre_run_sigs.add(r.get("sig"))
    rows, would = [], []
    notes = {"landed_without_ledger": 0, "pre_run_lines_of_our_attempts": 0, "ledger_without_outcome": 0}
    for s in segs:
        a2s: dict = {}
        for sig, a in s.sig_to_attempt.items():
            a2s.setdefault(a, set()).add(sig)
        for a in s.would_sends:
            would.append({"seg": s.name, "attempt": a.get("attempt"), "band": a.get("band"), "kind": (a.get("trigger") or {}).get("kind"),
                          "experiments": a.get("experiments") or {}})
        for a in s.attempts:
            aid = a.get("attempt")
            sigs = a2s.get(aid, set())
            lines = [ledger[x] for x in sigs if x in ledger]
            notes["pre_run_lines_of_our_attempts"] += sum(1 for x in sigs if x in pre_run_sigs)
            o = s.outcomes.get(aid) or {}
            final = o.get("final")
            verdicts = s.verdicts_by_attempt.get(aid, [])
            route = [x for x in lines if x.get("kind") == "route"] or lines
            row = {"seg": s.name, "attempt": aid, "decision": a.get("decision"), "band": a.get("band"), "kind": (a.get("trigger") or {}).get("kind"),
                   "mint": (a.get("route") or {}).get("mint"), "leader": (a.get("leader") or {}).get("kind"), "size": a.get("size_lamports"),
                   "experiments": a.get("experiments") or {}, "final": final, "landed": bool(route) or final in LANDED,
                   "win": any(x.get("ok") for x in route) if route else final == "landed_ok",
                   "would_fail": any(v.get("outcome") == "would-fail" for v in verdicts),
                   "lost_auction": any(v.get("outcome") == "lost-auction" for v in verdicts)}
            if route:
                row.update(money=True, net=sum(x.get("trade_net") or 0 for x in route), gross=sum(x.get("trade_gross") or 0 for x in route if x.get("ok")),
                           tip=sum(x.get("tip") or 0 for x in route if x.get("ok")), fee_fail=sum(x.get("fee") or 0 for x in route if not x.get("ok")))
                if final not in LANDED:
                    notes["ledger_without_outcome"] += 1
            elif row["landed"]:
                row.update(money=False, net=None, gross=None, tip=None, fee_fail=None)
                notes["landed_without_ledger"] += 1
            else:
                row.update(money=True, net=0, gross=0, tip=0, fee_fail=0)
            rows.append(row)
    return rows, would, notes


def _arm_stats(rows: list, hours=None, share=None) -> dict:
    n = len(rows)
    landed = sum(r["landed"] for r in rows)
    wins = [r for r in rows if r["win"]]
    known = [r for r in rows if r["money"]]
    nets = [r["net"] for r in known]
    win_nets = [r["net"] for r in wins if r["money"]]
    gross = sum(r["gross"] for r in wins if r["money"])
    tips = sum(r["tip"] for r in wins if r["money"])
    meme = [r for r in wins if tokens.classify(r["mint"]) == "meme"]
    common = [r for r in wins if tokens.classify(r["mint"]) == "common"]
    by_common: dict = {}
    for r in common:
        by_common[tokens.symbol(r["mint"])] = by_common.get(tokens.symbol(r["mint"]), 0) + 1
    lookalike = sorted({r["mint"] for r in meme if r["mint"] in tokens.LOOKALIKES})
    total = sum(nets)
    out = {"attempts": n, "landed": landed, "land_rate": ratio(landed, n), "land_rate_ci95": stats.wilson(landed, n),
           "wins": len(wins), "win_rate": ratio(len(wins), n), "win_rate_ci95": stats.wilson(len(wins), n),
           "net_total": total, "net_per_attempt": stats._clean(total / len(nets)) if nets else None,
           "net_per_attempt_ci95": stats.bootstrap_ci(nets) if nets else None,
           "net_per_win": stats._clean(sum(win_nets) / len(win_nets)) if win_nets else None,
           "tips_over_gross": ratio(tips, gross) if gross else None, "gross_wins": gross, "tips_wins": tips,
           "failed_fees": sum(r["fee_fail"] or 0 for r in known), "landed_failures": landed - len(wins),
           "would_fail": sum(r["would_fail"] for r in rows), "would_fail_rate": ratio(sum(r["would_fail"] for r in rows), n),
           "lost_auction": sum(r["lost_auction"] for r in rows),
           "wins_meme": len(meme), "wins_common": len(common), "net_meme": sum(r["net"] for r in meme if r["money"]),
           "net_common": sum(r["net"] for r in common if r["money"]), "wins_common_by_token": dict(sorted(by_common.items())),
           "money_unknown": n - len(known)}
    if lookalike:
        out["meme_lookalikes"] = {m: tokens.LOOKALIKES[m] for m in lookalike}
    if hours and share:
        out["net_per_hour_whole_run"] = stats._clean(total / share / hours)
    return out


def _counts_by(rows: list, key: str, field: str) -> dict:
    t: dict = {}
    for r in rows:
        a = _arm(r, key)
        if a is None:
            continue
        v = str(r.get(field))
        t.setdefault(a, {}).setdefault(v, 0)
        t[a][v] += 1
    return {a: dict(sorted(c.items())) for a, c in sorted(t.items())}


def _decisions(segs, key: str) -> dict | None:
    """the assignment's counts over every decision (decisions.jsonl `experiments`), when the decisions were kept"""
    if not any(s.has("decisions") for s in segs):
        return None
    counts: dict = {}
    kinds: dict = {}
    n = 0
    for s in segs:
        for d in s.decisions:
            if d.get("routes") is None:
                continue
            arm = _arm(d, key)
            if arm is None:
                continue
            n += 1
            counts[arm] = counts.get(arm, 0) + 1
            kinds.setdefault(arm, {}).setdefault(str(d.get("kind")), 0)
            kinds[arm][str(d.get("kind"))] += 1
    return {"n": n, "counts": dict(sorted(counts.items())), "by_kind": {a: dict(sorted(c.items())) for a, c in sorted(kinds.items())}}


# ------------------------------------------------------------------------------------------------ one experiment

def experiment(segs, key: str, rows: list, would: list, cfgs: dict, run_cfg: dict | None, hours) -> dict:
    conf = cfgs.get(key)
    in_scope = [r for r in rows if _arm(r, key) is not None]
    conf_arms = (conf or {}).get("arms") or []
    arms = [_label(a) for a in conf_arms] or sorted({_arm(r, key) for r in in_scope}, key=lambda x: (_num(x) is None, _num(x) or 0, x))
    weights = (conf or {}).get("weights") or [1.0] * len(arms)
    wmap = {a: float(w) for a, w in zip(arms, weights)}
    wsum = sum(wmap.values()) or 1.0
    control, why = _control(key, conf_arms or arms, run_cfg, conf)
    out = {"key": key, "config": {k: (conf or {}).get(k) for k in ("arms", "weights", "seed", "scope")} if conf else None,
           "control": control, "control_why": why}
    # the balance: the assignment over every decision, the sends, the bands and trigger kinds per arm
    dec = _decisions(segs, key)
    bal: dict = {"decisions": None}
    if dec:
        bal["decisions"] = {**dec, "weights": wmap, "chi2": stats.chi_square_balance(dec["counts"], wmap) if dec["counts"] else None}
    send_counts = {a: sum(1 for r in in_scope if _arm(r, key) == a) for a in arms}
    by_band, by_kind = _counts_by(in_scope, key, "band"), _counts_by(in_scope, key, "kind")
    bal.update(sends=send_counts, sends_chi2=stats.chi_square_balance(send_counts, wmap) if in_scope else None, by_band=by_band,
               by_kind=by_kind, band_independence=stats.chi_square_independence(by_band), kind_independence=stats.chi_square_independence(by_kind))
    if would:
        bal["would_sends"] = {a: sum(1 for r in would if _arm(r, key) == a) for a in arms}
    out["balance"] = bal
    # per arm
    per = {a: _arm_stats([r for r in in_scope if _arm(r, key) == a], hours, wmap.get(a, 1.0) / wsum) for a in arms}
    out["arms"] = per
    # against the control
    vs: dict = {}
    c = per.get(control)
    crow = [r for r in in_scope if _arm(r, key) == control]
    for a in arms:
        if a == control or not c:
            continue
        x = per[a]
        arow = [r for r in in_scope if _arm(r, key) == a]
        anets = [r["net"] for r in arow if r["money"]]
        cnets = [r["net"] for r in crow if r["money"]]
        p0 = c["win_rate"] or 0
        vs[a] = {"win_rate": stats.two_proportions(x["wins"], x["attempts"], c["wins"], c["attempts"]),
                 "land_rate": stats.two_proportions(x["landed"], x["attempts"], c["landed"], c["attempts"]),
                 "net_per_attempt_diff": stats._clean((x["net_per_attempt"] or 0) - (c["net_per_attempt"] or 0)) if anets and cnets else None,
                 "net_per_attempt_diff_ci95": stats.bootstrap_diff_ci(anets, cnets),
                 "win_rate_mde_rel": stats.mde_rel(p0, min(x["attempts"], c["attempts"])) if 0 < p0 < 1 else None,
                 "sends_per_arm_for_win_rate": {"+-30%": stats.n_per_arm(p0 * 1.3, p0) if 0 < p0 < 0.7 else None,
                                                "+-50%": stats.n_per_arm(p0 * 1.5, p0) if 0 < p0 < 0.6 else None}}
    out["vs_control"] = vs
    return out


# ------------------------------------------------------------------------------------------------ the PLAN's rules

def balance(seg, name: str) -> dict | None:
    """the arm counts of experiment record key `name` over the sends, against the configured weights (the short form;
    `experiment` has the full balance)"""
    segs = _segs(seg)
    cfg = _configs(segs).get(name)
    arms: dict = {}
    for s in segs:
        for a in s.attempts:
            v = _arm(a, name)
            if v is not None:
                arms[v] = arms.get(v, 0) + 1
    w = None
    if cfg and cfg.get("arms") and cfg.get("weights"):
        w = {_label(a): float(x) for a, x in zip(cfg["arms"], cfg["weights"])}
    return {"counts": dict(sorted(arms.items())), "weights": w, "chi2": stats.chi_square_balance(arms, w) if w and arms else None}


def x2(rows: list) -> dict:
    """would-fail against the delay arm, per band: a two-sided Cochran-Armitage trend test with the slope's 95% interval
    (per 10 ms). `go_speed`: would-fail rises >= 5 points per 10 ms of delay added (speed matters; one-sided p < 0.05);
    `go_delay`: it falls as much (adopt the best delay). Landings must confirm a gain (STAGE1-PLAN §3.2: accepted is not
    landed): the land rate per arm is beside it"""
    key = KEYS["x2"]
    by_band: dict = {}
    for r in rows:
        v = (r.get("experiments") or {}).get(key)
        if v is not None:
            by_band.setdefault(str(r.get("band")), []).append((_num(v), r))
    out = {}
    for band, items in sorted(by_band.items()):
        arms = sorted({d for d, _ in items})
        groups = [(d, sum(r["would_fail"] for x, r in items if x == d), sum(1 for x, _ in items if x == d)) for d in arms]
        t = stats.cochran_armitage(groups, "two-sided")
        per10 = t["slope"] * 10 if t else None
        ci10 = [stats._clean(v * 10) for v in t["slope_ci95"]] if t and t.get("slope_ci95") else None
        out[band] = {"arms": [{"delay_ms": g[0], "would_fail": g[1], "n": g[2], "rate": ratio(g[1], g[2]),
                               "landed": sum(r["landed"] for x, r in items if x == g[0]),
                               "land_rate": ratio(sum(r["landed"] for x, r in items if x == g[0]), g[2])} for g in groups],
                     "trend": t, "slope_per_10ms": stats._clean(per10) if per10 is not None else None, "slope_per_10ms_ci95": ci10,
                     "go_speed": bool(t and per10 is not None and per10 >= X2_SLOPE_PER_10MS and t["p_increasing"] < 0.05),
                     "go_delay": bool(t and per10 is not None and per10 <= -X2_SLOPE_PER_10MS and t["p_decreasing"] < 0.05)}
    return out


def x4_rule(e: dict) -> dict:
    """PLAN WP-11's X4 rule over `experiment`'s arms: the land rate per arm against the control, go when it drops less
    than 20% relative; STAGE1-PLAN §4's (`go_stage1`): no lost auctions and no fewer wins per send (one-sided p >= 0.05)
    at >= 1,000 sends per arm"""
    base = e.get("control")
    res = {}
    arms = e.get("arms") or {}
    b = arms.get(base) or {}
    for a, x in arms.items():
        r = {"n": x["attempts"], "land_rate": x["land_rate"], "land_rate_ci95": x["land_rate_ci95"], "net_per_attempt": x["net_per_attempt"],
             "net_ci95": x["net_per_attempt_ci95"]}
        if a != base and b.get("land_rate"):
            drop = 1 - (x["land_rate"] or 0) / b["land_rate"]
            r["relative_land_drop_vs_" + str(base)] = stats._clean(drop)
            r["go"] = drop < X4_MAX_REL_DROP
            wr = (e.get("vs_control") or {}).get(a, {}).get("win_rate") or {}
            r["fewer_wins_p"] = wr.get("p_less")
            r["go_stage1"] = bool(x["lost_auction"] == 0 and wr.get("p_less") is not None and wr["p_less"] >= 0.05
                                  and min(x["attempts"], b.get("attempts") or 0) >= 1_000)
        res[a] = r
    return {"baseline": base, "arms": res}


def x5(segs) -> dict:
    k: dict = {"bam": [0, 0], "jito": [0, 0]}
    for s in segs:
        for a in s.attempts:
            kind = (a.get("leader") or {}).get("kind")
            if kind in k:
                k[kind][1] += 1
                k[kind][0] += (s.outcomes.get(a["attempt"]) or {}).get("final") in LANDED
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


def factorial(rows: list, keys: list) -> dict:
    """the cells of every pair of experiments (each send is in one arm of each): attempts, wins, net"""
    out: dict = {}
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            cells: dict = {}
            for r in rows:
                a1, a2 = _arm(r, k1), _arm(r, k2)
                if a1 is None or a2 is None:
                    continue
                cells.setdefault(f"{NAMES.get(k1, k1)}={a1} {NAMES.get(k2, k2)}={a2}", []).append(r)
            out[f"{NAMES.get(k1, k1)} x {NAMES.get(k2, k2)}"] = {
                k: {"attempts": len(v), "wins": sum(r["win"] for r in v), "win_rate": ratio(sum(r["win"] for r in v), len(v)),
                    "net_total": sum(r["net"] for r in v if r["money"]),
                    "net_per_attempt": stats._clean(sum(r["net"] for r in v if r["money"]) / max(1, sum(1 for r in v if r["money"])))}
                for k, v in sorted(cells.items())}
    return out


def run(seg, ctx: dict, which: str = "all") -> dict:
    """R10 for a segment or a campaign (`model.Campaign`: every segment's attempts, the ledger across them)"""
    sec = section("R10", "Experiments")
    d = sec["data"]
    segs = _segs(seg)
    if any(s.legacy for s in segs):
        return incomplete(sec, "an arb-lab v1 segment: no experiment arms")
    rows, would, notes = _rows(segs)
    cfgs = _configs(segs)
    keys = sorted({k for r in rows + would for k in (r.get("experiments") or {})} | {k for k in cfgs if k in NAMES})
    if not keys and not any(s.has("experiments") for s in segs):
        return incomplete(sec, "no experiment arms recorded (Stage 1, WP-11)")
    hours = sum((s.window.get("trading_hours") or 0) for s in segs) or None
    run_cfg = _run_config(segs)
    d["segments"] = [s.name for s in segs]
    d["sends"] = len(rows)
    d["would_sends"] = len(would)
    d["trading_hours"] = stats._clean(hours) if hours else None
    d["money"] = {"source": "ledger.jsonl (dup and pre_run lines left out), by the attempts' signatures", **notes}
    if notes["landed_without_ledger"]:
        sec["caveats"].append(f"{notes['landed_without_ledger']} landing(s) without a ledger line: their money is unknown (counted apart, never 0)")
    if notes["pre_run_lines_of_our_attempts"]:
        sec["caveats"].append(f"{notes['pre_run_lines_of_our_attempts']} pre_run ledger line(s) name our attempts' signatures and are left out")
    if would and not rows:
        sec["caveats"].append("would-sends only (a shadow or dry run, or a closed gate): the balance holds, nothing landed")
    if not hours:
        sec["caveats"].append("no trading hours (warm-up and gate events): no net per hour")
    d["balance"] = {k: balance(seg, k) for k in keys}
    d["experiments"] = {}
    for k in keys:
        name = NAMES.get(k, k)
        if which not in ("all", name):
            continue
        e = experiment(segs, k, rows, would, cfgs, run_cfg, hours)
        d["experiments"][name] = e
        dec = (e["balance"].get("decisions") or {}).get("chi2")
        if dec and dec["p"] is not None and dec["p"] < 0.01:
            sec["caveats"].append(f"{name}: decisions per arm are unbalanced against the weights (p={dec['p']}): the assignment is suspect")
        b = d["balance"].get(k) or {}
        if b.get("chi2") and b["chi2"]["p"] is not None and b["chi2"]["p"] < 0.01:
            sec["caveats"].append(f"{k}: arm counts are unbalanced against the weights (p={b['chi2']['p']}); results suspect (an arm changes the "
                                  "funnel, or the assignment is off: see the decisions' balance)")
        bi = e["balance"].get("band_independence")
        if bi and bi["p"] is not None and bi["p"] < 0.01 and name != "size":
            sec["caveats"].append(f"{name}: the bands differ by arm (p={bi['p']}): compare within bands")
    if which in ("all", "x2") and KEYS["x2"] in keys:
        d["x2"] = x2(rows)
    if which in ("all", "x4") and "x4" in d["experiments"]:
        d["x4"] = x4_rule(d["experiments"]["x4"])
    if which in ("all", "margin") and "margin" in d["experiments"]:
        d["margin"] = {a: {"n": x["attempts"], "landed": x["landed"], "net_per_attempt": x["net_per_attempt"], "net_ci95": x["net_per_attempt_ci95"]}
                       for a, x in d["experiments"]["margin"]["arms"].items()}
    named = [k for k in keys if k in NAMES]
    if len(named) >= 2:
        d["factorial"] = factorial(rows, named)
    if which in ("all", "x5"):
        d["x5"] = x5(segs)
    if which in ("all", "x8"):
        d["x8"] = x8(segs[0]) if len(segs) == 1 else {}
    if which in ("all", "x9"):
        d["x9"] = x9(segs[0]) if len(segs) == 1 else {}
    return sec
