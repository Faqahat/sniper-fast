"""R10 Experiments (MEASUREMENT.md §6.4; PLAN WP-11; thresholds are R §5's, fixed before the run).

The arms of WP-11's experiments run side by side in one live run, assigned per decision by hash (src/experiments.rs).
`arbx-report experiments <segment or campaign dir> [x2|x4|size|margin|x5|x8|x9|all]` reports, for each experiment:

- the randomization's balance: arm counts against the weights over every decision (the assignment: status.jsonl's
  per-arm counters, else decisions.jsonl read one line at a time) and over the sends (the arms that applied: a
  treatment may change the funnel), and the bands and trigger kinds per arm (chi-square independence; the size arm moves
  the bands by design);
- per arm: attempts, landed, the land rate and the win rate with Wilson 95% intervals, net per attempt (bootstrap 95%),
  net per win, wins, tips / gross, failed fees, the meme and common wins (the owner's Stage 0 rule, by the route's mint:
  `tokens.py`; a win without a mint is `unknown`), the executor's `canary_wait` refusals of the arm's decisions, and the
  arm's net per hour as its net per send times the run's sends per hour (the canary's one send a second binds: the arms
  compete for it, so a weight share would overstate an arm that makes more decisions eligible);
- per arm by leader kind (jito, bam) and by tip policy (`share_of_edge`, `bam_floor`): on a BAM-led slot the BAM floor
  often bids the same for every X4 arm, so X4's primary comparison is the Jito-led one;
- each arm against its control (experiments.jsonl `control`: the first arm; never guessed), per decision (the randomized
  unit, every attempt by its assigned arm, a decision not sent netting 0: wins per decision, net per decision with a
  normal interval; the decisions from status, else decisions.jsonl, else the evaluations times the weight share) and per
  send (descriptive: win and land rates, net per attempt by bootstrap, the smallest change the sends so far detect, the
  sends per arm a +-30% / +-50% change needs), and on Jito-led sends;
- with two experiments or more, the factorial's cells.

Money comes from the ledger (ledger.jsonl), never from status counters: an attempt's net is its signatures' ledger
lines (`trade_net`), across the campaign's segments, as the Rust side counts them (`Segment.ledger`: no `dup` line,
nothing at or before the campaign's start, so no `pre_run` line of the previous campaign); an attempt that did not
land nets 0; a landing without a ledger line is counted apart, not as 0. X2: the would-fail rate against the delay, a two-sided trend test with the slope's interval (go "speed matters"
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


def _configured(key: str, cfg: dict | None, conf: dict | None):
    """the value the run's config.toml gives the experiment's knob (None: no config.toml, or no single value)"""
    if key == "x2_delay_ms":
        return 0
    if cfg is None:
        return None
    if key == "x4_share":
        shares = (cfg.get("tips") or {}).get("shares")
        mb = ((conf or {}).get("scope") or {}).get("max_band", 2)
        if isinstance(shares, list) and shares[:mb + 1] and len(set(shares[:mb + 1])) == 1:
            return shares[0]
        return None
    if key == "margin":
        return (cfg.get("send_policy") or {}).get("margin_floor", 1)
    return None


def _control(key: str, arms: list, cfg: dict | None, conf: dict | None) -> tuple:
    """(the control arm's label, why, a warning or None). The control is experiments.jsonl's `control` (the first arm
    configured: WP-11 review #3); a record without one (written before) takes the value the run's config.toml gives the
    knob when it is an arm, and none otherwise: the report never guesses (no control, no comparison)"""
    labels = [_label(a) for a in arms]
    if not labels:
        return None, "no arm", None
    cur = _configured(key, cfg, conf)
    cur_lab = next((lab for lab, a in zip(labels, arms) if cur is not None and _num(a) is not None and abs(_num(a) - float(cur)) < 1e-12), None)
    if (conf or {}).get("control") is not None:
        lab = _label(conf["control"])
        warn = None
        if cur is not None and cur_lab != lab and key != "x2_delay_ms":
            warn = f"{key}: the control {lab} (the first arm) is not the run's configured value {cur}"
        return lab, "experiments.jsonl `control` (the first arm configured)", warn
    if cur_lab is not None:
        return cur_lab, "no delay" if key == "x2_delay_ms" else "the configured value (the run's config.toml)", None
    return None, "none: experiments.jsonl has no `control` and the run's config.toml does not give one", (
        f"{key}: no control (an experiments.jsonl line without `control`, and no config.toml beside the records that names it): no arm is "
        "compared; put config.toml beside the records")


# ------------------------------------------------------------------------------------------------ rows

def _rows(segs) -> tuple:
    """One row per sent attempt across the segments (would-sends apart), with its money from the ledger. Returns
    (rows, would_sends, notes). A row's `experiments` are the arms that applied; `assigned` every arm its decision was
    assigned (attempts `experiments_assigned`; before it existed, the applied ones)"""
    ledger: dict = {}
    before: set = set()
    for s in segs:
        for r in s.ledger:
            ledger.setdefault(r.get("sig"), r)
        for r in s.ledger_before_start:
            before.add(r.get("sig"))
    rows, would = [], []
    notes = {"landed_without_ledger": 0, "lines_before_start_of_our_attempts": 0, "ledger_without_outcome": 0}
    for s in segs:
        a2s: dict = {}
        for sig, a in s.sig_to_attempt.items():
            a2s.setdefault(a, set()).add(sig)
        for a in s.would_sends:
            would.append({"seg": s.name, "attempt": a.get("attempt"), "band": a.get("band"), "kind": (a.get("trigger") or {}).get("kind"),
                          "experiments": a.get("experiments") or {}, "assigned": a.get("experiments_assigned") or a.get("experiments") or {}})
        for a in s.attempts:
            aid = a.get("attempt")
            sigs = a2s.get(aid, set())
            lines = [ledger[x] for x in sigs if x in ledger]
            notes["lines_before_start_of_our_attempts"] += sum(1 for x in sigs if x in before and x not in ledger)
            o = s.outcomes.get(aid) or {}
            final = o.get("final")
            verdicts = s.verdicts_by_attempt.get(aid, [])
            route = [x for x in lines if x.get("kind") == "route"] or lines
            tip = a.get("tip") or {}
            row = {"seg": s.name, "attempt": aid, "decision": a.get("decision"), "band": a.get("band"), "kind": (a.get("trigger") or {}).get("kind"),
                   "mint": (a.get("route") or {}).get("mint"), "leader": (a.get("leader") or {}).get("kind"), "policy": tip.get("policy"),
                   "size": a.get("size_lamports"), "experiments": a.get("experiments") or {},
                   "assigned": a.get("experiments_assigned") or a.get("experiments") or {}, "final": final, "landed": bool(route) or final in LANDED,
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


def _assigned(r: dict, key: str):
    v = (r.get("assigned") or {}).get(key)
    return None if v is None else _label(v)


def _arm_stats(rows: list, run_sends_per_hour=None) -> dict:
    n = len(rows)
    landed = sum(r["landed"] for r in rows)
    wins = [r for r in rows if r["win"]]
    known = [r for r in rows if r["money"]]
    nets = [r["net"] for r in known]
    win_nets = [r["net"] for r in wins if r["money"]]
    gross = sum(r["gross"] for r in wins if r["money"])
    tips = sum(r["tip"] for r in wins if r["money"])
    kinds = {k: [r for r in wins if tokens.classify(r["mint"]) == k] for k in ("meme", "common", "unknown")}
    by_common: dict = {}
    for r in kinds["common"]:
        by_common[tokens.symbol(r["mint"])] = by_common.get(tokens.symbol(r["mint"]), 0) + 1
    lookalike = sorted({r["mint"] for r in kinds["meme"] if r["mint"] in tokens.LOOKALIKES})
    total = sum(nets)
    npa = total / len(nets) if nets else None
    out = {"attempts": n, "landed": landed, "land_rate": ratio(landed, n), "land_rate_ci95": stats.wilson(landed, n),
           "wins": len(wins), "win_rate": ratio(len(wins), n), "win_rate_ci95": stats.wilson(len(wins), n),
           "net_total": total, "net_per_attempt": stats._clean(npa) if npa is not None else None,
           "net_per_attempt_ci95": stats.bootstrap_ci(nets) if nets else None,
           "net_per_win": stats._clean(sum(win_nets) / len(win_nets)) if win_nets else None,
           "tips_over_gross": ratio(tips, gross) if gross else None, "gross_wins": gross, "tips_wins": tips,
           "failed_fees": sum(r["fee_fail"] or 0 for r in known), "landed_failures": landed - len(wins),
           "would_fail": sum(r["would_fail"] for r in rows), "would_fail_rate": ratio(sum(r["would_fail"] for r in rows), n),
           "lost_auction": sum(r["lost_auction"] for r in rows),
           "wins_meme": len(kinds["meme"]), "wins_common": len(kinds["common"]), "wins_unknown_token": len(kinds["unknown"]),
           "net_meme": sum(r["net"] for r in kinds["meme"] if r["money"]), "net_common": sum(r["net"] for r in kinds["common"] if r["money"]),
           "wins_common_by_token": dict(sorted(by_common.items())), "money_unknown": n - len(known), "net_sum_sq": sum(v * v for v in nets),
           # review #1: the capacity-bound estimate (net per send x the run's sends per hour)
           "net_per_hour": stats._clean(npa * run_sends_per_hour) if (npa is not None and run_sends_per_hour) else None}
    if lookalike:
        out["meme_lookalikes"] = {m: tokens.LOOKALIKES[m] for m in lookalike}
    return out


def _split(rows: list, field: str) -> dict:
    """attempts, wins, win rate and net per attempt by `field` (leader kind, tip policy)"""
    out: dict = {}
    for r in rows:
        k = str(r.get(field))
        b = out.setdefault(k, {"attempts": 0, "wins": 0, "net_total": 0, "money": 0})
        b["attempts"] += 1
        b["wins"] += r["win"]
        if r["money"]:
            b["net_total"] += r["net"]
            b["money"] += 1
    for b in out.values():
        b["win_rate"] = ratio(b["wins"], b["attempts"])
        b["win_rate_ci95"] = stats.wilson(b["wins"], b["attempts"])
        b["net_per_attempt"] = stats._clean(b["net_total"] / b["money"]) if b["money"] else None
        del b["money"]
    return dict(sorted(out.items()))


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


def _status_arms(segs, key: str) -> dict | None:
    """status.jsonl `experiments` (the engine's per-arm counters, WP-11 review #2): each segment's last line that has them,
    summed over the segments; None when a segment's lines have none (recorded before them)"""
    out: dict = {}
    for s in segs:
        last = None
        for line in s.status:
            if isinstance(line.get("experiments"), dict):
                last = line["experiments"]
        if last is None:
            return None
        for arm, c in (last.get(key) or {}).items():
            o = out.setdefault(_label(_num(arm)) if _num(arm) is not None else arm, {"decisions": 0, "opportunities": 0, "sent": 0, "would_send": 0, "refused": {}})
            for f in ("decisions", "opportunities", "sent", "would_send"):
                o[f] += c.get(f) or 0
            for r, n in (c.get("refused") or {}).items():
                o["refused"][r] = o["refused"].get(r, 0) + n
    return out


def _decisions_stream(segs, key: str) -> dict | None:
    """decisions.jsonl read one line at a time (never held: a 60-min segment's decisions are gigabytes of JSON), keeping
    per assigned arm the decisions, their kinds, the opportunities, sends, would-sends and the executor's refusals by
    reason; None when no segment kept its decisions"""
    if not any(s.has("decisions") for s in segs):
        return None
    out: dict = {}
    from .. import streams
    for s in segs:
        # a report that already loaded them (the segment report's funnel) is read from its copy: not read twice
        src = s.__dict__["decisions"] if "decisions" in s.__dict__ else streams.iter_jsonl(s.stream_files("decisions"), "decisions")
        for d in src:
            if d.get("routes") is None:
                continue
            arm = _arm(d, key)
            if arm is None:
                continue
            o = out.setdefault(arm, {"decisions": 0, "opportunities": 0, "sent": 0, "would_send": 0, "refused": {}, "by_kind": {}})
            o["decisions"] += 1
            k = str(d.get("kind"))
            o["by_kind"][k] = o["by_kind"].get(k, 0) + 1
            if d.get("opp") is None:
                continue
            o["opportunities"] += 1
            if d.get("sent") is True:
                o["sent"] += 1
            elif d.get("would_send"):
                o["would_send"] += 1
            else:
                r = str(d.get("reason") or "").split(":")[0]
                o["refused"][r] = o["refused"].get(r, 0) + 1
    return out


def _evaluations(segs) -> int | None:
    """every decision of the segments (the randomized units): status.jsonl's `counts_total.evaluation` (one per
    decision), summed; None when a segment has none"""
    tot = 0
    for s in segs:
        agg = s.status_agg if isinstance(s.status_agg, dict) else {}
        v = (agg.get("total") or {}).get("counts_total.evaluation")
        if v is None:
            return None
        tot += v
    return tot


def _exec_total(segs, k: str):
    tot = 0
    for s in segs:
        agg = s.status_agg if isinstance(s.status_agg, dict) else {}
        v = (agg.get("total") or {}).get(k)
        if v is None:
            return None
        tot += v
    return tot


def _per_decision(x: dict, c: dict, da, dc) -> dict | None:
    """arm `x` against control `c` per decision (each decision is one unit, an unsent one nets 0): wins per decision and
    net per decision, with the difference's 95% interval (normal: the decisions are many). `x`/`c`: the arms' stats over
    their assigned attempts"""
    if not da or not dc:
        return None
    ma, mc = x["net_total"] / da, c["net_total"] / dc
    va = max(0.0, x["net_sum_sq"] / da - ma * ma) / da
    vc = max(0.0, c["net_sum_sq"] / dc - mc * mc) / dc
    se = (va + vc) ** 0.5
    diff = ma - mc
    return {"decisions": [stats._clean(da), stats._clean(dc)], "wins": stats.two_proportions(x["wins"], int(round(da)), c["wins"], int(round(dc))),
            "net_per_1k_decisions": [stats._clean(1000 * ma), stats._clean(1000 * mc)], "net_per_1k_decisions_diff": stats._clean(1000 * diff),
            "net_per_1k_decisions_diff_ci95": [stats._clean(1000 * (diff - 1.959964 * se)), stats._clean(1000 * (diff + 1.959964 * se))]}


def _per_send(x: dict, c: dict, xr: list, cr: list) -> dict:
    """arm `x` against control `c` over sends (descriptive while an arm changes which decisions are sent)"""
    p0 = c["win_rate"] or 0
    need = None
    if 0 < p0 < 1:
        need = {}
        for k in (30, 50):
            for sign, f in (("+", 1 + k / 100), ("-", 1 - k / 100)):
                need[f"{sign}{k}%"] = stats.n_per_arm(p0 * f, p0) if 0 < p0 * f < 1 else None
    anets = [r["net"] for r in xr if r["money"]]
    cnets = [r["net"] for r in cr if r["money"]]
    return {"win_rate": stats.two_proportions(x["wins"], x["attempts"], c["wins"], c["attempts"]),
            "land_rate": stats.two_proportions(x["landed"], x["attempts"], c["landed"], c["attempts"]),
            "net_per_attempt_diff": stats._clean((x["net_per_attempt"] or 0) - (c["net_per_attempt"] or 0)) if anets and cnets else None,
            "net_per_attempt_diff_ci95": stats.bootstrap_diff_ci(anets, cnets),
            "win_rate_mde_rel": stats.mde_rel(p0, min(x["attempts"], c["attempts"])) if 0 < p0 < 1 else None,
            "sends_per_arm_for_win_rate": need}


# ------------------------------------------------------------------------------------------------ one experiment

def experiment(segs, key: str, rows: list, would: list, cfgs: dict, run_cfg: dict | None, hours, run_sends_per_hour) -> dict:
    conf = cfgs.get(key)
    in_scope = [r for r in rows if _arm(r, key) is not None]
    conf_arms = (conf or {}).get("arms") or []
    arms = [_label(a) for a in conf_arms] or sorted({_arm(r, key) for r in in_scope}, key=lambda x: (_num(x) is None, _num(x) or 0, x))
    weights = (conf or {}).get("weights") or [1.0] * len(arms)
    wmap = {a: float(w) for a, w in zip(arms, weights)}
    wsum = sum(wmap.values()) or 1.0
    control, why, warn = _control(key, conf_arms or arms, run_cfg, conf)
    out = {"key": key, "config": {k: (conf or {}).get(k) for k in ("arms", "weights", "seed", "config_seed", "run", "scope", "control")} if conf else None,
           "control": control, "control_why": why, "control_warning": warn}
    # the decisions each arm was assigned (the randomized unit): the engine's counters, else decisions.jsonl streamed, else
    # expected from the evaluations and the weights
    st = _status_arms(segs, key)
    ds = None if st else _decisions_stream(segs, key)
    evals = _evaluations(segs)
    if st:
        dsrc, dcounts = "status.jsonl experiments", {a: (st.get(a) or {}).get("decisions", 0) for a in arms}
    elif ds:
        dsrc, dcounts = "decisions.jsonl", {a: (ds.get(a) or {}).get("decisions", 0) for a in arms}
    elif evals:
        dsrc, dcounts = "expected: status counts_total.evaluation x the weight share", {a: evals * wmap.get(a, 1.0) / wsum for a in arms}
    else:
        dsrc, dcounts = None, {}
    src = st or ds or {}
    bal: dict = {"decisions": None}
    if st or ds:
        counts = {a: (src.get(a) or {}).get("decisions", 0) for a in arms}
        bal["decisions"] = {"src": dsrc, "n": sum(counts.values()), "counts": counts, "weights": wmap,
                            "chi2": stats.chi_square_balance(counts, wmap) if sum(counts.values()) else None,
                            "by_kind": {a: (ds.get(a) or {}).get("by_kind", {}) for a in arms} if ds else None}
    send_counts = {a: sum(1 for r in in_scope if _arm(r, key) == a) for a in arms}
    by_band, by_kind = _counts_by(in_scope, key, "band"), _counts_by(in_scope, key, "kind")
    bal.update(sends=send_counts, sends_chi2=stats.chi_square_balance(send_counts, wmap) if in_scope else None, by_band=by_band,
               by_kind=by_kind, band_independence=stats.chi_square_independence(by_band), kind_independence=stats.chi_square_independence(by_kind))
    if would:
        bal["would_sends"] = {a: sum(1 for r in would if _arm(r, key) == a) for a in arms}
    out["balance"] = bal
    # per arm: per send (the arms that applied), per decision (every attempt by its assigned arm)
    per, assigned = {}, {}
    for a in arms:
        ar = [r for r in in_scope if _arm(r, key) == a]
        x = _arm_stats(ar, run_sends_per_hour)
        x["by_leader_kind"] = _split(ar, "leader")
        x["by_tip_policy"] = _split(ar, "policy")
        sr = src.get(a) or {}
        x["opportunities"] = sr.get("opportunities")
        x["refused"] = dict(sorted((sr.get("refused") or {}).items())) if sr else None
        x["canary_wait"] = (sr.get("refused") or {}).get("canary_wait") if sr else None
        dc_ = dcounts.get(a)
        x["decisions"] = stats._clean(dc_) if dc_ is not None else None
        assigned[a] = _arm_stats([r for r in rows if _assigned(r, key) == a])
        x["assigned"] = {k: assigned[a][k] for k in ("attempts", "wins", "net_total")}
        x["wins_per_1k_decisions"] = stats._clean(1000 * assigned[a]["wins"] / dc_) if dc_ else None
        x["net_per_1k_decisions"] = stats._clean(1000 * assigned[a]["net_total"] / dc_) if dc_ else None
        per[a] = x
    out["decisions_src"] = dsrc
    out["arms"] = per
    # against the control: per decision (randomized), per send (descriptive), per send on Jito-led slots (X4's primary)
    vs: dict = {}
    c = per.get(control)
    crow = [r for r in in_scope if _arm(r, key) == control]
    cj = [r for r in crow if r["leader"] == "jito"]
    for a in arms:
        if a == control or not c:
            continue
        arow = [r for r in in_scope if _arm(r, key) == a]
        aj = [r for r in arow if r["leader"] == "jito"]
        vs[a] = {"per_decision": _per_decision(assigned[a], assigned[control], dcounts.get(a), dcounts.get(control)),
                 "per_send": _per_send(per[a], c, arow, crow),
                 "per_send_jito_led": _per_send(_arm_stats(aj), _arm_stats(cj), aj, cj) if aj and cj else None}
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


def _rel_drop(k: int, n: int, k0: int, n0: int) -> dict | None:
    """the relative drop of a rate, 1 - (k/n)/(k0/n0), with its 95% interval (the log rate ratio's normal interval, a
    half success added to an empty cell)"""
    import math
    if not n or not n0 or not k0:
        return None
    a, b = (k or 0.5), k0
    rr = (a / n) / (b / n0)
    se = math.sqrt(max(0.0, (1 - a / n) / a + (1 - b / n0) / b))
    lo, hi = rr * math.exp(-1.959964 * se), rr * math.exp(1.959964 * se)
    return {"drop": stats._clean(1 - (k / n) / (k0 / n0)), "ci95": [stats._clean(1 - hi), stats._clean(1 - lo)]}


def x4_rule(e: dict, rows: list | None = None) -> dict:
    """PLAN WP-11's X4 rule over `experiment`'s arms: go when the land rate drops less than 20% relative to the control,
    on the drop's 95% upper bound (review #11: a point estimate passes a true 30% drop about a quarter of the time at
    ~2,500 sends per arm), over the Jito-led sends (review #4: the BAM floor often bids the same for every arm on a
    BAM-led slot), and over every send beside it; STAGE1-PLAN §4's (`go_stage1`): no lost auctions and no fewer wins per
    send (one-sided p >= 0.05) at >= 1,000 sends per arm, and the same test per decision"""
    base = e.get("control")
    key = e.get("key") or KEYS["x4"]
    res = {}
    arms = e.get("arms") or {}
    b = arms.get(base) or {}
    rows = rows or []
    sel = lambda a, jito: [r for r in rows if _arm(r, key) == a and (not jito or r["leader"] == "jito")]  # noqa: E731
    for a, x in arms.items():
        r = {"n": x["attempts"], "land_rate": x["land_rate"], "land_rate_ci95": x["land_rate_ci95"], "net_per_attempt": x["net_per_attempt"],
             "net_ci95": x["net_per_attempt_ci95"]}
        if a != base and b.get("attempts"):
            for name, jito in (("jito_led", True), ("all", False)):
                xa, xb = sel(a, jito), sel(base, jito)
                d = _rel_drop(sum(t["landed"] for t in xa), len(xa), sum(t["landed"] for t in xb), len(xb)) if rows else None
                r["land_drop_" + name] = d
            prim = r.get("land_drop_jito_led") or r.get("land_drop_all")
            r["go"] = bool(prim and prim["ci95"][1] < X4_MAX_REL_DROP)
            r["go_basis"] = "the drop's 95% upper bound on Jito-led sends" if r.get("land_drop_jito_led") else "the drop's 95% upper bound on every send"
            v = (e.get("vs_control") or {}).get(a, {})
            wr = (v.get("per_send") or {}).get("win_rate") or {}
            r["fewer_wins_p"] = wr.get("p_less")
            r["fewer_wins_per_decision_p"] = ((v.get("per_decision") or {}).get("wins") or {}).get("p_less")
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
    hours_src = "trading hours"
    if not hours:
        # without warm-up and gate events (a pull without events.jsonl): the wall hours, meta.json's start to stop.json's end
        hours = sum((s.window.get("wall_hours") or 0) for s in segs) or None
        hours_src = "wall hours (no warm-up / gate events)" if hours else None
    run_cfg = _run_config(segs)
    run_sends_per_hour = (len(rows) / hours) if (hours and rows) else None
    d["sends_per_hour"] = stats._clean(run_sends_per_hour) if run_sends_per_hour else None
    d["hours_src"] = hours_src
    # review #1: the canary's one send a second binds when its refusals reach the sends: the arms compete for the slot
    cw, sent = _exec_total(segs, "exec.counts_total.reject_canary_wait"), _exec_total(segs, "exec.sent_total")
    d["canary_wait"] = {"refusals": cw, "sends": sent}
    if cw is not None and sent and cw >= sent:
        sec["caveats"].append(f"the canary's send slot binds: {cw} canary_wait refusals for {sent} sends; the arms compete for it, so per-arm sends "
                              "and net per hour depend on the other arms (net per hour is net per send x the run's sends per hour; read the "
                              "per-decision comparison for whether an effect exists)")
    d["segments"] = [s.name for s in segs]
    d["sends"] = len(rows)
    d["would_sends"] = len(would)
    d["trading_hours"] = stats._clean(hours) if hours else None
    d["money"] = {"source": "ledger.jsonl as the Rust side counts it (no dup line, nothing at or before the campaign's start), by the attempts' signatures",
                  **notes}
    if notes["landed_without_ledger"]:
        sec["caveats"].append(f"{notes['landed_without_ledger']} landing(s) without a ledger line: their money is unknown (counted apart, never 0)")
    if notes["lines_before_start_of_our_attempts"]:
        sec["caveats"].append(f"{notes['lines_before_start_of_our_attempts']} ledger line(s) before the campaign's start name our attempts' signatures "
                              "and are left out")
    if would and not rows:
        sec["caveats"].append("would-sends only (a shadow or dry run, or a closed gate): the balance holds, nothing landed")
    if not hours:
        sec["caveats"].append("no trading or wall hours: no net per hour")
    elif hours_src != "trading hours":
        sec["caveats"].append(f"net per hour on {hours_src}: pull events.jsonl for the trading hours")
    if any(r["win"] and tokens.classify(r["mint"]) == "unknown" for r in rows):
        sec["caveats"].append("a win without its route's mint is counted `unknown`, neither meme nor common")
    d["balance"] = {k: balance(seg, k) for k in keys}
    d["experiments"] = {}
    for k in keys:
        name = NAMES.get(k, k)
        if which not in ("all", name):
            continue
        e = experiment(segs, k, rows, would, cfgs, run_cfg, hours, run_sends_per_hour)
        d["experiments"][name] = e
        if e.get("control_warning"):
            sec["caveats"].append(e["control_warning"])
        dec = (e["balance"].get("decisions") or {}).get("chi2")
        if dec and dec["p"] is not None and dec["p"] < 0.01:
            sec["caveats"].append(f"{name}: decisions per arm are unbalanced against the weights (p={dec['p']}): the assignment is suspect")
        b = d["balance"].get(k) or {}
        if b.get("chi2") and b["chi2"]["p"] is not None and b["chi2"]["p"] < 0.01:
            sec["caveats"].append(f"{k}: arm counts are unbalanced against the weights (p={b['chi2']['p']}); results suspect (an arm changes the "
                                  "funnel: read the per-decision comparison; or the assignment is off: see the decisions' balance)")
        bi = e["balance"].get("band_independence")
        if bi and bi["p"] is not None and bi["p"] < 0.01 and name != "size":
            sec["caveats"].append(f"{name}: the bands differ by arm (p={bi['p']}): compare within bands")
    if which in ("all", "x2") and KEYS["x2"] in keys:
        d["x2"] = x2(rows)
    if which in ("all", "x4") and "x4" in d["experiments"]:
        d["x4"] = x4_rule(d["experiments"]["x4"], rows)
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
