#!/usr/bin/env python3
# haqq SELL study, step 17: does it copy the exits of the OTHER bots that bought the same dump? Co-buyers = outside wallets that
# bought between the dump and 1 slot after haqq's buy. Per open slot d of each dip lot: did a co-buyer sell in the previous 2 slots
# (x), and did haqq's first sell land in slot d (y)? Core profiles, d <= 70, stratified by size and slot. Also: share of co-buyers already out at haqq's sell vs at a random open slot.
import sys, json, pickle, zlib, collections, random, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
from multiprocessing import Pool
LOTS = None
def work(b):
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb")); out = []; rng = random.Random(b)
    for li, l in LOTS.get(b, []):
        d = tp.get(l["m"])
        if d is None or not l["buy"]["dip"]: continue
        T = d["T"]; Wl = d["W"]; k = l["buy"]["k"]
        if k >= len(T) or Wl[T[k, 5]] != H.W: continue
        ref = l["buy"]["s"] - l["buy"]["trig_ds"]; bslot = l["buy"]["s"]
        first = l["sells"][0]["s"]
        co = set()
        for j in range(k - 1, -1, -1):
            if T[j, 0] < ref: break
            if T[j, 6] and Wl[T[j, 5]] != H.W: co.add(T[j, 5])
        for j in range(k + 1, len(T)):
            if T[j, 0] > bslot + 1: break
            if T[j, 6] and Wl[T[j, 5]] != H.W: co.add(T[j, 5])
        if not co: continue
        sold_at = {}
        for j in range(k + 1, len(T)):
            if T[j, 0] > first + 1: break
            u = T[j, 5]
            if u in co and not T[j, 6] and u not in sold_at: sold_at[u] = int(T[j, 0])
        for s in range(bslot + 1, first + 1):
            x = any(s - 2 <= v <= s - 1 for v in sold_at.values())
            x0 = any(v == s for v in sold_at.values())
            frac = sum(1 for v in sold_at.values() if v <= s - 1) / len(co)
            out.append((l["run"], round(l["buy"]["sol"], 2), s - ref, int(x), int(x0), frac, int(s == first), len(co)))
    return out
if __name__ == "__main__":
    lots = json.load(open(f"{H.OUT}/lots.json"))
    by = collections.defaultdict(list)
    for li, l in enumerate(lots):
        if l["closed"] and not l["censored"] and not l["brk"] and round(l["buy"]["sol"], 2) in (0.25, 0.27, 0.3, 0.4): by[zlib.crc32(l["m"].encode()) % 64].append((li, l))
    LOTS = by
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, range(64)): R += o
    R = [r for r in R if r[2] <= 70]
    A_ = np.array([(r[1], r[2], r[3], r[4], r[6]) for r in R], float); sz, d, x, x0, yy = A_.T
    print("core profiles (0.25/0.27/0.30/0.40), slots d<=70, stratified by (size, slot d after the trigger):")
    for key, col in (("a co-buyer sold in d-2..d-1", x), ("a co-buyer sells in the same slot d", x0)):
        ob = ex = 0.0; nn = 0
        for s_ in np.unique(sz):
            for dd in np.unique(d):
                m = (sz == s_) & (d == dd)
                if m.sum() < 20: continue
                base = yy[m & (col == 0)].mean() if (m & (col == 0)).sum() else yy[m].mean()
                mm = m & (col == 1); ob += yy[mm].sum(); ex += base * mm.sum(); nn += int(mm.sum())
        print(f"   {key}: haqq sells observed {ob:.0f} vs expected {ex:.0f} (x{ob / max(ex, 1e-9):.2f}) over {nn} open slots")
    R = np.array(R, dtype=object)
    y = R[:, 6].astype(int); x = R[:, 3].astype(int); x0 = R[:, 4].astype(int); fr = R[:, 5].astype(float)
    print(f"open slots {len(R)}, sells {y.sum()}; co-buyers per lot median {np.median(R[:, 7].astype(int))}")
    print(f"P(haqq sells in slot d | a co-buyer sold in d-2..d-1) {y[x == 1].mean():.2%} (n {int((x == 1).sum())}) vs no co-buyer sell {y[x == 0].mean():.2%}")
    print(f"P(haqq sells in slot d | a co-buyer sells in the same slot d) {y[x0 == 1].mean():.2%} vs not {y[x0 == 0].mean():.2%}")
    for lo, hi in ((0, 0.001), (0.001, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)):
        m = (fr >= lo) & (fr < hi)
        if m.sum() > 100: print(f"   share of co-buyers already out [{lo:g},{hi:g}): P(sell) {y[m].mean():.2%} n {int(m.sum())}")
