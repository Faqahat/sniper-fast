#!/usr/bin/env python3
# BUkpShoE profile (read-only) from bukp/trips_<run>.json: trigger types, speed, entry state, sizing, exits (hold modes,
# exit multiple vs peak, what preceded each sell), concurrency, P&L split. -> printed + bukp/profile.json
import json, collections, statistics, sys
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/bukp"
runs = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
T = {r: json.load(open(f"{OUT}/trips_{r}.json")) for r in runs}
def pct(x, ps=(10, 25, 50, 75, 90)):
    x = sorted(v for v in x if v is not None)
    return [round(x[min(len(x) - 1, int(p / 100 * len(x)))], 3) for p in ps] if x else None
prof = {}
for run, ts in T.items():
    cl = [t for t in ts if t["closed"]]
    P = {}
    ts_same = [t for t in ts if t["trig_sell"] and t["trig_sell"]["dslot"] == 0]
    P["n"] = len(ts); P["closed"] = len(cl)
    P["trigger"] = dict(same_slot_sell=round(len(ts_same) / len(ts), 3),
                        sell_prev_1_3=round(sum(1 for t in ts if t["trig_sell"] and t["trig_sell"]["dslot"] > 0 and not (t["trig_sell"] and t["trig_sell"]["dslot"] == 0)) / len(ts), 3),
                        no_sell_in_3_slots=round(sum(1 for t in ts if not t["trig_sell"]) / len(ts), 3),
                        same_slot_sell_sol=pct([t["trig_sell"]["sol"] for t in ts_same]), same_slot_sell_move=pct([t["trig_sell"]["move"] for t in ts_same]),
                        same_slot_sell_who=collections.Counter(t["trig_sell"]["who"] for t in ts_same).most_common(8),
                        idx_after_sell=pct([t["trig_sell"]["didx"] for t in ts_same]),
                        largest_sell_any_window_sol=pct([t["trig_sell"]["sol"] for t in ts if t["trig_sell"]]))
    st = lambda f: pct([t["state"].get(f) for t in ts])
    P["state"] = {f: st(f) for f in ("age", "curve", "ath_r", "dd3", "dd10", "ret10", "ret30", "ret100", "net3", "net10", "nb10", "ns10", "nw30", "nwal", "peak", "dev_sold", "ins_sold", "nbot_hold", "quiet")}
    P["hours"] = collections.Counter(t["state"]["hour"] for t in ts).most_common()
    P["size"] = pct([t["buys"][0]["sol"] for t in ts]); P["size_values"] = collections.Counter(round(t["buys"][0]["sol"], 2) for t in ts).most_common(10)
    P["scale_in"] = sum(1 for t in ts if t["nb"] > 1); P["multi_sell"] = sum(1 for t in ts if t["ns"] > 1)
    P["hold"] = pct([t["hold"] for t in cl]); P["hold_hist"] = collections.Counter(min(t["hold"] // 20 * 20, 2000) for t in cl if t["hold"] is not None).most_common(12)
    P["exit_mult"] = pct([t["exit_mult"] for t in cl]); P["peak_mult"] = pct([t["peak_mult"] for t in cl])
    prevs = [t["sells"][-1]["prev"] for t in cl if t["sells"][-1]["prev"]]
    P["exit_prev"] = collections.Counter((p["side"], "same" if p["dslot"] == 0 else ("1-3" if p["dslot"] <= 3 else ">3")) for p in prevs).most_common()
    P["exit_after_big_buy3"] = round(sum(1 for t in cl if t["sells"][-1]["maxb3"] >= 0.5) / max(1, len(cl)), 3)
    P["exit_after_big_sell3"] = round(sum(1 for t in cl if t["sells"][-1]["maxs3"] >= 0.5) / max(1, len(cl)), 3)
    # concurrency: open positions at each entry
    ev = sorted([(t["slot"], 1) for t in cl] + [(t["slot"] + t["hold"], -1) for t in cl])
    cur = 0; mx = 0; at_entry = []
    for s, dlt in ev:
        cur += dlt; mx = max(mx, cur)
        if dlt == 1: at_entry.append(cur)
    P["concurrency"] = dict(max=mx, at_entry=pct(at_entry))
    pn = [t["pnl_curve"] for t in cl]
    P["pnl"] = round(sum(pn), 2); P["win"] = round(sum(1 for x in pn if x > 0) / len(pn), 3)
    P["pnl_wo_top1pct"] = round(sum(sorted(pn)[:-max(1, len(pn) // 100)]), 2)
    P["pnl_by_size"] = {f"{lo}-{hi}": (sum(1 for t in cl if lo <= t["buys"][0]["sol"] < hi), round(sum(t["pnl_curve"] for t in cl if lo <= t["buys"][0]["sol"] < hi), 2)) for lo, hi in ((0, 0.6), (0.6, 0.8), (0.8, 1.0), (1.0, 1.3), (1.3, 2), (2, 10))}
    P["pnl_by_hold"] = {f"{lo}-{hi}": (sum(1 for t in cl if lo <= t["hold"] < hi), round(sum(t["pnl_curve"] for t in cl if lo <= t["hold"] < hi), 2)) for lo, hi in ((0, 30), (30, 100), (100, 160), (160, 600), (600, 1200), (1200, 1500), (1500, 10 ** 6))}
    P["pnl_by_trigger"] = {k: (len(v), round(sum(t["pnl_curve"] for t in v), 2)) for k, v in (("same-slot sell", [t for t in cl if t["trig_sell"] and t["trig_sell"]["dslot"] == 0]), ("earlier sell", [t for t in cl if t["trig_sell"] and t["trig_sell"]["dslot"] > 0]), ("no sell", [t for t in cl if not t["trig_sell"]]))}
    prof[run] = P
json.dump(prof, open(f"{OUT}/profile.json", "w"), indent=1)
for run, P in prof.items():
    print(f"\n===== {run}: {P['n']} trips ({P['closed']} closed); curve P&L {P['pnl']:+.2f} SOL, win {P['win']:.0%}, w/o top 1% {P['pnl_wo_top1pct']:+.2f}")
    for k in ("trigger", "size", "size_values", "scale_in", "multi_sell", "hold", "hold_hist", "exit_mult", "peak_mult", "exit_prev", "exit_after_big_buy3", "exit_after_big_sell3", "concurrency", "pnl_by_size", "pnl_by_hold", "pnl_by_trigger"):
        print(f"  {k}: {P[k]}")
    print("  state:", {k: v for k, v in P["state"].items()})
    print("  hours (PKT):", P["hours"][:24])
