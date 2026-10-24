#!/usr/bin/env python3
# READ-ONLY, offline: summaries of perlaunch_q9z.json (collector windows): results by behaviour / quote / slot, landing,
# landing spend, size tiers and what sets them, exit ladder, later-buy triggers. -> an_launch.txt (printed)
import os, json, collections, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(HERE, "perlaunch_q9z.json")))
R = list(P.values())
def q(xs, ps=(0.1, 0.25, 0.5, 0.75, 0.9)):
    xs = sorted(x for x in xs if x is not None)
    return [round(xs[int(p * (len(xs) - 1))], 4) for p in ps] if xs else None
def line(name, rs):
    v = [r["sol_result"] for r in rs]
    if not v: return
    print(f"  {name:44} n {len(v):4d}  SOL {sum(v):+8.2f}  mean {st.mean(v):+.4f}  med {st.median(v):+.4f}  win {sum(1 for x in v if x > 0) / len(v):.0%}")
print("== realized SOL from exact lamport deltas of all its txs per launch (collector windows; SOL-quoted only, non-SOL rows count fees only)")
for beh in ("snipe", "later"):
    for f in (1, 0):
        line(f"{beh} {'filled' if f else 'failed (attempt only)'} SOL-quoted", [r for r in R if r["beh"] == beh and r["filled"] == f and r["quote"] == "SOL" and not r["may"]])
line("ALL SOL-quoted", [r for r in R if r["quote"] == "SOL"])
print("  by slot of the first attempt (SOL-quoted, filled + failed):")
for k, sel in (("create slot", lambda r: r["off"] == 0), ("next slot", lambda r: r["off"] == 1), ("2-25 slots (<5 s)", lambda r: 2 <= r["off"] <= 25),
               ("26-150 (5-30 s)", lambda r: 26 <= r["off"] <= 150), ("151-1500 (30 s-5 min)", lambda r: 151 <= r["off"] <= 1500), (">1500 (>5 min)", lambda r: r["off"] > 1500)):
    line(k, [r for r in R if r["quote"] == "SOL" and sel(r)])
print("  by run (SOL-quoted):")
for run in ("R1", "R2"): line(run, [r for r in R if r["quote"] == "SOL" and r["run"] == run])
print("\n== failed-tx costs inside these launches")
for beh in ("snipe", "later"):
    rs = [r for r in R if r["beh"] == beh]
    print(f"  {beh}: failed txs {sum(r['n_fail'] for r in rs)}, of which with a priority fee {sum(r['n_fail_buyfee'] for r in rs)}, fees {sum(r['fail_fee'] for r in rs):.2f} SOL")
F = [r for r in R if r["filled"] and r.get("buy_sol")]
print("\n== landing (filled, SOL-quoted)")
for beh in ("snipe", "later"):
    rs = [r for r in F if r["beh"] == beh and r["quote"] == "SOL"]
    print(f"  {beh}: n {len(rs)} | slot delta {collections.Counter(min(r['d_slot'], 9) for r in rs).most_common(6)} | outside buy txs ahead q {q([r['ahead'] for r in rs])} | entry price / post-bundle q {q([r['entry_x'] for r in rs])}")
    a0 = [r for r in rs if r["ahead"] == 0]; print(f"     first outside buyer: {len(a0)}/{len(rs)} ({len(a0) / max(1, len(rs)):.0%})")
    am = [r["arr_ms"] for r in rs if r.get("arr_ms") is not None]
    if am: print(f"     arrival ms in our feed (R2 timelines): n {len(am)} q {q(am)}")
sn0 = [r for r in R if r["beh"] == "snipe" and r.get("arr_ms") is not None]
print(f"  all snipe attempts with a timeline: n {len(sn0)}; filled arrival q {q([r['arr_ms'] for r in sn0 if r['filled']])} | failed arrival q {q([r['arr_ms'] for r in sn0 if not r['filled']])}")
print("\n== landing spend per filled buy (SOL-quoted): priority fee + tips, % of buy")
for beh in ("snipe", "later"):
    rs = [r for r in F if r["beh"] == beh and r["quote"] == "SOL" and r.get("prio") is not None]
    for lab, sel in (("Jito tip, no priority", lambda r: r["prio"] < 1e-5 and any(s == "jito" for s, _ in r["tipsv"])), ("priority fee, no tip", lambda r: r["prio"] >= 1e-5 and not r["tipsv"]),
                     ("neither (other transfer?)", lambda r: r["prio"] < 1e-5 and not r["tipsv"]), ("router path", lambda r: r.get("router"))):
        g = [r for r in rs if sel(r)]
        if not g: continue
        pct = [(r["prio"] + sum(x for _, x in r["tipsv"])) / r["buy_sol"] * 100 for r in g]
        oth = [r["other_out"] for r in g if r.get("other_out") is not None]
        print(f"  {beh:6} {lab:28} n {len(g):4d}  spend % of buy q {q(pct)}  | unexplained outflow SOL q {q(oth)}")
    allp = [(r["prio"] + sum(x for _, x in r["tipsv"])) for r in rs]
    print(f"  {beh:6} total landing spend {sum(allp):.2f} SOL on {sum(r['buy_sol'] for r in rs):.1f} SOL bought ({sum(allp) / max(1e-9, sum(r['buy_sol'] for r in rs)) * 100:.2f}%)")
print("\n== size tiers (gross = event SOL x 1.0125, SOL-quoted filled)")
for beh in ("snipe", "later"):
    rs = [r for r in F if r["beh"] == beh and r["quote"] == "SOL"]
    print(f"  {beh}: {collections.Counter(round(r['buy_sol'] * 1.0125, 1) for r in rs).most_common(12)}")
rs = [r for r in F if r["quote"] == "SOL" and r["beh"] == "snipe"]
def grp(name, key):
    g = collections.defaultdict(list)
    for r in rs: g[key(r)].append(r["buy_sol"] * 1.0125)
    print(f"  snipe size by {name}: " + " | ".join(f"{k}: n {len(v)} med {st.median(v):.2f} mean {st.mean(v):.2f}" for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))))
grp("dev buy", lambda r: "<1" if r.get("dev_sol", 0) < 1 else "1-2" if r["dev_sol"] < 2 else "2-3" if r["dev_sol"] < 3 else "3-5" if r["dev_sol"] < 5 else "5+")
grp("bundle SOL", lambda r: "0" if r.get("bundle_sol", 0) < 0.01 else "<3" if r["bundle_sol"] < 3 else "3-6" if r["bundle_sol"] < 6 else "6+")
grp("slot delta", lambda r: r["d_slot"] if r["d_slot"] <= 1 else "2+")
grp("run", lambda r: r["run"])
rs2 = [r for r in F if r["quote"] == "SOL" and r["beh"] == "snipe"]
print("  snipe result by size (SOL-quoted filled): " + " | ".join(f"{k}: n {len(v)} SOL {sum(v):+.2f}" for k, v in sorted(collections.defaultdict(list, {k: [r['sol_result'] for r in rs2 if round(r['buy_sol'] * 1.0125, 1) == k] for k in {round(r['buy_sol'] * 1.0125, 1) for r in rs2}}).items()) if len(v) >= 8))
print("\n== exit ladder (SOL-quoted filled, first buy only)")
for beh in ("snipe", "later"):
    rs = [r for r in F if r["beh"] == beh and r["quote"] == "SOL" and r.get("sells")]
    ns = [len(r["sells"]) for r in rs]; f1 = [r["sells"][0]["frac"] for r in rs]; d1 = [r["sells"][0]["ds"] for r in rs]
    x1 = [r["sells"][0]["x"] for r in rs]; dl = [r["sells"][-1]["ds"] for r in rs]
    print(f"  {beh}: tokens {len(rs)} | sells per token q {q(ns)} | first sell: share q {q(f1)}, slots after buy q {q(d1)}, price x q {q(x1)} | last sell slots q {q(dl)}")
    later_fr = [s["frac"] for r in rs for s in r["sells"][1:-1]]; gaps = [b["ds"] - a["ds"] for r in rs for a, b in zip(r["sells"], r["sells"][1:])]
    print(f"     middle sells share q {q(later_fr)} | gap between sells (slots) q {q(gaps)}")
    print(f"     share of first sell (rounded): {collections.Counter(round(x, 2) for x in f1 if x).most_common(8)}")
    print(f"     middle share (rounded): {collections.Counter(round(x, 2) for x in later_fr if x).most_common(8)}")
    for k, sel in (("1 sell", lambda r: len(r["sells"]) == 1), ("2 sells", lambda r: len(r["sells"]) == 2), ("3-5", lambda r: 3 <= len(r["sells"]) <= 5), ("6+", lambda r: len(r["sells"]) >= 6)):
        g = [r for r in rs if sel(r)]
        if g: print(f"     {k:8} n {len(g):4d}  SOL {sum(r['sol_result'] for r in g):+7.2f}  first-sell price x med {st.median([r['sells'][0]['x'] for r in g if r['sells'][0]['x']] or [0]):.3f}  hold (slots) med {st.median([r['sells'][-1]['ds'] for r in g])}")
print("\n== later buys: price action before its buy (SOL curve, filled + failed are only known for filled)")
rs = [r for r in F if r["beh"] == "later" and r["quote"] == "SOL" and r.get("px_vs_bundle")]
print(f"  n {len(rs)} | price vs post-bundle q {q([r['px_vs_bundle'] for r in rs])} | 10 s change q {q([r['px_chg_10s'] for r in rs])} | 60 s change q {q([r['px_chg_60s'] for r in rs])}")
print(f"  peak-before / post-bundle q {q([r['peak_before_x'] for r in rs])} | net SOL flow 10 s q {q([r['flow_10s'] for r in rs])} | buys 10 s q {q([r['buys_10s'] for r in rs])} | mc SOL q {q([r['mc_sol'] for r in rs])}")
print(f"  previous trade: buy {sum(1 for r in rs if r['prev_trade'] and r['prev_trade']['buy'])}/{len(rs)}, same slot {sum(1 for r in rs if r['prev_trade'] and r['prev_trade']['ds'] == 0)}, prev size q {q([r['prev_trade']['sol'] for r in rs if r['prev_trade']])}")
print(f"  previous trader: {collections.Counter(r['prev_trade']['user'] for r in rs if r['prev_trade']).most_common(8)}")
print(f"  seconds after create q {q([r['off'] * 0.212 for r in rs])} | result SOL {sum(r['sol_result'] for r in rs):+.2f}")
for k, sel in (("10 s change < 1.0", lambda r: r["px_chg_10s"] < 1.0), ("10 s change 1.0-1.3", lambda r: 1.0 <= r["px_chg_10s"] < 1.3), ("10 s change >= 1.3", lambda r: r["px_chg_10s"] >= 1.3)):
    g = [r for r in rs if sel(r)]
    if g: print(f"     {k:22} n {len(g):4d} SOL {sum(r['sol_result'] for r in g):+.2f}")
