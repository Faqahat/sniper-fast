#!/usr/bin/env python3
# haqq SELL study, step 11: what comes right before its sells (tape level, block-position ms proxy).
# For every lot's FIRST sell: the last 3 outside trades before it (side, size, wallet type, ms before), the lot return just before
# the sell, and whether the sell slot is one of the profile's checkpoints. Baseline: the same stats at random tape points while held.
import sys, json, pickle, zlib, collections, random, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
from multiprocessing import Pool
WTN = {0: "other", 1: "creator", 2: "bundle", 3: "sniper", 4: "cohort", 5: "hk", 6: "dyx", 7: "ours", 8: "haqq"}
CPS = {"A.25": {9, 17, 25, 33, 41, 49, 57, 65}, "C.30": {9, 17, 25, 33, 41, 49, 57, 65}, "P.01": {9, 17, 25, 33, 41, 49, 57, 65, 201},
       "B.27": {10, 12, 15, 20, 25, 30, 40, 50, 60, 65, 201}, "D.40": {10, 12, 15, 20, 25, 30, 40, 50, 60, 65, 201}, "E.49": {20}}
prof = lambda sz: {0.25: "A.25", 0.27: "B.27", 0.3: "C.30", 0.4: "D.40", 0.49: "E.49", 0.01: "P.01"}.get(round(sz, 2), "BIG" if sz >= 0.6 else "other")
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
DYX = "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw"
SS = {}
def init():
    for run in ("R1", "R2", "R3", "R4"):
        for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(s, 400), i + 1) * H.SMS
LOTS = None
def work(b):
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb")); out = []; rng = random.Random(b)
    for li, l in LOTS.get(b, []):
        d = tp.get(l["m"])
        if d is None: continue
        T = d["T"]; Wl = d["W"]; users = [Wl[x] for x in T[:, 5]]; k = l["buy"]["k"]
        if k >= len(T) or users[k] != H.W: continue
        q = float(T[k, 8]); cost = l["cost"] * 1e9
        x0 = l["sells"][0]
        ks = next((j for j in range(k + 1, len(T)) if T[j, 0] == x0["s"] and T[j, 1] == x0["i"] and users[j] == H.W), None)
        if ks is None: continue
        creator = None
        def wt(u, j):
            if u in H.US: return 7
            if u == H.HK: return 5
            if u == DYX: return 6
            if u in COH: return 4
            return 0
        def ctx(kk):
            a_s = A(int(T[kk, 0]), int(T[kk, 1]))
            prev = [j for j in range(kk - 1, k, -1) if users[j] != H.W][:3]
            fr = (T[kk - 1, 13] + T[kk - 1, 14]) / 1e4
            ret = T[kk - 1, 9] * q / (T[kk - 1, 10] + q) * (1 - fr) / cost - 1
            p3 = [(bool(T[j, 6]), T[j, 7] / 1e9, wt(users[j], j), a_s - A(int(T[j, 0]), int(T[j, 1])), int(T[kk, 0] - T[j, 0])) for j in prev]
            own_prev = next((j for j in range(kk - 1, k, -1) if users[j] == H.W), None)
            return dict(ret=float(ret), prev=p3, own_gap=(a_s - A(int(T[own_prev, 0]), int(T[own_prev, 1]))) if own_prev is not None else None)
        ref = l["buy"]["s"] - (l["buy"]["trig_ds"] or 0) if l["buy"]["dip"] else None
        dd = x0["s"] - ref if ref is not None else None
        pf = prof(l["buy"]["sol"])
        c = ctx(ks); c.update(li=li, pf=pf, d=dd, cp=(dd in CPS.get(pf, set()) or (dd - 1) in CPS.get(pf, set())) if dd is not None else None, kind="sell", run=l["run"])
        out.append(c)
        # baseline: a random outside trade strictly between buy and sell
        cand = [j for j in range(k + 2, ks) if users[j] != H.W]
        if cand:
            j = rng.choice(cand); c2 = ctx(j); c2.update(li=li, pf=pf, d=(int(T[j, 0]) - ref) if ref is not None else None, kind="base", run=l["run"]); out.append(c2)
    return out
if __name__ == "__main__":
    lots = json.load(open(f"{H.OUT}/lots.json"))
    by = collections.defaultdict(list)
    for li, l in enumerate(lots):
        if l["closed"] and not l["censored"] and not l["brk"]: by[zlib.crc32(l["m"].encode()) % 64].append((li, l))
    LOTS = by
    R = []
    with Pool(6, initializer=init) as p:
        for o in p.imap_unordered(work, range(64)): R += o
    pickle.dump(R, open(f"{H.OUT}/triggers.pkl", "wb"))
    def q(v, ps=(10, 25, 50, 75, 90)):
        return " / ".join(f"{x:.0f}" for x in np.percentile(v, ps)) if v else "-"
    for grp in ("sell", "base"):
        for cpf in (True, False, None):
            sel = [r for r in R if r["kind"] == grp and (cpf is None or r.get("cp") == cpf)]
            if grp == "base" and cpf is not None: continue
            if not sel: continue
            last = [r["prev"][0] for r in sel if r["prev"]]
            lab = grp + ("" if cpf is None else (" at checkpoint" if cpf else " off checkpoint"))
            print(f"\n== {lab}: n {len(sel)}")
            print(f"   last outside trade before: buy {np.mean([x[0] for x in last]):.0%}; ms before p10..p90 {q([x[3] for x in last])}; same slot {np.mean([x[4] == 0 for x in last]):.0%}")
            for side in (True, False):
                sz = [x[1] for x in last if x[0] == side]
                print(f"   last trade {'BUY' if side else 'SELL'} size p25/50/75/90: {' / '.join(f'{v:.2f}' for v in np.percentile(sz, (25, 50, 75, 90)))}; >=1 SOL {np.mean([v >= 1 for v in sz]):.0%}")
            print("   last trade wallet:", collections.Counter(WTN[x[2]] for x in last).most_common(5))
            print(f"   lot return just before: p10..p90 {' / '.join(f'{v:+.2f}' for v in np.percentile([r['ret'] for r in sel], (10, 25, 50, 75, 90)))}")
