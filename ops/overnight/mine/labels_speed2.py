#!/usr/bin/env python3
# Same moments as mine.pkl / mine_r4.pkl, new labels for FASTER landing: our buy lands T = 20 / 35 ms after the trigger. Holds 1 / 3 s, followers
# kept and dropped-2-slots. Output labels_speed2.pkl (row order = mine.pkl rows, then mine_r4.pkl rows).
import os, sys, pickle, collections, numpy as np, json, glob, gzip, base64
sys.argv = ["build.py"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as Bd, r4build as R4
from multiprocessing import Pool
def lab(tr, t0, T, drop2):
    k = max((i for i, t in enumerate(tr) if Bd.ms(t["s"], t["i"]) <= t0), default=None)
    if k is None: return [np.nan, np.nan]
    kf = k
    while kf + 1 < len(tr) and Bd.ms(tr[kf + 1]["s"], tr[kf + 1]["i"]) - t0 <= T: kf += 1
    V, Tk = tr[kf]["vsol"], tr[kf]["vtok"]
    if V <= 0 or V > 112e9: return [np.nan, np.nan]
    X = 1e9 / 1.0125; kk = V * Tk; V2 = V + X; Tk2 = kk / V2; q = Tk - Tk2; V, Tk = V2, Tk2; fill = t0 + T; fs = tr[kf]["s"]
    val = lambda V, Tk: (V - V * Tk / (Tk + q)) * (1 - 0.0125) / 1e9
    path = [(fill, val(V, Tk))]
    for t in tr[kf + 1:]:
        mt = Bd.ms(t["s"], t["i"])
        if mt - fill > 3_500: break
        if t["buy"]:
            if drop2 and t["s"] - fs <= 2: continue
            V2 = V + t["sol"]; Tk = V * Tk / V2; V = V2
        else: Tk2 = Tk + t["tok"]; V = V * Tk / Tk2; Tk = Tk2
        path.append((mt, val(V, Tk)))
    return [[p for m_, p in path if m_ - fill <= h * 1000][-1] - 1.003 for h in (1, 3)]
def work(args):
    key, items, tapes = args
    if tapes is None: tapes = Bd.rp.read_bucket(key[0], key[1], {m for m, _, _ in items})
    out = []
    for m, t0, idx in items:
        tr = tapes.get(m)
        if not tr: out.append((idx, [np.nan] * 8)); continue
        row = []
        for T in (10, 50):
            row += lab(tr, t0, T, False) + lab(tr, t0, T, True)
        out.append((idx, row))
    return out
if __name__ == "__main__":
    D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb"))
    n = len(D["M"]); Y = np.full((n + len(D4["M"]), 8), np.nan, np.float32)
    groups = collections.defaultdict(list)
    for idx, (m, t0, run, bt) in enumerate(D["M"]): groups[(run, Bd.rp.bucket(m))].append((m, t0, idx))
    with Pool(12) as p:
        for out in p.imap_unordered(work, [(k, v, None) for k, v in groups.items()], chunksize=2):
            for idx, row in out: Y[idx] = row
    # R4: re-parse the raw recording (same files as r4build)
    RUN = "/home/moiz/sniper-data/collect/run_20261024_1425"; files = sorted(glob.glob(f"{RUN}/txs/*.jsonl.gz"))[:-1]
    T4 = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(R4.parse, files):
            for m, v in o.items(): T4[m] += v
    T4 = {m: sorted(v, key=lambda t: (t["s"], t["i"], t["j"])) for m, v in T4.items()}
    items = [(m, t0, n + idx) for idx, (m, t0, run, bt) in enumerate(D4["M"])]
    for idx, row in work((("R4", 0), items, T4)): Y[idx] = row
    pickle.dump(dict(Y=Y, cols=["10ms_1s", "10ms_3s", "10ms_1s_drop2", "10ms_3s_drop2", "50ms_1s", "50ms_3s", "50ms_1s_drop2", "50ms_3s_drop2"]), open("labels_speed2.pkl", "wb"))
    print("labels done", Y.shape, "nan share", float(np.isnan(Y).mean()))
