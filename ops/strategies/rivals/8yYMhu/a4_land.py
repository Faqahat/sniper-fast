#!/usr/bin/env python3
"""8yYMhu a4 (read-only): landing anatomy. Orders = attempts grouped by (mint, trigger slot, trigger idx). MEASURED from att.pkl.
Out: DATA/a4.txt"""
import sys, os, pickle, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
A = pickle.load(open(f"{X.D}/att.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
def day1(a): return X.W0 <= a["bt"] < X.W1
for lab, AA in (("ALL 10-25..10-29", A), ("24h D1", [a for a in A if day1(a)])):
    P(f"\n######## {lab}: attempts {len(AA)}")
    c = collections.Counter(a["out"] for a in AA); n = len(AA)
    P("on-chain attempts by outcome: " + ", ".join(f"{k} {v} ({100*v/n:.1f}%)" for k, v in c.most_common()))
    O = collections.defaultdict(list)
    for a in AA:
        if "trig_slot" in a: O[(a["mint"], a["trig_slot"], a["trig_idx"])].append(a)
    no = len(O); land = sum(any(x["out"] == "landed" for x in v) for v in O.values())
    multi = collections.Counter(len(v) for v in O.values())
    P(f"orders (mint, trigger) {no}: filled {land} ({100*land/no:.1f}%); on-chain copies per order {dict(sorted(multi.items())[:6])}")
    pat = collections.Counter("+".join(sorted(x["out"] for x in v)) for v in O.values())
    P("order outcome patterns: " + ", ".join(f"{k} {v}" for k, v in pat.most_common(12)))
    lo = [v for v in O.values() if any(x["out"] == "landed" for x in v)]
    P(f"  failed copies riding on FILLED orders: {sum(len(v)-1 for v in lo)} ({collections.Counter(x['out'] for v in lo for x in v if x['out']!='landed')})")
    uo = [v for v in O.values() if not any(x["out"] == "landed" for x in v)]
    P(f"  unfilled orders {len(uo)}: first outcome {collections.Counter(min(v, key=lambda x: (x['s'], x['i']))['out'] for v in uo)}")
    # landed: index gap, ms
    LD = [a for a in AA if a["out"] == "landed" and "trig_slot" in a]
    g = np.array([a["trig_gap"] for a in LD])
    P(f"landed with trigger {len(LD)}: same slot {100*np.mean(g==0):.1f}%, +1 {100*np.mean(g==1):.1f}%, >=2 {100*np.mean(g>=2):.1f}%")
    S0 = [a for a in LD if a["trig_gap"] == 0]
    ig = np.array([a["igap"] for a in S0]); ms = np.array([a["ms"] for a in S0]); nb = np.array([a["n_between"] for a in S0]); bb = np.array([a["buys_between"] for a in S0])
    P(f"  index gap trigger->his buy p10/25/50/75/90 = " + "/".join(f"{X.pct(ig,q):.0f}" for q in (10, 25, 50, 75, 90)) +
      f"; chain-clock ms p10/25/50/75/90 = " + "/".join(f"{X.pct(ms,q):.0f}" for q in (10, 25, 50, 75, 90)))
    for N in (1, 3, 5, 10, 25, 50, 100):
        P(f"    within {N:3} txs of the trigger: {100*np.mean(ig<=N):5.1f}%")
    P(f"  pump trades between trigger and him p50 {X.med(nb):.0f}, outside BUYS between p50 {X.med(bb):.0f}; he is the FIRST buyer after the trigger in {100*np.mean(bb==0):.1f}%")
    tf = np.array([a["trig_frac"] for a in S0]); hf = np.array([a["frac"] for a in S0])
    P(f"  trigger position in its block (frac) p10/25/50/75/90 = " + "/".join(f"{X.pct(tf,q):.2f}" for q in (10, 25, 50, 75, 90)) +
      f"; his position p50 {X.med(hf):.2f}; trigger in 2nd half {100*np.mean(tf>=0.5):.1f}%, last 20% {100*np.mean(tf>=0.8):.1f}%")
    # fill probability of an order vs trigger frac
    P("  order fill rate by trigger position in block (orders that reached the chain):")
    for lo_, hi_ in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .9), (.9, 1.01)):
        v = [vv for k, vv in O.items() if lo_ <= vv[0]["trig_frac"] < hi_]
        if v:
            f = np.mean([any(x["out"] == "landed" for x in vv) for vv in v]); late = np.mean([all(x["out"] == "late" for x in vv) for vv in v])
            P(f"    trig frac {lo_:.1f}-{hi_:.1f}: orders {len(v):5}  filled {100*f:4.0f}%  only-late {100*late:4.0f}%")
    # by leader client / area of the trigger slot
    P("  by leader client of the trigger slot: orders, filled %, landed ms p50, same-slot igap p50")
    for kk in ("trig_client", "trig_area"):
        for cval in sorted({vv[0].get(kk) for vv in O.values()}, key=str):
            v = [vv for vv in O.values() if vv[0].get(kk) == cval]
            if len(v) < 30: continue
            f = np.mean([any(x["out"] == "landed" for x in vv) for vv in v])
            lv = [x for vv in v for x in vv if x["out"] == "landed" and x["trig_gap"] == 0]
            P(f"    {kk}={cval:12} orders {len(v):5} filled {100*f:4.0f}%  landed ms p50 {X.med([x['ms'] for x in lv]) if lv else float('nan'):5.0f}  igap p50 {X.med([x['igap'] for x in lv]) if lv else float('nan'):4.0f}")
    # landed relay by leader client
    P("  landed copy relay by leader client of his slot:")
    cc = collections.defaultdict(collections.Counter)
    for a in [a for a in AA if a["out"] == "landed"]: cc[a["client"]][a["relay"]] += 1
    for k, v in sorted(cc.items(), key=lambda kv: -sum(kv[1].values())):
        n2 = sum(v.values()); P(f"    {k:12} n={n2:5} " + "  ".join(f"{r} {100*b/n2:.0f}%" for r, b in v.most_common(6)))
    P("  landed copy relay by leader AREA:")
    cc = collections.defaultdict(collections.Counter)
    for a in [a for a in AA if a["out"] == "landed"]: cc[a["area"]][a["relay"]] += 1
    for k, v in sorted(cc.items(), key=lambda kv: -sum(kv[1].values())):
        n2 = sum(v.values()); P(f"    {k:12} n={n2:5} " + "  ".join(f"{r} {100*b/n2:.0f}%" for r, b in v.most_common(6)))
    # failed copies by relay (failed txs: tips revert; the recorder still lists the tip transfer? use tip_amt list)
    P("  CU price of landed buys p10/50/90: " + "/".join(f"{X.pct([a['cup'] for a in AA if a['out']=='landed' and a['cup']], q):.0f}" for q in (10, 50, 90)) +
      "; tx fee p50 " + f"{X.med([a['fee'] for a in AA if a['out']=='landed']):.0f} lamports")
    P("  failed-attempt outcome by trigger position (frac): ")
    for lo_, hi_ in ((0, .5), (.5, .8), (.8, 1.01)):
        v = [a for a in AA if "trig_frac" in a and lo_ <= a["trig_frac"] < hi_]
        cc2 = collections.Counter(a["out"] for a in v); n2 = len(v)
        P(f"    trig frac {lo_:.1f}-{hi_:.1f}: n {n2:5} " + "  ".join(f"{k} {100*x/n2:.0f}%" for k, x in cc2.most_common()))
open(f"{X.D}/a4.txt", "w").write("\n".join(out) + "\n")
