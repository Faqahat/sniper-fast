"""FILTER-TUNE common: load the extracts, build one row per live position (realized P&L) and one per live T2 skip (shadow paper)."""
import pickle, json, collections, os
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
D0 = "/home/moiz/sniper-data/filters3/tune"
RUNS = ["r37", "r38", "r39", "r40", "r41", "r42", "r43", "r44", "r45", "r46"]
SPLIT = datetime(2026, 11, 1, 12, 0, tzinfo=PKT).timestamp() * 1e9          # DEV | VAL inside r42
ATT0 = datetime(2026, 11, 2, 8, 0, tzinfo=PKT).timestamp() * 1e9            # attack WINDOW (owner's "about 08:00-08:40")
ATT1 = datetime(2026, 11, 2, 8, 40, tzinfo=PKT).timestamp() * 1e9
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
_cache = {}
def load(run):
    if run not in _cache: _cache[run] = pickle.load(open(f"{D0}/ex_{run}.pkl", "rb"))
    return _cache[run]
def pkt(t): return datetime.fromtimestamp(t / 1e9, PKT)
def period(run, t):
    if run in ("r43", "r44", "r45", "r46"): return "HOLD"
    if run == "r42" and t >= SPLIT: return "VAL"
    return "DEV"

def holders_feats(hs, whale=None):
    """fill-time (OUR LANDING, before our buy) holder features from ann.holders (>= 2% holders, hold clocks)"""
    f = {}
    hs = hs or []
    oth = [h for h in hs if h.get("w") != whale]
    f["fresh_sum"] = sum(h.get("pct", 0) for h in hs if (h.get("n") or 0) <= 1)
    f["fresh_n"] = sum(1 for h in hs if (h.get("n") or 0) <= 1)
    f["oth_max"] = max([h.get("pct", 0) for h in oth] or [0])
    f["oth_sum"] = sum(h.get("pct", 0) for h in oth)
    f["n_hold"] = len(hs)
    risky = [h for h in hs if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3]
    f["risky_sum"] = sum(h.get("pct", 0) for h in risky)
    f["risky_max"] = max([h.get("pct", 0) for h in risky] or [0])
    f["risky_n"] = len(risky)
    f["risky_maxhz"] = max([h.get("hz3") or 0 for h in risky] or [0])
    f["risky_minage"] = min([h.get("age") or 0 for h in risky] or [9999])
    f["risky_maxn"] = max([h.get("n") or 0 for h in risky] or [0])
    f["risky_maxrisk"] = max([h.get("risk") or 0 for h in risky] or [0])
    big = [h for h in hs if h.get("pct", 0) >= 6]
    f["st_hz"] = max([h.get("hz3") or 0 for h in big if (h.get("risk") or 0) >= 5] or [0])
    f["st_pct"] = max([h.get("pct", 0) for h in big if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3] or [0])
    f["st_age"] = min([h.get("age") or 0 for h in big if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3] or [9999])
    f["st_n"] = max([h.get("n") or 0 for h in big if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3] or [0])
    hc = [h for h in hs if h.get("pct", 0) >= 6 and (h.get("n") or 0) >= 5 and (h.get("h3") or 0) >= 0.3]
    f["hc_pct"] = max([h.get("pct", 0) for h in hc] or [0])
    f["hc_h3"] = max([h.get("h3") or 0 for h in hc] or [0])
    f["hc_n"] = max([h.get("n") or 0 for h in hc] or [0])
    f["hc_age"] = min([h.get("age") or 0 for h in hc] or [9999])
    return f

def positions(runs=RUNS, seed=None):
    """one row per realized live position, in realized order per run. gcr = the dashboard's bad-creator flag (run-only ledger unless seed)"""
    rows = []
    led = collections.defaultdict(lambda: [0, 0.0])
    if seed:
        for c, d in json.load(open(seed)).items(): led[c] = [d["n"], d["sum"]]
    for run in runs:
        D = load(run)
        if not seed: led = collections.defaultdict(lambda: [0, 0.0])
        # replay the ledger in record order: arms flag, realizations add
        evs = [(a["_seq"], 0, k) for k, a in D["arms"].items()] + [(s, 1, (k, p)) for k, p, kd, s in D["real"]]
        evs.sort()
        gflag, gled = {}, {}
        for s, typ, x in evs:
            if typ == 0:
                a = D["arms"][x].get("ann")
                if a is not None:
                    c = a.get("creator"); n, sm = led[c] if c else (0, 0.0)
                    gflag[x] = bool(c and a.get("cr_pct", 0) >= 3 and n >= 2 and sm <= -0.05); gled[x] = (n, sm)
            else:
                k, p = x
                a = (D["arms"].get(k) or {}).get("ann")
                if a and a.get("creator") and a.get("cr_pct", 0) >= 3: led[a["creator"]][0] += 1; led[a["creator"]][1] += p / 1e9
        for i, (k, p, kd, s) in enumerate(D["real"]):
            a = D["arms"].get(k, {}); f = D["fills"].get(k, {}); c = D["closes"].get(k, {})
            fa = f.get("ann") or {}
            kind = a.get("kind", kd or "t2")
            t = f.get("t") or (a.get("trig") or {}).get("t") or 0
            trig = a.get("trig") or {}; dump = a.get("dump") or {}
            whale = trig.get("wallet") if kind == "t2" else dump.get("seller")
            r = {"run": run, "k": k, "mint": k[1], "kind": kind, "pnl": p / 1e9, "t": t, "seq": s, "per": period(run, t),
                 "day": pkt(t).strftime("%m-%d"), "att": ATT0 <= t < ATT1 and run == "r42",
                 "quiet": a.get("quiet") or {}, "v2": a.get("v2") or {}, "ann": a.get("ann") or {}, "nb": a.get("nb"),
                 "trig": trig, "dump": dump, "arm_holders": a.get("holders") or [], "whale": whale,
                 "fann": fa, "has_fann": bool(fa), "sat": f.get("slots_after_trigger"), "ms_rx": f.get("ms_send_to_rx"),
                 "client": f.get("client"), "path": f.get("path"), "spend": (a.get("spend") or f.get("spend") or 0) / 1e9,
                 "fill_slot": f.get("slot"), "fill_idx": f.get("idx"), "exit_why": c.get("exit_why"),
                 "sell_slot": (c.get("sell_land") or [None])[0], "gcr": gflag.get(k, False), "gled": gled.get(k)}
            r.update(holders_feats(fa.get("holders"), whale))
            g = fa.get("guard") or {}
            r["guard"] = bool(g.get("block")); r["guard_pct"] = g.get("pct") or 0; r["guard_set_n"] = len(g.get("set") or [])
            r["guard_sign"] = sum(x.get("sign_pct") or 0 for x in g.get("set") or [])
            r["st"] = bool(fa.get("st_block")); r["grp"] = bool(fa.get("grp_block")) if "grp_block" in fa else r["risky_sum"] >= 6.0
            r["ctx85"] = bool(fa.get("ctx85")); r["ob6"] = fa.get("ob6") or 0; r["depth"] = fa.get("depth") or 0
            r["hc"] = r["hc_pct"] > 0
            # followed (QUIET3's label): a buy by another wallet (not us, not the whale, not the arm's holders) after our first buy up to
            # our last sell landing; inslot = such a buy in our fill slot after us; first2 = within 2 slots of our fill
            tp = D["tape"].get(k[1], [])
            excl = OURS | {whale} | {h.get("w") for h in r["arm_holders"]}
            fs, fi, ss = r["fill_slot"] or 0, r["fill_idx"] or 0, r["sell_slot"] or ((r["fill_slot"] or 0) + 3)
            fol = [x for x in tp if x[3] and x[2] not in excl and (x[0], x[1]) > (fs, fi) and x[0] <= ss]
            r["followed"] = bool(fol); r["fol_n"] = len({x[2] for x in fol}); r["fol_sol"] = sum(x[4] for x in fol) / 1e9
            sells = [x for x in tp if not x[3] and x[2] not in OURS and (x[0], x[1]) > (fs, fi) and x[0] <= ss]
            r["sold_in_hold"] = sum(x[4] for x in sells) / 1e9
            r["whale_sold_in_hold"] = sum(x[4] for x in sells if x[2] == whale) / 1e9
            rows.append(r)
    return rows

def skips(runs=RUNS):
    """one row per live T2 skip with the shadow's paper (row c net_cheap scaled to the live size), as filters_report.py"""
    out = []
    for run in runs:
        D = load(run)
        live_size = None
        for k, a in sorted(D["arms"].items(), key=lambda x: x[1]["_seq"]):
            if a.get("kind", "t2") == "t2": live_size = (a.get("spend") or 0) / 1e9 or None; break
        for s in D["skips"]:
            sig = s["trig"]["sig"]; sa = D["sh_arm"].get(sig); w = sa["w"] if sa else None
            v = None; sf = None
            if w is not None and w in D["sh_exit"]:
                v = D["sh_exit"][w]["net_cheap"]; sf = D["sh_fill"].get(w)
                if live_size and sf and sf.get("sol_in"): v = v * live_size / sf["sol_in"]
            t = s["trig"].get("t") or 0
            out.append({"run": run, "why": s["why"], "sig": sig, "mint": s["trig"].get("mint"), "t": t, "per": period(run, t), "day": pkt(t).strftime("%m-%d"),
                        "att": ATT0 <= t < ATT1 and run == "r42", "paper": v, "sh_fill": sf, "quiet": s.get("quiet") or {}, "v2": s.get("v2") or {},
                        "ann": s.get("ann") or {}, "nb": s.get("nb"), "trig": s["trig"], "seq": s["_seq"]})
    return out

def summ(vals):
    w = [x for x in vals if x > 0]; l = [x for x in vals if x <= 0]
    return {"n": len(vals), "win_n": len(w), "win": round(sum(w), 3), "lose_n": len(l), "lose": round(sum(l), 3), "saved": round(-sum(vals), 3),
            "prec": round(len(l) / len(vals), 3) if vals else None}
def wo_top(vals, k=5):
    """saved without the k trades that help the filter most (the k biggest losses it blocks)"""
    s = sorted(vals)
    return round(-sum(s[k:]), 3)
