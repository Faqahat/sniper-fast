import json, statistics as st, collections, math
R = json.load(open("/root/comp/w4_rows.json"))
def q(v, ps=(10, 25, 50, 75, 90)):
    v = sorted(x for x in v if x is not None)
    if not v: return "-"
    return " ".join(f"{v[min(len(v)-1, int(len(v)*p/100))]:.3g}" for p in ps)
def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else float("nan")
print("== 4yFAz: n first buys", len(R), "tiers", collections.Counter(r["tier"] for r in R).most_common())
print("\n-- size tier vs entry state (medians) --")
print(f"{'tier':>6} {'n':>4} {'vsol_pre':>8} {'mcSOL':>6} {'mcUSD':>6} {'pxVsPB':>6} {'dev':>5} {'gsol':>5} {'glued':>5} {'pos':>5} {'dslot':>5} {'outN':>4} {'outSOL':>6} {'impact':>6} {'%vsol':>6} {'pnl%':>6} {'win':>4} {'meanPnL':>7}")
for T in [0.49, 0.721, 1.171, 1.432, 2.153, 2.926, None]:
    g = [r for r in R if r["tier"] == T]
    if not g: continue
    gt = [r for r in g if "dev" in r]
    print(f"{str(T):>6} {len(g):4d} {med([r['vsol_pre'] for r in g]):8.2f} {med([r['mc_pre'] for r in g]):6.1f} {med([r['mc_usd'] for r in g]):6.0f} {med([r.get('px_vs_pb') for r in gt]):6.2f} "
          f"{med([r.get('dev') for r in gt]):5.2f} {med([r.get('gsol') for r in gt]):5.2f} {med([r.get('glued') for r in gt]):5.1f} {med([r.get('pos') for r in gt]):5.0f} {med([r.get('dslot') for r in gt]):5.1f} "
          f"{med([r.get('n_out_ahead') for r in gt]):4.0f} {med([r.get('sol_out_ahead') for r in gt]):6.2f} {med([r['impact'] for r in g]):6.3f} {med([r['size_pct_vsol'] for r in g]):6.3f} "
          f"{100*med([r['pnl_pct'] for r in g]):6.1f} {sum(1 for r in g if r['pnl']>0)/len(g):4.2f} {st.mean([r['pnl'] for r in g]):7.3f}")
# regressions: log size vs log vsol_pre, log mc ; R^2
def r2(x, y):
    if len(x) < 5: return float("nan")
    c = st.correlation(x, y); return c * c
G = [r for r in R if r["sol"] > 0.05]
ly = [math.log(r["sol"]) for r in G]
print("\nR^2 log(size) ~ log(vsol_pre): %.3f ; ~ log(mcSOL): %.3f ; ~ impact: n/a (size defines impact)" % (r2([math.log(r["vsol_pre"]) for r in G], ly), r2([math.log(r["mc_pre"]) for r in G], ly)))
Gt = [r for r in G if "dev" in r]
lyt = [math.log(r["sol"]) for r in Gt]
for k in ("dev", "gsol", "glued", "dslot", "n_out_ahead", "sol_out_ahead", "px_vs_pb"):
    xs = [float(r.get(k) or 0) for r in Gt]
    print(f"  R^2 log(size) ~ {k}: {r2(xs, lyt):.3f}  (n={len(Gt)})")
# dev bins
print("\n-- size by dev buy bin (tape subset) --")
for lo, hi in [(0, 0.3), (0.3, 1), (1, 2), (2, 4), (4, 100)]:
    g = [r for r in Gt if lo <= r["dev"] < hi]
    if g: print(f"  dev {lo}-{hi}: n {len(g)} median size {med([r['sol'] for r in g]):.2f} tiers {collections.Counter(r['tier'] for r in g).most_common(4)}")
print("\n-- size by bundle (gsol) bin --")
for lo, hi in [(0, 0.01), (0.01, 2), (2, 5), (5, 1000)]:
    g = [r for r in Gt if lo <= r["gsol"] < hi]
    if g: print(f"  gsol {lo}-{hi}: n {len(g)} median size {med([r['sol'] for r in g]):.2f} mean pnl% {100*st.mean([r['pnl_pct'] for r in g]):.1f}")
print("\n-- size by hour (UTC) --")
import time
hh = collections.defaultdict(list)
for r in R: hh[time.strftime("%m-%d %H", time.gmtime(r["bt"]))].append(r["sol"])
print("  ", " | ".join(f"{k[-5:]}:{len(v)}/{st.median(v):.2f}" for k, v in sorted(hh.items())))
# FEES
print("\n== 4yFAz fees ==")
print("cu price (µlam) q:", q([r["cu"] or 0 for r in R]))
print("cu limit q:", q([r["cul"] or 0 for r in R]))
print("priority SOL q:", q([r["prio"] for r in R]))
print("tips SOL q:", q([r["tip"] for r in R]), " tip providers:", collections.Counter(x[0] for r in R for x in r["tips"]).most_common(6))
print("land total SOL q:", q([r["land"] for r in R]), " land % of size q:", q([100 * r["land_pct"] for r in R]))
print("top-level transfers in buy tx (dst8):", collections.Counter(x[0] for r in R for x in r["xf"]).most_common(6))
print("prio by tier:", {T: round(med([r["prio"] for r in R if r["tier"] == T]), 4) for T in [0.49, 0.721, 1.171, 1.432, 2.153, 2.926]})
print("prio/size by tier:", {T: round(med([r["land_pct"] for r in R if r["tier"] == T]), 4) for T in [0.49, 0.721, 1.171, 1.432, 2.153, 2.926]})
pc = collections.Counter(round(r["prio"], 3) for r in R); print("most common priority SOL:", pc.most_common(8))
print("cul common:", collections.Counter(r["cul"] for r in R).most_common(5))
# fee vs position
Gp = [r for r in R if r.get("pos") is not None]
print("\nposition in create slot (n=%d) q:" % len(Gp), q([r["pos"] for r in Gp]), " in S:", len(Gp), "of", len([r for r in R if "dslot" in r]), " dslot q:", q([r.get("dslot") for r in R if "dslot" in r]))
for lo, hi in [(0, 0.02), (0.02, 0.04), (0.04, 0.06), (0.06, 1)]:
    g = [r for r in R if lo <= r["prio"] + r["tip"] < hi and "dslot" in r]
    if g: print(f"  land {lo}-{hi}: n {len(g)} inS {sum(1 for r in g if r['dslot']==0)/len(g):.2f} med pos {med([r.get('pos') for r in g])} ")
print("leader clients at his buy:", collections.Counter(r.get("lc") for r in R if "lc" in r).most_common(6))
# EXITS
print("\n== 4yFAz exits ==")
print("n sells per mint:", collections.Counter(min(r["nsell"], 10) for r in R).most_common())
print("first sell frac of tokens q:", q([r["sell_tok_frac"][0] for r in R if r["sell_tok_frac"]]))
fr = collections.Counter(round(f, 2) for r in R for f in r["sell_tok_frac"][:3]); print("common sell fracs (first 3):", fr.most_common(8))
print("first sell after buy (slots) q:", q([r["sell_dslots"][0] for r in R if r["sell_dslots"]]))
print("last sell after buy (slots) q:", q([r["sell_dslots"][-1] for r in R if r["sell_dslots"]]))
gaps = [b - a for r in R for a, b in zip(r["sell_dslots"], r["sell_dslots"][1:])]
print("gap between sells (slots) q:", q(gaps))
print("sold fraction q:", q([r["sold_frac"] for r in R]))
print("pnl % q:", q([100 * r["pnl_pct"] for r in R]), " mean %.2f%%  win %.2f  total %.2f SOL" % (100 * st.mean([r["pnl_pct"] for r in R]), sum(1 for r in R if r["pnl"] > 0) / len(R), sum(r["pnl"] for r in R)))
print("sell landing SOL q:", q([x for r in R for x in r["sell_land"]]), " sell cu q:", q([x or 0 for r in R for x in r["sell_cu"]]))
C = [c for r in R for c in r.get("sell_ctx", [])]
C1 = [r["sell_ctx"][0] for r in R if r.get("sell_ctx")]
print("\nfirst-sell context (n=%d):" % len(C1))
print("  px vs entry q:", q([c["px_vs_entry"] for c in C1]))
print("  peak vs entry q:", q([c["peak_vs_entry"] for c in C1]))
print("  drawdown from peak q:", q([c["dd_from_peak"] for c in C1]))
print("  big other sell in prior 1s q:", q([c["w1"]["big_sell"] for c in C1]), " any sell prior 1s: %.2f" % (sum(1 for c in C1 if c["w1"]["ns"] > 0) / len(C1)))
print("  bundle sell prior 3s >0: %.2f" % (sum(1 for c in C1 if c["w3"]["bundle_sell"] > 0) / len(C1)))
print("  buys prior 1s q:", q([c["w1"]["nb"] for c in C1]), " buy SOL prior 3s q:", q([c["w3"]["bsol"] for c in C1]))
print("  first sell when px<entry: %.2f ; when px>=1.1x: %.2f" % (sum(1 for c in C1 if c["px_vs_entry"] < 1) / len(C1), sum(1 for c in C1 if c["px_vs_entry"] >= 1.1) / len(C1)))
print("all sells: px vs entry q:", q([c["px_vs_entry"] for c in C]), " dd q:", q([c["dd_from_peak"] for c in C]))
# hazard: did first sell come right after a price drop? compare dd at sell vs typical
print("first sell dslot vs pnl bucket:")
for lo, hi in [(-9, 0), (0, 0.1), (0.1, 0.3), (0.3, 9)]:
    g = [r for r in R if lo <= r["pnl_pct"] < hi and r["sell_dslots"]]
    if g: print(f"  pnl {lo}-{hi}: n {len(g)} first sell slot med {med([r['sell_dslots'][0] for r in g])} nsell med {med([r['nsell'] for r in g])}")
