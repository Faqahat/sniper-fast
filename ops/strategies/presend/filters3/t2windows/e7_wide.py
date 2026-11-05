#!/usr/bin/env python3
"""T2-WINDOWS step 7, IDEA B: whales slightly under 6 % (5-6 %, 4-5 %) as extra T2 windows, with the CURRENT live filters applied
(proxies validated on the 6 % triggers, e5): create-slot (age 0), age-1 (age < 2), QUIET (since_last >= 1 & no cohort holder & whale's
dump followers < 4 or none), QUIET3-A (trades in 120 s <= 15 & whale dumps <= 3), lone whale (<= 1 buyer in 50 slots), creator ledger 2:0.05
(the creator's earlier live positions, any run, realized sum <= -0.05 SOL with >= 2 positions; creator from the engine's records of the mint),
one window per token (a live window armed on the mint -> skip), one position (a live position open at the fill -> 0; a live fill inside the
added position -> displaced). Trigger = the wide shadow's first >= 3 % crossing (= the T2 detector's rule at a lower threshold).
Money [ESTIMATE]: sim at the current config (0.55 SOL, H_cur = the 125 ms exit's measured fill -> sell landing) and at the run's own config;
calibrated by the period's per-window T2 gap (sim - live on live T2 windows, e5).
usage: e7_wide.py -> /home/moiz/sniper-data/filters3/t2windows/wide.json"""
import sys, json, collections, bisect
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L, t2score as S


def creator_ledger(X, P):
    """creator -> sorted [(t_close_ns, pnl)] of our live positions (records' creator per mint)"""
    cr_of = {}
    for x in X:
        c = (x.get("rec") or {}).get("creator")
        if c: cr_of.setdefault(x["mint"], c)
    led = collections.defaultdict(list)
    for r, ses, w, m, t0, t1, pnl, kind in P["live_pos"]:
        c = cr_of.get(m)
        if c: led[c].append((t1, pnl))
    for c in led: led[c].sort()
    return cr_of, led


def cr_skip(led, c, t):
    v = led.get(c)
    if not v: return False
    k = bisect.bisect_left(v, (t, -1e9))
    xs = v[:k]
    return len(xs) >= 2 and sum(p for _, p in xs) <= -0.05


def filters(x, v, cr_of, led):
    a = x["anc"]; age = a.get("age_slots") or 0
    if age == 0: return "create_slot"
    if age < 2: return "young_age"
    if v.get("quiet", True) and x["since_last"] >= 1 and x["coh"] == 0 and x["wh_fol"] < 4.0: return "quiet"
    if v.get("q3a", True) and x["n120"] <= 15 and x["wh_dumps"] <= 3: return "quiet3_a"
    if v.get("lone", True) and x["nb50"] <= 1: return "lone_whale"
    c = cr_of.get(x["mint"])
    if v.get("cr", True) and c and cr_skip(led, c, a["t"]): return "cr_loss"
    if age < v.get("amin", 0): return "age_band"
    return None


def score(X, P, v, gaps, hours, cr_of, led):
    pos = S.Positions(P); lo, hi = v["band"]
    rows = collections.defaultdict(lambda: collections.defaultdict(float)); contrib = collections.defaultdict(list)
    why = collections.defaultdict(collections.Counter)
    cand = sorted([x for x in X if x["c"] == "wide" and not x.get("err") and x["per"] in ("fit", "choose", "final") and lo <= (x["anc"].get("pct") or 0) < hi],
                  key=lambda x: x["anc"]["t"])
    last_win = {}
    mech = v.get("mech", "cur"); hj = 1 if mech == "cur" else 0
    for x in cand:
        per = x["per"]; d = rows[per]; d["cand"] += 1
        f = filters(x, v, cr_of, led)
        if f: why[per][f] += 1; continue
        s = x["sims"][mech]; t0 = x["anc"]["t"]; t1 = t0 + int((s.get("E", 0) + 400) * 1e6)
        if pos.mint_armed(x["mint"], t0, t1): why[per]["live_window_on_mint"] += 1; continue
        if last_win.get(x["mint"], 0) > t0: why[per]["added_window_on_mint"] += 1; continue
        last_win[x["mint"]] = t1
        m, p = S.money(x, P, mech, hj)
        if s["p"] > 0 and s.get("fcc"):
            tf = int((s["fcc"] + x["off"]) * 1e6)
            if pos.busy(tf): why[per]["position_open"] += 1; continue
            if s["p"] >= 0.5:
                H = P["H_cur"] if mech == "cur" else P["cal"][x["run"]]["H"]
                te = tf + int((H + 300) * 1e6)
                disp = pos.displaced(tf, te)
                if disp: d["disp_n"] += len(disp); d["disp_sol"] -= sum(disp) * s["p"]
                pos.added.append((tf, te))
        cal = m - gaps[per]
        why[per]["ADDED"] += 1
        d["add_n"] += 1; d["add_fill"] += p; d["raw"] += m; d["cal"] += cal; d["win"] += s.get("pos", 0) * p
        d["stress"] += cal + (s["c2"] - s["c0"]) / 1e9
        contrib[per].append(cal)
    out = {}
    for per in ("fit", "choose", "final"):
        d = rows[per]; h = hours[per]; c = sorted(contrib[per])
        net = d["cal"] + d["disp_sol"]; raw = d["raw"] + d["disp_sol"]
        out[per] = {"hours": round(h, 2), "cand": int(d["cand"]), "added": int(d["add_n"]), "fills": round(d["add_fill"], 1),
                    "win": round(d["win"] / d["add_fill"], 3) if d["add_fill"] else None, "raw": round(raw, 3), "cal": round(net, 3),
                    "day_raw": round(raw / h * 24, 2), "day_cal": round(net / h * 24, 2), "wo5": round(sum(c[:-5]) + d["disp_sol"], 3) if len(c) > 5 else round(min(0, sum(c)), 3),
                    "day_wo5": round((sum(c[:-5]) + d["disp_sol"]) / h * 24, 2) if len(c) > 5 else None,
                    "stress20": round(d["stress"] + d["disp_sol"], 3), "day_stress": round((d["stress"] + d["disp_sol"]) / h * 24, 2),
                    "displaced": int(d["disp_n"]), "disp_sol": round(d["disp_sol"], 3), "why": dict(why[per])}
    return out


VARIANTS = {
    "W5 5-6% + live filters": {"band": (5, 6)},
    "W4 4-5% + live filters": {"band": (4, 5)},
    "W45 4-6% + live filters": {"band": (4, 6)},
    "W5 own size/exit (run config)": {"band": (5, 6), "mech": "own"},
    "W4 own size/exit (run config)": {"band": (4, 5), "mech": "own"},
    "W5 no QUIET3-A": {"band": (5, 6), "q3a": False},
    "W5 no filters but age>=2": {"band": (5, 6), "quiet": False, "q3a": False, "lone": False, "cr": False},
    "W5 age>=10": {"band": (5, 6), "amin": 10},
    "W5 5.5-6%": {"band": (5.5, 6)},
}


def t2_gaps(X, P):
    g = {}
    for per in ("fit", "choose", "final"):
        n = 0; gap = 0.0
        for x in X:
            if x["c"] == "t2" and x["live"] and not x.get("err") and x["per"] == per and "real_fill" in x:
                n += 1; gap += S.money(x, P, "own", fees=False)[0] - (x["live_pnl"] or 0.0)
        g[per] = gap / n if n else 0.0
    return g


if __name__ == "__main__":
    X, P = S.load()
    merged = S.coverage(P); sh = S.seg_hours(P, merged)
    hours = collections.defaultdict(float)
    for (r, per), h in sh.items():
        if per in ("fit", "choose", "final") and r >= 41: hours[per] += h      # the wide shadow (the 3-6 % triggers) exists from r41
    gaps = t2_gaps(X, P)
    cr_of, led = creator_ledger(X, P)
    print("hours", {k: round(v, 1) for k, v in hours.items()}, "| T2 sim gap per live window", {k: round(v * 1e3, 2) for k, v in gaps.items()}, "mSOL")
    res = {}
    for name, v in VARIANTS.items():
        o = score(X, P, v, gaps, hours, cr_of, led); res[name] = o
        print(f"{name:32s} " + " | ".join(f"{per}: {o[per]['added']:4d}w {o[per]['fills']:6.1f}f win {o[per]['win'] or 0:.2f} {o[per]['cal']:+7.3f} ({o[per]['day_cal']:+6.2f}/d raw {o[per]['day_raw']:+6.2f}) w/o5 {o[per]['wo5']:+6.3f} -20% {o[per]['day_stress']:+6.2f}/d disp {o[per]['displaced']}"
                                      for per in ("fit", "choose", "final")), flush=True)
    for per in ("fit", "choose", "final"): print(per, "W45 why:", res["W45 4-6% + live filters"][per]["why"])
    json.dump({"hours": hours, "gaps": gaps, "variants": {k: {a: (list(b) if isinstance(b, tuple) else b) for a, b in v.items()} for k, v in VARIANTS.items()}, "res": res},
              open(f"{L.D}/wide.json", "w"), indent=1)
