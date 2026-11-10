#!/usr/bin/env python3
"""T2-WINDOWS step 6, IDEA A: smarter re-arms. Every re-arm candidate (a >= 6 % sell; armed / skipped no_holder / age / r5) of the tape-covered
live hours, scored per variant against the live rule each run actually ran (R5 skip on in r48-r49 only).
  kept live window   -> live realized - its failed-try fees (+ the sim's mechanics delta when the variant changes gap / size / stops)
  dropped live window -> its money is removed (PROVEN part)
  added window        -> sim money [ESTIMATE], raw and calibrated (minus the period's per-window gap sim - live on live re-arm windows);
                         0 when a live position is open at its fill (one position) or a live window is armed on the mint; a later live
                         fill inside its position is displaced (its realized removed)
Periods (agent task): fit = r39-r41 + r42 < 11-01 12:00 PKT; choose = r42 after + r44-r46; final = r47-r49.
usage: e6_rearm.py [PERIODS]  -> /home/it/sniper-data/filters3/t2windows/rearm.json"""
import sys, json, collections, math
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L, t2score as S

ELIG = ("armed", "rearm_no_holder", "rearm_age", "rearm_r5")
R5_LIVE_RUNS = (48, 49)


def mech_of(v):
    h, g, sz, q = v.get("h", 6), v.get("gap", 20), v.get("size"), v.get("q", True)
    if sz: return {6: {0.30: "s30", 0.45: "s45", 0.65: "s65"}, 0: {0.45: "h0s45"}, 3: {0.45: "h3s45"}}[h][sz]
    if not q: return "noq" if h == 6 else "h0noq"
    return {(6, 20): "m0", (3, 20): "h3", (0, 20): "h0", (6, 10): "g10", (6, 30): "g30", (6, 40): "g40", (0, 10): "g10h0", (0, 30): "g30h0"}[(h, g)]


def r5_of(x):
    r5 = (x["rec"] or {}).get("r5")
    if r5 is not None: return bool(r5["all4"])
    return bool((x.get("r5p") or {}).get("all4"))


def top_pct(x):
    return max((p for w, p in x.get("h", [])), default=0.0)


def selected(x, v):
    """does variant v arm a window on candidate x (signing-time features only: dump record, holders at dump + 2, R5 at the check,
    dip bots before the dump)"""
    if x["why"] not in ELIG: return False
    a = x["anc"]
    if (a.get("vsol") or 0) >= 100e9: return False
    if v.get("live") or (v.get("keep_live") and x["why"] == "armed"):   # the live rule as each run ran it
        return x["why"] == "armed"
    age = a.get("age_slots") or 0
    if age > v.get("amax", 141) or age < v.get("amin", 0): return False
    pct = a.get("pct") or 0
    lo, hi = v.get("band", (0, 999))
    if not (lo <= pct < hi): return False
    h = v.get("h", 6)
    if h > 0 and top_pct(x) < h: return False
    r5 = v.get("r5", "live")
    if r5 == "live": r5 = x["run"] in R5_LIVE_RUNS
    if r5 and h >= 6 and r5_of(x): return False
    if r5 and h < 6 and top_pct(x) >= 1 and (x.get("r5p") or {}).get("all4"): return False
    b = v.get("bots")
    if b == "tok" and not x.get("bots_tok"): return False
    if b == "notok" and x.get("bots_tok"): return False
    if b == "glob_hi" and (x.get("bots_glob") or 0) < v.get("glob_thr", 0): return False
    if v.get("seller_not_cr") and x.get("seller_cr"): return False
    return True


def score(X, P, v, gaps, hours):
    pos = S.Positions(P); mech = mech_of(v)
    rows = collections.defaultdict(lambda: collections.defaultdict(float)); adds = collections.defaultdict(list); rems = collections.defaultdict(list)
    events = []
    for x in X:
        if x["c"] != "re" or x.get("err") or x["per"] not in ("fit", "choose", "final"): continue
        sel = selected(x, v); live = x["why"] == "armed"
        if not sel and not live: continue
        per = x["per"]; d = rows[per]
        if live:
            lm = (x["live_pnl"] or 0.0) - (x.get("live_fees") or 0.0)
            if not sel:
                d["rem_n"] += 1; d["rem_sol"] -= lm; rems[per].append(-lm)
                d["rem_stress"] -= lm + (x.get("live_stress") or 0.0)
                continue
            if mech != "m0":
                dv = S.money(x, P, mech)[0] - S.money(x, P, "m0")[0]
                d["mech_sol"] += dv; adds[per].append(dv)
                s_, s0 = x["sims"][mech], x["sims"]["m0"]
                d["mech_stress"] += ((s_["c2"] - s0["c2"]) - (s_["c0"] - s0["c0"])) / 1e9 + dv
            continue
        events.append(x)
    # added windows, chronological, one position at a time
    events.sort(key=lambda x: x["anc"]["t"])
    for x in events:
        per = x["per"]; d = rows[per]; s = x["sims"].get(mech) or {}
        d["cand"] += 1
        if s.get("noarm"): d["noarm"] += 1; continue
        t0 = x["anc"]["t"]; t1 = t0 + int((s.get("E", 0) + 800) * 1e6)
        if pos.mint_armed(x["mint"], t0, t1): d["blk_mint"] += 1; continue
        m, p = S.money(x, P, mech)
        if s["p"] > 0 and s.get("fcc"):
            tf = int((s["fcc"] + x["off"]) * 1e6)
            if pos.busy(tf): d["blk_pos"] += 1; continue
            if s["p"] >= 0.5:
                H = P["cal"][x["run"]]["H"]
                te = tf + int((H + 300) * 1e6)
                disp = pos.displaced(tf, te)
                if disp: d["disp_n"] += len(disp); d["disp_sol"] -= sum(disp) * s["p"]
                pos.added.append((tf, te))
        sp = {"s30": 0.30, "s45": 0.45, "s65": 0.65, "h0s45": 0.45, "h3s45": 0.45}.get(mech) or (P["cal"][x["run"]]["re_spend"] / 1e9)
        own = P["cal"][x["run"]]["re_spend"] / 1e9
        cal = m - gaps[per] * (sp / own)
        d["add_n"] += 1; d["add_fill"] += p; d["add_raw"] += m; d["add_cal"] += cal
        d["add_win"] += s.get("pos", 0) * p
        d["add_stress"] += cal + (s["c2"] - s["c0"]) / 1e9
        adds[per].append(cal)
    out = {}
    for per in ("fit", "choose", "final"):
        d = rows[per]; h = hours[per]
        net_raw = d["add_raw"] + d["rem_sol"] + d["mech_sol"] + d["disp_sol"]
        net_cal = d["add_cal"] + d["rem_sol"] + d["mech_sol"] + d["disp_sol"]
        contrib = sorted(adds[per] + rems[per])
        wo5 = sum(contrib[:-5]) + d["disp_sol"] if len(contrib) > 5 else min(0.0, sum(contrib))
        stress = d["add_stress"] + d["rem_stress"] + d["mech_stress"] + d["disp_sol"]
        out[per] = {"hours": round(h, 2), "added": int(d["add_n"]), "add_fills": round(d["add_fill"], 1), "add_win": round(d["add_win"] / d["add_fill"], 3) if d["add_fill"] else None,
                    "add_raw": round(d["add_raw"], 3), "add_cal": round(d["add_cal"], 3), "removed": int(d["rem_n"]), "rem_sol": round(d["rem_sol"], 3), "mech_sol": round(d["mech_sol"], 3),
                    "displaced": int(d["disp_n"]), "disp_sol": round(d["disp_sol"], 3), "blk_pos": int(d["blk_pos"]), "blk_mint": int(d["blk_mint"]), "noarm": int(d["noarm"]),
                    "net_raw": round(net_raw, 3), "net_cal": round(net_cal, 3), "day_cal": round(net_cal / h * 24, 2) if h else None, "day_raw": round(net_raw / h * 24, 2) if h else None,
                    "wo5_cal": round(wo5, 3), "stress20_cal": round(stress, 3), "day_stress": round(stress / h * 24, 2) if h else None}
    return out


VARIANTS = {
    "LIVE": {"live": True},
    "RULE (live rule rebuilt)": {},
    "R5 on everywhere": {"r5": True},
    "R5 off everywhere": {"r5": False},
    "H3 holder>=3%": {"h": 3},
    "H0 no holder needed": {"h": 0},
    "H0 + R5 off": {"h": 0, "r5": False},
    "age<=300": {"amax": 300},
    "age<=600": {"amax": 600},
    "age<=1200": {"amax": 1200},
    "age any": {"amax": 10 ** 9},
    "age 142-600 only (added)": {"amax": 600, "amin": 142, "keep_live": True},
    "H0 + age<=300": {"h": 0, "amax": 300},
    "band 6-10% only": {"band": (6, 10)},
    "band 10-15% only": {"band": (10, 15)},
    "band >=15% only": {"band": (15, 999)},
    "gap 10": {"gap": 10},
    "gap 30": {"gap": 30},
    "gap 40": {"gap": 40},
    "no QUIET 6:2 stop": {"q": False},
    "H0 gap 10": {"h": 0, "gap": 10},
    "H0 gap 30": {"h": 0, "gap": 30},
    "size 0.30": {"size": 0.30},
    "size 0.45": {"size": 0.45},
    "size 0.65": {"size": 0.65},
    "dip bot on token before dump": {"bots": "tok"},
    "no dip bot on token": {"bots": "notok"},
    "H0 + dip bot on token": {"h": 0, "bots": "tok"},
    "H0 + no dip bot on token": {"h": 0, "bots": "notok"},
    "dumper not creator": {"seller_not_cr": True},
}


def gaps_of(X, P):
    g = {}
    for per in ("fit", "choose", "final"):
        n = 0; gap = 0.0
        for x in X:
            if x["c"] == "re" and x["live"] and not x.get("err") and x["per"] == per and "real_fill" in x:
                n += 1; gap += S.money(x, P, "m0", fees=False)[0] - (x["live_pnl"] or 0.0)
        g[per] = gap / n if n else 0.0
    return g


if __name__ == "__main__":
    X, P = S.load()
    merged = S.coverage(P); sh = S.seg_hours(P, merged)
    hours = collections.defaultdict(float)
    for (r, per), h in sh.items():
        if per in ("fit", "choose", "final"): hours[per] += h
    gaps = gaps_of(X, P)
    print("hours", {k: round(v, 1) for k, v in hours.items()}, "| re-arm sim gap per live window (SOL)", {k: round(v * 1e3, 2) for k, v in gaps.items()}, "mSOL")
    # bots global threshold = median over fit candidates
    gl = sorted(x.get("bots_glob") or 0 for x in X if x["c"] == "re" and not x.get("err") and x["per"] == "fit")
    thr = gl[len(gl) // 2] if gl else 0
    VARIANTS["dip bots busy globally (>= fit median)"] = {"bots": "glob_hi", "glob_thr": thr}
    VARIANTS["H0 + dip bots busy globally"] = {"h": 0, "bots": "glob_hi", "glob_thr": thr}
    res = {}
    for name, v in VARIANTS.items():
        res[name] = score(X, P, v, gaps, hours)
        o = res[name]
        print(f"{name:42s} " + " | ".join(f"{per}: +{o[per]['added']:4d}w {o[per]['add_fills']:6.1f}f -{o[per]['removed']:4d}w net {o[per]['net_cal']:+7.3f} ({o[per]['day_cal']:+6.2f}/d raw {o[per]['day_raw']:+6.2f}) w/o5 {o[per]['wo5_cal']:+6.3f} -20% {o[per]['day_stress']:+6.2f}/d"
                                     for per in ("fit", "choose", "final")), flush=True)
    json.dump({"hours": hours, "gaps": gaps, "glob_thr": thr, "variants": {k: dict(v) if not isinstance(v, dict) else {a: (list(b) if isinstance(b, tuple) else b) for a, b in v.items()} for k, v in VARIANTS.items()},
               "res": res}, open(f"{L.D}/rearm.json", "w"), indent=1)
