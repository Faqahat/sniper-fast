#!/usr/bin/env python3
"""vs248 step 9 (read-only): 248's refused-by-us lots (REF:* buckets) and S_FAIL lots, D2-D5: split 248's P&L there into
EXIT (its sell time vs our timer styles at ITS OWN entry) and COSTS (its 0.54 vs our measured per-fill costs). Exact replay (INFERRED);
248's entry is MEASURED (not our landing - our landing on these is analyst F's rank-model work). Followers x1.0 / x0.9.
Our styles: pre-send exit = sell decided 0.40 s after the fill (our p50 hold), regular = 0.87 s (our p50 hold); +0 here because the
hold already includes our sell landing. Costs per fill (mSOL): NOW ps 2.54 / reg 4.38 (MEASURED v4 sec 6), S2 1.86 (analyst D/F), 248 0.54."""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/vs248")
from v5_extra import M, sim
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_vs248"
DAYS = (2, 3, 4, 5)
Z = pickle.load(open(f"{OUT}/v2.pkl", "rb")); H = Z["H"]
Z1 = pickle.load(open(f"{OUT}/v1.pkl", "rb"))
span = {int(m): (int(a), int(e)) for m, a, e in zip(Z1["mints"], Z1["st"], Z1["en"])}
S = np.load(f"{SCR}/tape_sub.npy", mmap_mode="r"); CC = np.load(f"{SCR}/tape_cc.npy", mmap_mode="r")
cache = {}
def mint(mi):
    if mi not in cache:
        if len(cache) > 400: cache.clear()
        a, e = span[mi]; cache[mi] = M(S, CC, a, e)
    return cache[mi]
grp = lambda b: "REF:gate" if b.startswith("REF:gate") else "REF:other reasons" if b.startswith("REF") else b
acc = collections.defaultdict(lambda: collections.defaultdict(list))
for h in H:
    if h["day"] not in DAYS or h["open"] or not h["sells"]: continue
    g = grp(h["bucket"])
    if g not in ("REF:gate", "REF:other reasons", "S_FAIL", "NOENG", "NODUMP"): continue
    m = mint(h["mi"]); rm = set(s[1] for s in h["sells"]); own = [(s[1] - 1, s[3]) for s in h["sells"]]
    for fol in (1.0, 0.9):
        his = sim(m, h["k"], h["tok"], h["fee"], own, rm, fol) - h["cost"]
        r = dict(his=his)
        for nm, ms in (("t040", 400), ("t087", 870), ("t2s", 2000)):
            q = int(np.searchsorted(m.cc, h["cc"] + ms, side="right")) - 1
            r[nm] = sim(m, h["k"], h["tok"], h["fee"], [(max(q, h["k"]), 1.0)], rm, fol) - h["cost"]
        acc[(g, fol)]["rows"].append((h["day"], r))
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
P("# 248's lots on dumps we did not fill (D2-D5), at 248's OWN entry: its exit vs our timer styles, x its / our costs; SOL per day (INFERRED replay)")
P("| bucket | followers | lots | 248 exit, 248 cost (= measured) | 248 exit, our S2 cost | 248 exit, our NOW reg cost | our ps-style 0.40 s, NOW ps cost | our reg-style 0.87 s, NOW reg cost | 2 s timer, NOW reg cost |")
P("|---|---|---|---|---|---|---|---|---|")
for (g, fol), d in sorted(acc.items()):
    rows = d["rows"]; n = len(rows)
    def per(k, c): return np.mean([sum(r[k] - c for dd, r in rows if dd == day) for day in DAYS])
    P(f"| {g} | x{fol} | {n} | {per('his', 0.00054):+.2f} | {per('his', 0.00186):+.2f} | {per('his', 0.00438):+.2f} | {per('t040', 0.00254):+.2f} | {per('t087', 0.00438):+.2f} | {per('t2s', 0.00438):+.2f} |")
open(f"{OUT}/v9_refused.txt", "w").write("\n".join(out) + "\n")
