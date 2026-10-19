import json, statistics as st, collections
R = json.load(open("/root/comp/w4_rows.json"))
def q(v, ps=(10, 25, 50, 75, 90)):
    v = sorted(x for x in v if x is not None)
    return " ".join(f"{v[min(len(v)-1, int(len(v)*p/100))]:.3g}" for p in ps) if v else "-"
# classify each sell: frac of tokens then remaining
print("== 4yFAz exit actions ==")
acts = collections.Counter()
rows = []
for r in R:
    ctx = r.get("sell_ctx") or []
    rem = 1.0
    for i, c in enumerate(ctx):
        f = c["frac"]; fr = f / rem if rem > 1e-9 else 1
        kind = "ALL" if fr > 0.95 else ("1/3" if 0.28 <= fr <= 0.36 else ("30%" if 0.28 <= fr <= 0.32 else f"{fr:.2f}"))
        rows.append(dict(i=i, dslot=c["dslot"], px=c["px_vs_entry"], pk=c["peak_vs_entry"], dd=c["dd_from_peak"], frac_rem=fr, kind="ALL" if fr > 0.95 else ("PART" if fr < 0.95 else "?"),
                         big1=c["w1"]["big_sell"], bs3=c["w3"]["bundle_sell"], nb1=c["w1"]["nb"], ns1=c["w1"]["ns"], first=(i == 0)))
        rem -= f
print("sell rows", len(rows))
F = [x for x in rows if x["first"]]
print("\nfirst sell by timing bucket (slots after buy):")
for lo, hi in [(0, 1), (1, 3), (3, 8), (8, 12), (12, 30), (30, 999)]:
    g = [x for x in F if lo <= x["dslot"] < hi]
    if g: print(f"  dslot {lo}-{hi}: n {len(g)} ALL {sum(1 for x in g if x['kind']=='ALL')/len(g):.2f} | px/entry q {q([x['px'] for x in g])} | frac_rem med {st.median(x['frac_rem'] for x in g):.2f}")
print("\nfirst sell at dslot 8-12 (the ~4 s decision): ALL vs PART by px/entry:")
g = [x for x in F if 8 <= x["dslot"] < 12]
for lo, hi in [(0, 0.95), (0.95, 1.0), (1.0, 1.05), (1.05, 1.1), (1.1, 1.2), (1.2, 9)]:
    h = [x for x in g if lo <= x["px"] < hi]
    if h: print(f"  px {lo}-{hi}: n {len(h)} ALL {sum(1 for x in h if x['kind']=='ALL')/len(h):.2f}")
print("\nvery early sells (dslot 0-2): px/entry q", q([x["px"] for x in F if x["dslot"] <= 2]), " frac_rem q", q([x["frac_rem"] for x in F if x["dslot"] <= 2]))
print("early sells (dslot 0-2) peak/entry q", q([x["pk"] for x in F if x["dslot"] <= 2]))
L = [x for x in rows if not x["first"]]
print("\nlater sells: ALL share %.2f; px/entry q %s; dd q %s" % (sum(1 for x in L if x["kind"] == "ALL") / max(1, len(L)), q([x["px"] for x in L]), q([x["dd"] for x in L])))
print("later sells ALL: px q", q([x["px"] for x in L if x["kind"] == "ALL"]), " dslot q", q([x["dslot"] for x in L if x["kind"] == "ALL"]))
print("later sells PART: px q", q([x["px"] for x in L if x["kind"] != "ALL"]), " dslot q", q([x["dslot"] for x in L if x["kind"] != "ALL"]))
# trigger rates in the prior 1 s at first sell vs at all sells
print("\nreactive? share of first sells with another wallet's sell >=0.5 SOL in prior 1 s: %.2f ; bundle sell in prior 3 s: %.2f" %
      (sum(1 for x in F if x["big1"] >= 0.5) / len(F), sum(1 for x in F if x["bs3"] > 0) / len(F)))
# hold time distribution in seconds
hold = [r["sell_dslots"][-1] * 0.4 for r in R if r["sell_dslots"]]
print("\nhold to last sell (s) q", q(hold), " first sell (s) q", q([r["sell_dslots"][0] * 0.4 for r in R if r["sell_dslots"]]))
print("pnl%% by nsell==1: mean %.2f med %.2f n %d ; nsell>1: mean %.2f med %.2f n %d" % (
    100 * st.mean(r["pnl_pct"] for r in R if r["nsell"] == 1), 100 * st.median(r["pnl_pct"] for r in R if r["nsell"] == 1), sum(1 for r in R if r["nsell"] == 1),
    100 * st.mean(r["pnl_pct"] for r in R if r["nsell"] > 1), 100 * st.median(r["pnl_pct"] for r in R if r["nsell"] > 1), sum(1 for r in R if r["nsell"] > 1)))
# fee vs size table
print("\n== 4yFAz fee vs size ==")
for lo, hi in [(0, 1), (1, 2), (2, 2.5), (2.5, 3.5), (3.5, 99)]:
    g = [r for r in R if lo <= r["sol"] < hi]
    print(f"size {lo}-{hi}: n {len(g)} land med {st.median(r['land'] for r in g):.4f} mean {st.mean(r['land'] for r in g):.4f} P(prio>0.01) {sum(1 for r in g if r['prio']>0.01)/len(g):.2f} land% med {100*st.median(r['land_pct'] for r in g):.2f}")
c = st.correlation([r["sol"] for r in R], [r["land"] for r in R]); print("corr(size, land) %.3f R2 %.3f" % (c, c * c))
for k in ("dev", "gsol"):
    g = [r for r in R if k in r]
    c = st.correlation([r[k] for r in g], [r["land"] for r in g]); print(f"corr({k}, land) {c:.3f}")
g = [r for r in R if "dev" in r]
print("land by dev bin:", {f"{lo}-{hi}": round(st.median([r['land'] for r in g if lo <= r['dev'] < hi] or [0]), 4) for lo, hi in [(0, .5), (.5, 1), (1, 2), (2, 4), (4, 99)]})
print("land by outcome (pnl>0 vs <=0): %.4f vs %.4f" % (st.median(r["land"] for r in R if r["pnl"] > 0), st.median(r["land"] for r in R if r["pnl"] <= 0)))
print("land by leader client:", {k: (len(v), round(st.median(v), 4)) for k, v in collections.defaultdict(list, {}).items()})
lc = collections.defaultdict(list)
for r in R:
    if "lc" in r: lc[r["lc"]].append(r["land"])
print("  ", {k: (len(v), round(st.median(v), 4)) for k, v in lc.items()})
# fee path: priority-only vs tip-only vs both
def path(r):
    if r["prio"] > 0.001 and r["tip"] > 0: return "prio+tip"
    if r["prio"] > 0.001: return "prio"
    if r["tip"] > 0: return "tip:" + ",".join(sorted({x[0] for x in r["tips"]}))
    return "none?"
pc = collections.Counter(path(r) for r in R); print("fee path:", pc.most_common(10))
for p_, _ in pc.most_common(6):
    g = [r for r in R if path(r) == p_ and "dslot" in r]
    if g: print(f"  {p_}: n {len(g)} inS {sum(1 for r in g if r['dslot']==0)/len(g):.2f} pos med {st.median([r['pos'] for r in g if r.get('pos') is not None] or [-1])} land med {st.median(r['land'] for r in g):.4f} size med {st.median(r['sol'] for r in g):.2f}")
