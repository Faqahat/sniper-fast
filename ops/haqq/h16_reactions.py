#!/usr/bin/env python3
# haqq SELL study, step 16: event reactions. For every outside trade while a lot is open (after its buy, before its first sell):
# did the lot's first sell land within 0-150 ms after it (block-position proxy), and does that depend on the trade (side, size,
# wallet type) and the profile? Baseline = all outside trades while open.
import sys, json, pickle, zlib, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
from multiprocessing import Pool
PROF = {0.25: "A.25", 0.27: "B.27", 0.3: "C.30", 0.4: "D.40", 0.49: "E.49", 0.01: "P.01"}
prof = lambda sz: PROF.get(round(sz, 2), "BIG" if sz >= 0.6 else "other")
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
SS = {}
def init():
    for run in ("R1", "R2", "R3", "R4"):
        for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(s, 400), i + 1) * H.SMS
LOTS = None; LAUNCH = None
def work(b):
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb")); out = []
    for li, l in LOTS.get(b, []):
        d = tp.get(l["m"])
        if d is None: continue
        T = d["T"]; Wl = d["W"]; k = l["buy"]["k"]
        if k >= len(T) or Wl[T[k, 5]] != H.W: continue
        x0 = l["sells"][0]
        ks = next((j for j in range(k + 1, len(T)) if T[j, 0] == x0["s"] and T[j, 1] == x0["i"] and Wl[T[j, 5]] == H.W and not T[j, 6]), None)
        if ks is None: continue
        a_s = A(int(T[ks, 0]), int(T[ks, 1]))
        cre = LAUNCH.get(l["m"])
        S0 = cre[0] if cre else None
        q = float(T[k, 8]); cost = l["cost"] * 1e9
        pf = prof(l["buy"]["sol"])
        for j in range(k + 1, ks):
            u = Wl[T[j, 5]]
            if u == H.W: continue
            a = A(int(T[j, 0]), int(T[j, 1]))
            dt = a_s - a
            wt = "creator" if cre and (u == cre[1] or u == cre[2]) else ("cohort" if u in COH else ("hk" if u == H.HK else "other"))
            fr = (T[j, 13] + T[j, 14]) / 1e4
            ret = T[j, 9] * q / (T[j, 10] + q) * (1 - fr) / cost - 1
            p_pre = (T[j, 9] + (-T[j, 7] if T[j, 6] else T[j, 7])) / max(1, (T[j, 10] + (T[j, 8] if T[j, 6] else -T[j, 8])))
            move = (T[j, 9] / T[j, 10]) / p_pre - 1
            nxt = j + 1 < ks and Wl[T[j + 1, 5]] != H.W
            out.append((pf, bool(T[j, 6]), float(T[j, 7]) / 1e9, wt, float(dt), bool(dt <= 150), float(ret), float(move), l["run"], j == ks - 1 or all(Wl[T[jj, 5]] == H.W for jj in range(j + 1, ks))))
    return out
if __name__ == "__main__":
    lots = json.load(open(f"{H.OUT}/lots.json"))
    LAUNCH = {}
    for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426", "run_20261024_1425"):
        for line in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
            try: c = json.loads(line)
            except Exception: continue
            LAUNCH.setdefault(c["mint"], (c["slot"], c.get("creator"), c.get("user")))
    by = collections.defaultdict(list)
    for li, l in enumerate(lots):
        if l["closed"] and not l["censored"] and not l["brk"]: by[zlib.crc32(l["m"].encode()) % 64].append((li, l))
    LOTS = by
    R = []
    with Pool(6, initializer=init) as p:
        for o in p.imap_unordered(work, range(64)): R += o
    pickle.dump(R, open(f"{H.OUT}/reactions.pkl", "wb"))
    R = np.array(R, dtype=object)
    print("outside trades while lots open:", len(R))
    for pf in ("A.25", "B.27", "C.30", "D.40", "E.49", "P.01", "BIG"):
        S = [r for r in R if r[0] == pf]
        if not S: continue
        base = np.mean([r[5] for r in S])
        print(f"\n{pf}: events {len(S)}, P(lot sold within 150 ms after an event) {base:.1%}")
        for lab, f in (("sell >=1 SOL", lambda r: (not r[1]) and r[2] >= 1), ("sell 0.3-1", lambda r: (not r[1]) and 0.3 <= r[2] < 1), ("sell <0.3", lambda r: (not r[1]) and r[2] < 0.3),
                       ("creator sell", lambda r: (not r[1]) and r[3] == "creator"), ("cohort sell", lambda r: (not r[1]) and r[3] == "cohort"),
                       ("buy >=1 SOL", lambda r: r[1] and r[2] >= 1), ("buy 0.3-1", lambda r: r[1] and 0.3 <= r[2] < 1), ("buy <0.3", lambda r: r[1] and r[2] < 0.3),
                       ("price move <= -10%", lambda r: r[7] <= -0.10), ("price move >= +10%", lambda r: r[7] >= 0.10),
                       ("lot ret <= -20% after it", lambda r: r[6] <= -0.2), ("lot ret >= +25% after it", lambda r: r[6] >= 0.25)):
            s = [r for r in S if f(r)]
            if len(s) >= 30: print(f"   {lab:26s} n {len(s):6d}: {np.mean([r[5] for r in s]):6.1%}  (x{np.mean([r[5] for r in s]) / max(base, 1e-9):.1f})")
