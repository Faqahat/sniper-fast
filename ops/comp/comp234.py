# READ-ONLY offline. Tasks 2-4 for the top competitor wallets on rule-#2 launches: buy-size model, fees, exits.
import sys, json, collections, statistics as st, math, random
sys.path.insert(0, "/root/comp")
from lib import *
SET = sys.argv[1] if len(sys.argv) > 1 else "r2"
NMIN = int(sys.argv[2]) if len(sys.argv) > 2 else 8
SOLPX = json.load(open("/root/solprice.json")).get("price", 104)
WAL = json.load(open(f"/root/comp/wallets_{SET}.json"))
NAMED = ["9XPMCaxt", "7Wt42kky", "C2i1eVJw", "CWiNFAEk", "Six5j1cv", "NULLioEU", "straywAW", "dKMjeGJ4", "BXB7FF4m", "Anubis51", "G9sQPg9E"]
prof = sorted([w for w in WAL if w["n"] >= NMIN and w["pnl"] > 0], key=lambda w: -w["pnl"])
top = [w["w"] for w in prof[:10]]
named = [w["w"] for w in WAL if any(w["w"].startswith(p) for p in NAMED) and w["w"] not in top]
TOPS = top + named
lab = {w: w[:8] for w in TOPS}
print("TOP (n>=%d, pnl>0, by total net PnL):" % NMIN, [w[:8] for w in top])
print("named extra:", [w[:8] for w in named])

def q(v, ps=(10, 25, 50, 75, 90)):
    v = sorted(x for x in v if x is not None)
    return " ".join(f"{v[min(len(v)-1, int(len(v)*p/100))]:.3g}" for p in ps) if v else "-"
def r2(x, y):
    if len(x) < 5 or len(set(x)) < 2 or len(set(y)) < 2: return float("nan")
    c = st.correlation(x, y); return c * c
def ols(X, y):
    # tiny OLS with intercept, returns (coef, R2)
    n = len(y); k = len(X[0]) + 1
    A = [[1.0] + list(r) for r in X]
    AtA = [[sum(A[i][a] * A[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Aty = [sum(A[i][a] * y[i] for i in range(n)) for a in range(k)]
    # gaussian elimination
    M = [row[:] + [Aty[i]] for i, row in enumerate(AtA)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12: return None, float("nan")
        M[c], M[p] = M[p], M[c]
        for r in range(k):
            if r != c:
                fct = M[r][c] / M[c][c]
                M[r] = [M[r][j] - fct * M[c][j] for j in range(k + 1)]
    b = [M[i][k] / M[i][i] for i in range(k)]
    yh = [sum(b[j] * A[i][j] for j in range(k)) for i in range(n)]
    my = sum(y) / n
    ss = sum((y[i] - my) ** 2 for i in range(n)); se = sum((y[i] - yh[i]) ** 2 for i in range(n))
    return b, 1 - se / ss if ss > 0 else float("nan")

# ---------- collect per-launch rows for TOPS from tapes (buys, sells, context) ----------
TS = set(TOPS)
rows = collections.defaultdict(list)     # wallet -> per-launch dict
allS = []                                # all outside buys in create slot: (d, cup, prio, tip, land, client, size) for position-vs-fee
for r in load(f"/root/comp/tapes_{SET}.jsonl"):
    ev, fb = order_launch(r)
    if not ev: continue
    S = r["slot"]; bw = bundle_set(r)
    gv, gt = post_bundle_state(r); pb = gv / gt
    seenS = set()
    for e in ev:
        if e["slot"] == S and e["buy"] and e["user"] not in bw and e["d"] is not None and e["sig"] not in seenS:
            seenS.add(e["sig"])
            prio = (e["cup"] or 0) * (e["cul"] or 0) / 1e6 / 1e9
            tip = sum(x[1] for x in e["tips"]) / 1e9
            allS.append(dict(d=e["d"], cup=e["cup"] or 0, prio=prio, tip=tip, land=(e["txfee"] or 0) / 1e9 + tip, lc=leader_client(r, S),
                             size=e["sol"] / 1e9, prov=",".join(sorted({x[0] for x in e["tips"]})) or ("prio" if prio > 0.001 else "none"), w=e["user"], mint=r["mint"]))
    for w in TS:
        idx = [k for k, e in enumerate(ev) if e["user"] == w]
        if not idx: continue
        b0 = next((k for k in idx if ev[k]["buy"]), None)
        if b0 is None or ev[b0]["slot"] - S > 150 or w in bw: continue
        e0 = ev[b0]; pre = pre_state(e0)
        out_ahead = [e for e in ev[:b0] if e["buy"] and e["user"] not in bw]
        prio = (e0["cup"] or 0) * (e0["cul"] or 0) / 1e6 / 1e9
        tip = sum(x[1] for x in e0["tips"]) / 1e9
        entry_px = e0["vsol"] / e0["vtok"]   # spot after his buy
        fill_px = e0["sol"] / e0["tok"]
        tb = sum(ev[k]["tok"] for k in idx if ev[k]["buy"]); cost = sum(ev[k]["sol"] + ev[k]["fee"] + ev[k]["cfee"] for k in idx if ev[k]["buy"])
        sells = []
        for k in idx:
            e = ev[k]
            if e["buy"] or k < b0: continue
            prior = ev[b0 + 1:k]
            pk = max([x["vsol"] / x["vtok"] for x in prior] + [entry_px])
            cur = (prior[-1]["vsol"] / prior[-1]["vtok"]) if prior else entry_px
            def win(sl):
                ws = [x for x in prior if x["slot"] >= e["slot"] - sl and x["user"] != w]
                return dict(nb=sum(1 for x in ws if x["buy"]), ns=sum(1 for x in ws if not x["buy"]), bsol=sum(x["sol"] for x in ws if x["buy"]) / 1e9,
                            ssol=sum(x["sol"] for x in ws if not x["buy"]) / 1e9, big=max([x["sol"] / 1e9 for x in ws if not x["buy"]] or [0]),
                            bund=sum(x["sol"] for x in ws if not x["buy"] and x["_b"]) / 1e9)
            for x in prior: x["_b"] = x["user"] in bw
            sells.append(dict(dslot=e["slot"] - e0["slot"], frac=e["tok"] / max(1, tb), px_vs_entry=cur / fill_px, peak_vs_entry=pk / fill_px, dd=cur / pk - 1,
                              w1=win(2), w3=win(7), w10=win(25), sol=e["sol"] / 1e9, cup=e["cup"], land=landing_cost(e) / 1e9))
        proc = sum(ev[k]["sol"] - ev[k]["fee"] - ev[k]["cfee"] for k in idx if not ev[k]["buy"])
        ts = sum(ev[k]["tok"] for k in idx if not ev[k]["buy"])
        last_px = ev[-1]["vsol"] / ev[-1]["vtok"]
        pnl = (proc + max(0, tb - ts) * last_px * (1 - 0.0125) - cost) / 1e9
        landall = sum(landing_cost(ev[k]) for k in set(idx)) / 1e9
        rows[w].append(dict(mint=r["mint"], bt=r["bt"], S=S, sol=e0["sol"] / 1e9, tok=e0["tok"], vsol_pre=pre[0] / 1e9, real_pre=pre[0] / 1e9 - 30,
                            mc_sol=pre[0] / pre[1] * 1e6, px_vs_pb=(pre[0] / pre[1]) / pb, impact=entry_px / (pre[0] / pre[1]) - 1, dev=r["dev"] / 1e9, gsol=r["gsol"] / 1e9,
                            glued=r["glued"], d=e0["d"], dslot=e0["slot"] - S, n_out=len({x["user"] for x in out_ahead}), sol_out=sum(x["sol"] for x in out_ahead) / 1e9,
                            cup=e0["cup"] or 0, cul=e0["cul"] or 0, prio=prio, tip=tip, txfee=(e0["txfee"] or 0) / 1e9, land=(e0["txfee"] or 0) / 1e9 + tip,
                            prov=",".join(sorted({x[0] for x in e0["tips"]})) or ("prio" if prio > 0.001 else "none"),
                            xf=[(x[0][:8], x[1]) for x in e0["xf"] if x[2] == 1 and x[1] < e0["sol"] // 2][:3], lc=leader_client(r, e0["slot"]), sig=e0["sig"],
                            nbuys=sum(1 for k in idx if ev[k]["buy"]), sells=sells, pnl=pnl, pnl_pct=pnl / (cost / 1e9), landall=landall,
                            sold=ts / max(1, tb), payer=e0["payer"], nsig=len(e0["signers"])))
json.dump({"rows": rows, "allS": allS, "tops": TOPS}, open(f"/root/comp/top_{SET}.json", "w"))

# ---------- TASK 2: size model ----------
print("\n================ TASK 2: BUY SIZE per top wallet ================")
for w in TOPS:
    R = rows.get(w, [])
    if len(R) < 3: continue
    sz = [x["sol"] for x in R]
    mode = collections.Counter(round(s, 2) for s in sz).most_common(3)
    cv = st.pstdev(sz) / st.mean(sz)
    ly = [math.log(max(s, 1e-4)) for s in sz]
    lv = [math.log(x["vsol_pre"]) for x in R]
    b, R2v = ols([[a] for a in lv], ly)
    feats = ["vsol_pre", "gsol", "dev", "dslot", "n_out", "sol_out", "px_vs_pb"]
    b2, R2m = ols([[math.log(x["vsol_pre"]), x["gsol"], x["dev"], x["dslot"], x["n_out"], x["sol_out"], x["px_vs_pb"]] for x in R], ly) if len(R) >= 15 else (None, float("nan"))
    tokcv = st.pstdev([x["tok"] for x in R]) / st.mean([x["tok"] for x in R])
    pct = [x["sol"] / x["vsol_pre"] for x in R]
    imp = [x["impact"] for x in R]
    print(f"\n{w[:8]} n={len(R)}  size q {q(sz)}  CV {cv:.2f}  modes {mode}  tokCV {tokcv:.2f}")
    print(f"   size/vsol q {q(pct)} CV {st.pstdev(pct)/st.mean(pct):.2f} | own impact q {q(imp)} | log-size~log-vsol slope {b[1] if b else float('nan'):.2f} R2 {R2v:.2f} | multi R2 {R2m:.2f}")
    print(f"   entry mcSOL q {q([x['mc_sol'] for x in R])} (USD med {st.median(x['mc_sol'] for x in R)*SOLPX:.0f}) | px_vs_pb q {q([x['px_vs_pb'] for x in R])} | max px_vs_pb {max(x['px_vs_pb'] for x in R):.2f}")
    print(f"   pos d q {q([x['d'] for x in R if x['dslot']==0])}  inS {sum(1 for x in R if x['dslot']==0)/len(R):.2f}  dslot q {q([x['dslot'] for x in R])} | out ahead n q {q([x['n_out'] for x in R])} sol q {q([x['sol_out'] for x in R])}")
    for k in ("gsol", "dev", "dslot", "n_out", "sol_out", "px_vs_pb"):
        pass
    print("   R2 log(size) vs: " + " ".join(f"{k}={r2([float(x[k]) for x in R], ly):.2f}" for k in ("vsol_pre", "mc_sol", "gsol", "dev", "dslot", "n_out", "sol_out", "px_vs_pb", "d")
                                               if all(x[k] is not None for x in R)))
    # tier view: size by gsol / dev bins
    for k, bins in (("dev", [(0, 1), (1, 2), (2, 4), (4, 99)]), ("sol_out", [(0, 0.01), (0.01, 2), (2, 5), (5, 999)])):
        s = []
        for lo, hi in bins:
            g = [x["sol"] for x in R if lo <= x[k] < hi]
            if g: s.append(f"{lo}-{hi}:{len(g)}/{st.median(g):.2f}")
        print(f"   size by {k}: " + "  ".join(s))

# ---------- TASK 3: fees ----------
print("\n================ TASK 3: FEES per top wallet ================")
print(f"{'wallet':9} {'n':>3} {'cuPrice med':>11} {'cuLim med':>9} {'prio med':>8} {'tip med':>8} {'land med':>8} {'land/size':>9} {'providers':40} corr(land,size) corr(land,gsol) corr(land,outcome)")
for w in TOPS:
    R = rows.get(w, [])
    if len(R) < 3: continue
    pv = collections.Counter(x["prov"] for x in R).most_common(3)
    def c(a, b):
        try: return f"{st.correlation(a, b):.2f}"
        except Exception: return "nan"
    print(f"{w[:8]:9} {len(R):3d} {st.median(x['cup'] for x in R):11.0f} {st.median(x['cul'] for x in R):9.0f} {st.median(x['prio'] for x in R):8.4f} {st.median(x['tip'] for x in R):8.4f} "
          f"{st.median(x['land'] for x in R):8.4f} {100*st.median(x['land']/x['sol'] for x in R if x['sol']>0):8.2f}% {str(pv)[:40]:40} {c([x['land'] for x in R],[x['sol'] for x in R]):>6} "
          f"{c([x['land'] for x in R],[x['gsol'] for x in R]):>6} {c([x['land'] for x in R],[x['pnl_pct'] for x in R]):>6}")
# fee drivers pooled across top wallets (within-wallet demeaned log land)
print("\nFee drivers (pooled top wallets, within-wallet demeaned log(land)) R2 by single feature:")
P = []
for w in TOPS:
    R = [x for x in rows.get(w, []) if x["land"] > 0]
    if len(R) < 5: continue
    m = st.mean(math.log(x["land"]) for x in R)
    for x in R:
        P.append(dict(y=math.log(x["land"]) - m, lsize=math.log(max(x["sol"], 1e-4)) - st.mean(math.log(max(z["sol"], 1e-4)) for z in R), **{k: x[k] for k in ("gsol", "dev", "vsol_pre", "dslot", "n_out", "sol_out", "px_vs_pb", "pnl_pct")}, lc=x["lc"], d=x["d"]))
if P:
    y = [p["y"] for p in P]
    print("   " + " ".join(f"{k}={r2([float(p[k]) for p in P], y):.3f}" for k in ("lsize", "gsol", "dev", "vsol_pre", "dslot", "n_out", "sol_out", "px_vs_pb", "pnl_pct")))
    lcg = collections.defaultdict(list)
    for p in P: lcg[p["lc"]].append(p["y"])
    print("   demeaned log land by leader client:", {k: (len(v), round(st.mean(v), 2)) for k, v in lcg.items() if len(v) >= 5})

# position vs fee (all outside buys in S)
print("\nPOSITION vs FEE: all outside buys in the create slot (n=%d)" % len(allS))
A = [a for a in allS if a["d"] is not None]
for lo, hi in [(0, 0.001), (0.001, 0.003), (0.003, 0.006), (0.006, 0.01), (0.01, 0.02), (0.02, 0.04), (0.04, 0.08), (0.08, 9)]:
    g = [a for a in A if lo <= a["land"] < hi]
    if g: print(f"   land {lo}-{hi} SOL: n {len(g):4d} d q {q([a['d'] for a in g])}  P(d<=25) {sum(1 for a in g if a['d']<=25)/len(g):.2f}  P(d<=8) {sum(1 for a in g if a['d']<=8)/len(g):.2f}")
print("   by provider:")
pg = collections.defaultdict(list)
for a in A: pg[a["prov"]].append(a)
for k, g in sorted(pg.items(), key=lambda kv: -len(kv[1]))[:12]:
    print(f"     {k[:28]:28} n {len(g):4d} land med {st.median(a['land'] for a in g):.4f}  d q {q([a['d'] for a in g])}  P(d<=25) {sum(1 for a in g if a['d']<=25)/len(g):.2f}")
print("   by leader client x land bucket, P(d<=25):")
for lc in sorted({a["lc"] for a in A}):
    g = [a for a in A if a["lc"] == lc]
    if len(g) < 30: continue
    s = []
    for lo, hi in [(0, 0.003), (0.003, 0.01), (0.01, 0.03), (0.03, 9)]:
        h = [a for a in g if lo <= a["land"] < hi]
        if len(h) >= 5: s.append(f"{lo}-{hi}:{len(h)}/{sum(1 for a in h if a['d']<=25)/len(h):.2f}")
    print(f"     {lc:14} n {len(g):4d}  " + "  ".join(s))
# regression d ~ log cu price + log tip (+ client dummies)
X = [[math.log10(1 + a["cup"]), math.log10(1e-6 + a["tip"])] for a in A]
b, R2 = ols(X, [math.log(1 + a["d"]) for a in A]) if len(A) > 20 else (None, float("nan"))
print(f"   OLS log(1+d) ~ log10(cuprice) + log10(tip): coef {[round(c, 3) for c in b] if b else b}  R2 {R2:.3f}")
for lc in sorted({a["lc"] for a in A}):
    g = [a for a in A if a["lc"] == lc]
    if len(g) < 40: continue
    b, R2 = ols([[math.log10(1 + a["cup"]), math.log10(1e-6 + a["tip"])] for a in g], [math.log(1 + a["d"]) for a in g])
    print(f"     {lc:14} n {len(g):4d} coef {[round(c, 3) for c in b] if b else b} R2 {R2:.3f}")

# ---------- TASK 4: exits ----------
print("\n================ TASK 4: EXITS per top wallet ================")
for w in TOPS:
    R = rows.get(w, [])
    if len(R) < 3: continue
    S1 = [x["sells"][0] for x in R if x["sells"]]
    nsell = collections.Counter(min(len(x["sells"]), 5) for x in R)
    if not S1:
        print(f"\n{w[:8]} n={len(R)} no sells in window"); continue
    allsells = [s for x in R for s in x["sells"]]
    print(f"\n{w[:8]} n={len(R)} sells/launch {dict(sorted(nsell.items()))}  sold-in-window {sum(1 for x in R if x['sold']>0.99)/len(R):.2f}  pnl% q {q([100*x['pnl_pct'] for x in R])} mean {100*st.mean(x['pnl_pct'] for x in R):.1f}% win {sum(1 for x in R if x['pnl']>0)/len(R):.2f}")
    print(f"   hold to 1st sell (s) q {q([s['dslot']*0.4 for s in S1])} | to last sell (s) q {q([x['sells'][-1]['dslot']*0.4 for x in R if x['sells']])} | 1st sell frac q {q([s['frac'] for s in S1])}")
    print(f"   at 1st sell: px/entry q {q([s['px_vs_entry'] for s in S1])} | peak/entry q {q([s['peak_vs_entry'] for s in S1])} | dd from peak q {q([s['dd'] for s in S1])}")
    print(f"   prior 1s: other big sell q {q([s['w1']['big'] for s in S1])} P(any sell) {sum(1 for s in S1 if s['w1']['ns']>0)/len(S1):.2f} P(bundle sell) {sum(1 for s in S1 if s['w1']['bund']>0)/len(S1):.2f} "
          f"| prior 3s P(bundle sell) {sum(1 for s in S1 if s['w3']['bund']>0)/len(S1):.2f} | prior 3s buySOL q {q([s['w3']['bsol'] for s in S1])} sellSOL q {q([s['w3']['ssol'] for s in S1])}")
    print(f"   sell landing SOL q {q([s['land'] for s in allsells])}")
