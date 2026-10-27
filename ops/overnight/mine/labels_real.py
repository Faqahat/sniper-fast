#!/usr/bin/env python3
# REALISTIC labels: our 1 SOL buy lands T ms after the trigger; every outside buy within 2 slots after our fill keeps its OWN slippage limit:
# decoded limit if known (core/slip_args.jsonl), else a deterministic draw from the measured tolerance distribution for its size bucket.
# It fails (is removed) if our buy pushed its tokens-out below its limit. Later followers (> 2 slots) saw our buy and are kept.
# Latencies 10/20/35/50/75 ms, holds 1/3 s. Output labels_real.pkl (row order = mine.pkl then mine_r4.pkl).
import os, sys, pickle, json, glob, collections, zlib, bisect, numpy as np
sys.argv = ["build.py"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as Bd, r4build as R4
from multiprocessing import Pool
TS = json.load(open("tol_by_sig.json")); TD_ = pickle.load(open("tol_dist.pkl", "rb")); EDGES = TD_["edges"]; DIST = TD_["by"]
def tol(sig, sol):
    if sig in TS: return TS[sig]
    b = max(0, min(len(DIST) - 1, bisect.bisect_right(EDGES, sol / 1e9) - 1)); d = DIST[b]
    return d[int((zlib.crc32(sig.encode()) % 1_000_003) / 1_000_003 * len(d))]
LATS = (10, 20, 35, 50, 75); HOLDS = (1, 3)
def lab(tr, t0):
    k = max((i for i, t in enumerate(tr) if Bd.ms(t["s"], t["i"]) <= t0), default=None)
    if k is None: return [np.nan] * (len(LATS) * len(HOLDS))
    out = []
    for T in LATS:
        kf = k
        while kf + 1 < len(tr) and Bd.ms(tr[kf + 1]["s"], tr[kf + 1]["i"]) - t0 <= T: kf += 1
        V, Tk = tr[kf]["vsol"], tr[kf]["vtok"]
        if V <= 0 or V > 112e9: out += [np.nan] * len(HOLDS); continue
        X = 1e9 / 1.0125; kk = V * Tk; V2 = V + X; Tk2 = kk / V2; q = Tk - Tk2; V, Tk = V2, Tk2; fill = t0 + T; fs = tr[kf]["s"]
        val = lambda V, Tk: (V - V * Tk / (Tk + q)) * (1 - 0.0125) / 1e9
        path = [(fill, val(V, Tk))]
        for j in range(kf + 1, len(tr)):
            t = tr[j]; mt = Bd.ms(t["s"], t["i"])
            if mt - fill > 3_500: break
            if t["buy"]:
                if t["s"] - fs <= 2:
                    pv, pt = tr[j - 1]["vsol"], tr[j - 1]["vtok"]
                    want = pt * t["sol"] / (pv + t["sol"]); got = Tk * t["sol"] / (V + t["sol"])
                    if got > 0 and tol(t["sig"], t["sol"]) < want / got - 1: continue
                V2 = V + t["sol"]; Tk = V * Tk / V2; V = V2
            else: Tk2 = Tk + t["tok"]; V = V * Tk / Tk2; Tk = Tk2
            path.append((mt, val(V, Tk)))
        out += [[p for m_, p in path if m_ - fill <= h * 1000][-1] - 1.003 for h in HOLDS]
    return out
def work(args):
    key, items, tapes = args
    if tapes is None: tapes = Bd.rp.read_bucket(key[0], key[1], {m for m, _, _ in items})
    return [(idx, lab(tapes[m], t0) if tapes.get(m) else [np.nan] * 10) for m, t0, idx in items]
if __name__ == "__main__":
    D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb")); n = len(D["M"])
    Y = np.full((n + len(D4["M"]), 10), np.nan, np.float32)
    groups = collections.defaultdict(list)
    for idx, (m, t0, run, bt) in enumerate(D["M"]): groups[(run, Bd.rp.bucket(m))].append((m, t0, idx))
    with Pool(12) as p:
        for out in p.imap_unordered(work, [(k, v, None) for k, v in groups.items()], chunksize=2):
            for idx, row in out: Y[idx] = row
    RUN = "/home/moiz/sniper-data/collect/run_20261024_1425"; files = sorted(glob.glob(f"{RUN}/txs/*.jsonl.gz"))[:-1]
    T4 = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(R4.parse, files):
            for m, v in o.items(): T4[m] += v
    T4 = {m: sorted(v, key=lambda t: (t["s"], t["i"], t["j"])) for m, v in T4.items()}
    for idx, row in work((("R4", 0), [(m, t0, n + idx) for idx, (m, t0, run, bt) in enumerate(D4["M"])], T4)): Y[idx] = row
    cols = [f"{T}ms_{h}s_real" for T in LATS for h in HOLDS]
    pickle.dump(dict(Y=Y, cols=cols), open("labels_real.pkl", "wb")); print("done", Y.shape)
