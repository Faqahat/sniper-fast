#!/usr/bin/env python3
# sssssDdM profile (read-only) from sssss/trips_<run>.json: trigger types, speed, entry state, sizing rule, exits (hold
# modes, exit multiple vs peak, what preceded each sell), concurrency, fleet overlap, P&L split.
# -> printed + sssss/profile.json      (adapted from bukp/bk2_profile.py)
import json, collections, sys
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/sssss"
runs = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
T = {r: json.load(open(f"{OUT}/trips_{r}.json")) for r in runs}
def pct(x, ps=(10, 25, 50, 75, 90)):
    x = sorted(v for v in x if v is not None)
    return [round(x[min(len(x) - 1, int(p / 100 * len(x)))], 3) for p in ps] if x else None
def split(cl, lab, f):
    g = collections.defaultdict(list)
    for t in cl: g[f(t)].append(t["pnl_curve"])
    return {k: (len(v), round(sum(v), 2), round(float(np.mean(v)), 4), round(float(np.mean([x > 0 for x in v])), 2)) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}
def trig_type(t):
    l = t["last"]
    if not l: return "none"
    side = "buy" if l["side"] == "B" else "sell"
    when = "same" if l["dslot"] == 0 else ("1slot" if l["dslot"] == 1 else "2+slots")
    return f"{when}-{side}"
def sol_band(x, edges=(0.1, 0.3, 0.5, 1.0, 2.0)):
    for e in edges:
        if x < e: return f"<{e}"
    return f">={edges[-1]}"
prof = {}
for run, ts in T.items():
    cl = [t for t in ts if t["closed"]]
    P = {"n": len(ts), "closed": len(cl)}
    P["trigger_type"] = collections.Counter(trig_type(t) for t in ts).most_common()
    same = [t["last"] for t in ts if t["last"] and t["last"]["dslot"] == 0]
    P["same_slot_last"] = {s: dict(n=len([l for l in same if l["side"] == s]), sol=pct([l["sol"] for l in same if l["side"] == s]), move=pct([l["move"] for l in same if l["side"] == s]),
                                   didx=pct([l["didx"] for l in same if l["side"] == s]), dms=pct([l["dms"] for l in same if l["side"] == s]),
                                   who=collections.Counter(l["who"] for l in same if l["side"] == s).most_common(8)) for s in "BS"}
    # largest same-slot buy before the entry (any position in the slot)
    sb = [max([x for x in t["same"] if x["side"] == "B"], key=lambda x: x["sol"]) for t in ts if any(x["side"] == "B" for x in t["same"])]
    ss = [max([x for x in t["same"] if x["side"] == "S"], key=lambda x: x["sol"]) for t in ts if any(x["side"] == "S" for x in t["same"])]
    P["same_slot_max_buy"] = dict(share=round(len(sb) / len(ts), 3), sol=pct([x["sol"] for x in sb]), didx=pct([x["didx"] for x in sb]), dms=pct([x["dms"] for x in sb]))
    P["same_slot_max_sell"] = dict(share=round(len(ss) / len(ts), 3), sol=pct([x["sol"] for x in ss]), didx=pct([x["didx"] for x in ss]), dms=pct([x["dms"] for x in ss]))
    P["n_same_slot_before"] = pct([len(t["same"]) for t in ts])
    P["entry_idx_in_block"] = pct([t["idx"] for t in ts])
    st = lambda f: pct([t["state"].get(f) for t in ts])
    P["state"] = {f: st(f) for f in ("age", "curve", "ath_r", "from_bun", "ret1", "ret3", "ret10", "ret30", "ret100", "dd3", "dd10", "net3", "net10", "nb3", "ns3", "nb10", "ns10",
                                     "nw10", "nw30", "ntr", "nwal", "peak", "dev_sold", "ins_sold", "nbot_hold", "fam_hold", "quiet")}
    P["hours"] = sorted(collections.Counter(t["state"]["hour"] for t in ts).items())
    P["size"] = pct([t["buys"][0]["sol"] for t in ts]); P["size_pct_curve"] = pct([t["buys"][0]["sol"] / t["buys"][0]["vsol"] * 1e11 for t in ts])
    P["own_impact_pct"] = pct([t["buys"][0]["move"] for t in ts])
    P["scale_in"] = sum(1 for t in ts if t["nb"] > 1); P["multi_sell"] = sum(1 for t in ts if t["ns"] > 1)
    P["hold"] = pct([t["hold"] for t in cl]); P["hold_hist20"] = sorted(collections.Counter(min(t["hold"] // 20 * 20, 3000) for t in cl).items())[:40]
    P["hold_fine"] = sorted(collections.Counter(t["hold"] for t in cl if t["hold"] <= 40).items())
    P["exit_mult"] = pct([t["exit_mult"] for t in cl]); P["peak_mult"] = pct([t["peak_mult"] for t in cl]); P["min_mult"] = pct([t["min_mult"] for t in cl])
    P["exit_vs_peak"] = pct([t["exit_mult"] / t["peak_mult"] for t in cl if t["peak_mult"]])
    prevs = [t["sells"][-1]["prev"] for t in cl if t["sells"][-1]["prev"]]
    P["exit_prev"] = collections.Counter((p["side"], "same" if p["dslot"] == 0 else ("1-3" if p["dslot"] <= 3 else ">3"), sol_band(p["sol"])) for p in prevs).most_common(14)
    P["exit_prev_who"] = collections.Counter(p["who"] for p in prevs).most_common(10)
    P["exit_after_big_sell3"] = round(sum(1 for t in cl if t["sells"][-1]["maxs3"] >= 0.5) / len(cl), 3)
    P["exit_after_big_buy3"] = round(sum(1 for t in cl if t["sells"][-1]["maxb3"] >= 0.5) / len(cl), 3)
    P["exit_after_sib_trade3"] = round(sum(1 for t in cl if t["sells"][-1]["sib3"]) / len(cl), 3)
    P["exit_sell_didx_after_prev_same_slot"] = pct([t["sells"][-1]["prev"]["didx"] for t in cl if t["sells"][-1]["prev"] and t["sells"][-1]["prev"]["dslot"] == 0])
    ev = sorted([(t["slot"], 1) for t in cl] + [(t["slot"] + t["hold"], -1) for t in cl], key=lambda x: (x[0], x[1]))
    cur = 0; mx = 0; at = []
    for s, dlt in ev:
        cur += dlt; mx = max(mx, cur)
        if dlt == 1: at.append(cur)
    P["concurrency"] = dict(max=mx, at_entry=pct(at))
    P["fleet"] = dict(sib_holds_at_entry=round(sum(1 for t in ts if t["sibpos"]) / len(ts), 3), sib_trade_50slots_before=round(sum(1 for t in ts if t["fleet_before"]) / len(ts), 3))
    pn = [t["pnl_curve"] for t in cl]
    P["pnl"] = round(sum(pn), 2); P["win"] = round(float(np.mean([x > 0 for x in pn])), 3); P["pnl_wo_top1pct"] = round(sum(sorted(pn)[:-max(1, len(pn) // 100)]), 2)
    P["fees_est"] = round(len(cl) * (0.00012 + 0.0001 + 0.25 * 0.00006), 2)
    P["pnl_by_trigger"] = split(cl, "trig", trig_type)
    P["pnl_by_size"] = split(cl, "size", lambda t: sol_band(t["buys"][0]["sol"], (0.6, 0.8, 1.0, 1.3, 2.0)))
    P["pnl_by_hold"] = split(cl, "hold", lambda t: next((f"<{e}" for e in (10, 30, 100, 300, 1000, 3000) if t["hold"] < e), ">=3000"))
    P["pnl_by_curve"] = split(cl, "curve", lambda t: next((f"<{e}" for e in (35, 40, 50, 60, 70, 90) if t["state"].get("curve", 0) < e), ">=90"))
    P["pnl_by_age"] = split(cl, "age", lambda t: next((f"<{e}" for e in (25, 150, 750, 3000, 12000) if t["state"].get("age", 0) < e), ">=12000"))
    P["pnl_by_sib"] = split(cl, "sib", lambda t: "sib_holds" if t["sibpos"] else "alone")
    P["pnl_by_hour"] = split(cl, "hour", lambda t: f"{t['state']['hour'] // 3 * 3:02d}h")
    P["pnl_by_exit_ctx"] = split(cl, "exit", lambda t: "after big sell<=3sl" if t["sells"][-1]["maxs3"] >= 0.5 else ("after big buy<=3sl" if t["sells"][-1]["maxb3"] >= 0.5 else "other"))
    prof[run] = P
json.dump(prof, open(f"{OUT}/profile.json", "w"), indent=1)
for run, P in prof.items():
    print(f"\n===== {run}: {P['n']} trips ({P['closed']} closed); curve P&L {P['pnl']:+.2f} SOL (tx fees ~{P['fees_est']}), win {P['win']:.0%}, w/o top 1% {P['pnl_wo_top1pct']:+.2f}")
    for k, v in P.items():
        if k in ("n", "closed", "pnl", "win", "pnl_wo_top1pct", "fees_est"): continue
        if k == "state": print("  state:"); [print(f"     {kk}: {vv}") for kk, vv in v.items()]; continue
        print(f"  {k}: {v}")
