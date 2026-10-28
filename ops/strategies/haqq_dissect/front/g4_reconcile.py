#!/usr/bin/env python3
"""FRONT addendum step 4 (read-only, MEASURED): k4 vs k8 incl. FRA27; why k8 did not move the first after-dump try.
- (a)/(b) tables with FRA26+FRA27 pooled (k8 cli40/cfg20);
- block position of ALL our landed tries (send slot vs next slot);
- the first try after a dump: signed BEFORE the engine had seen the dump (pre-sent) or after; tries landing within 50 ms after the dump;
- paying dumps: first try ms and 'first' share per leader client, k4 vs k8.
Out: sniper-data/haqq_dissect/front/g4.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
pc = lambda v, q: float(np.percentile(v, q)) if len(v) else float("nan")
rows = pickle.load(open(f"{OUT}/g2_rows.pkl", "rb")) + pickle.load(open(f"{OUT}/g3_r27_rows.pkl", "rb"))
K8 = lambda g: g.startswith("k8")
GS = [("k4 (20/s)", lambda r: r["g"] == "k4 cap20"), ("k8 all", lambda r: K8(r["g"])), ("k8 cap30 (AMS17,19,32,33)", lambda r: r["g"] in ("k8 cap30", "k8 cli40/cfg30")),
      ("k8 cfg20 (FRA26,27)", lambda r: r["g"] == "k8 cli40/cfg20")]
rng = np.random.default_rng(5)
def bmed(v):
    v = np.asarray(v, float)
    if len(v) < 5: return (np.nan, np.nan)
    b = [np.median(v[rng.integers(0, len(v), len(v))]) for _ in range(500)]; return pc(b, 5), pc(b, 95)
def tab(title, sel):
    P(f"\n## {title}")
    P("| group | dumps | try landed <= 2 slots after | first try ms p25/p50/p75 [90% CI of p50] | same slot | buys ahead p50 | we were first | first try filled | any try filled | front #1 ms p50 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for nm, f in GS:
        v = [r for r in rows if f(r) and sel(r)]
        if not v: continue
        a = [r for r in v if "ms" in r]; ms = [r["ms"] for r in a]; lo, hi = bmed(ms)
        P(f"| {nm} | {len(v):,} | {100*len(a)/len(v):.0f}% | {pc(ms,25):.0f}/{pc(ms,50):.0f}/{pc(ms,75):.0f} [{lo:.0f}..{hi:.0f}] | {100*np.mean([r['same'] for r in a]):.0f}% | "
          f"{pc([r['ahead'] for r in a],50):.0f} | {100*np.mean([r['ahead']==0 for r in a]):.0f}% | {100*np.mean([r['ok'] for r in a]):.0f}% | {100*np.mean([r['anyok'] for r in a]):.0f}% | "
          f"{pc([r['f1ms'] for r in v if r['f1ms'] is not None],50):.1f} |")
tab("(a) dumps >= 12% in armed windows", lambda r: r["drop"] >= 0.12)
tab("(b) PAYING dumps (front value >= +30 mSOL) in armed windows", lambda r: r["vf"] >= 0.030)
tab("(b) non-paying dumps >= 12%", lambda r: not (r["vf"] >= 0.030) and r["drop"] >= 0.12)
# per client on paying + all >=12%
P("\n## Paying dumps by the client of the slot our first try landed in")
P("| client | k4: n | k4: first-try ms p50 | k4: we were first | k8: n | k8: ms p50 | k8: we were first |")
P("|---|---|---|---|---|---|---|")
pay = [r for r in rows if r["vf"] >= 0.030 and "ms" in r]
for c in sorted({r["client"] for r in pay}, key=lambda c: -sum(r["client"] == c for r in pay)):
    a = [r for r in pay if r["client"] == c and r["g"] == "k4 cap20"]; b = [r for r in pay if r["client"] == c and K8(r["g"])]
    if len(a) + len(b) < 20: continue
    P(f"| {c} | {len(a)} | {pc([r['ms'] for r in a],50):.0f} | {100*np.mean([r['ahead']==0 for r in a]) if a else float('nan'):.0f}% | {len(b)} | "
      f"{pc([r['ms'] for r in b],50):.0f} | {100*np.mean([r['ahead']==0 for r in b]) if b else float('nan'):.0f}% |")
# block position of all landings
RU = pickle.load(open(f"{OUT}/g1_runs.pkl", "rb"))
s0, bsz = L.slot_sizes(); SMAX = s0 + len(bsz) - 1
P("\n## Where our tries land in the block (ALL landed tries, tape runs)")
P("| group | landed in send slot: block pos p10/p25/p50/p75 | landed in NEXT slot: block pos p10/p25/p50/p75 | share of all landings in the first 40% of a block |")
P("|---|---|---|---|")
for nm, ks in (("k4", lambda c: c["k"] == 4), ("k8", lambda c: c["k"] == 8)):
    a = []; b = []
    for run, x in RU.items():
        if not ks(x["cfg"]): continue
        for t in x["tries"]:
            if t.get("slot") is None or t.get("idx") is None or not (s0 <= t["slot"] <= SMAX): continue
            p = t["idx"] / bsz[t["slot"] - s0]
            (a if t["slot"] == t["send_slot"] else b if t["slot"] == t["send_slot"] + 1 else []).append(p)
    al = np.array(a + b)
    P(f"| {nm} | {pc(a,10):.2f}/{pc(a,25):.2f}/{pc(a,50):.2f}/{pc(a,75):.2f} | {pc(b,10):.2f}/{pc(b,25):.2f}/{pc(b,50):.2f}/{pc(b,75):.2f} | {100*np.mean(al<0.4):.0f}% |")
# pre-sent or reactive: the first try after each dump, was it signed before the engine saw the dump (sign position < dump)?
P("\n## The first try after the dump: signed before the engine saw the dump (pre-sent) vs after; send -> land")
trs = {}
for run, x in RU.items():
    for t in x["tries"]:
        if t.get("slot") is not None and t.get("idx") is not None: trs[(run, t["mint"], t["slot"], t["idx"])] = t
P("| group | dumps (try after) | signed before seeing the dump | its land ms after the dump p50 | signed after seeing it | land ms p50 | tries landing within 50 ms after the dump: mean |")
P("|---|---|---|---|---|---|---|")
for nm, f in GS:
    v = [r for r in rows if f(r) and "ms" in r and r["drop"] >= 0.12]
    pre = []; post = []; n50 = []
    for r in v:
        cand = [t for (run, m, s, i), t in trs.items() if run == r["run"] and m == r["mint"] and (s, i) > (r["ds"], r["di"]) and s <= r["ds"] + 2] if False else None
    # (efficient) group tries by (run, mint)
    by = collections.defaultdict(list)
    for (run, m, s, i), t in trs.items(): by[(run, m)].append(t)
    for r in v:
        aft = sorted([t for t in by[(r["run"], r["mint"])] if (t["slot"], t["idx"]) > (r["ds"], r["di"]) and t["slot"] <= r["ds"] + 2], key=lambda t: (t["slot"], t["idx"]))
        if not aft: continue
        t = aft[0]; ps = tuple((t.get("pos") or [0, 0])[:2])
        (pre if ps < (r["ds"], r["di"]) else post).append(r["ms"])
        if r["run"] != "FRA27":
            n50.append(sum(1 for z in aft if L.cc(z["slot"], z["idx"]) - L.cc(r["ds"], r["di"]) <= 50))
    P(f"| {nm} | {len(pre)+len(post)} | {100*len(pre)/max(len(pre)+len(post),1):.0f}% | {pc(pre,50):.0f} | {100*len(post)/max(len(pre)+len(post),1):.0f}% | {pc(post,50):.0f} | {np.mean(n50) if n50 else float('nan'):.2f} |")
open(f"{OUT}/g4.txt", "w").write("\n".join(out) + "\n")
