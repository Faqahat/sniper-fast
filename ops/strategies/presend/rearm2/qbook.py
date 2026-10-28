#!/usr/bin/env python3
"""QUIET whale-dump book from the tapes (apply_filter.ChainIx.dumps definition): a sell >= 0.3 SOL that drops the price >= 8%
by itself on a curve < 100 SOL; nf = distinct OTHER buyers after it in its slot and the next 2 slots. Out: seller b58 ->
sorted [(slot, bt, nf)] (deduplicated on (slot, idx, j) across tapes). Read-only on the tapes."""
import sys, json, pickle, collections, time
import numpy as np
OUR = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}

def one(tab, out, seen):
    t0 = time.time()
    T = np.load(f"{tab}/trades.npy", mmap_mode="r")
    ids = json.load(open(f"{tab}/ids.json"))
    cols = {c: np.asarray(T[c]) for c in ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "bt")}
    o = np.lexsort((cols["j"], cols["idx"], cols["slot"], cols["mint"]))
    C = {k: v[o] for k, v in cols.items()}
    del cols
    vs = C["vsol"].astype(np.float64); vt = C["vtok"].astype(np.float64); tok = C["tok"].astype(np.float64); sol = C["sol"].astype(np.float64)
    p = vs / np.maximum(vt, 1); pre = (vs + sol) / np.maximum(vt - tok, 1)
    cand = np.flatnonzero((C["buy"] == 0) & (C["sol"] >= 300_000_000) & (C["vsol"] < 100_000_000_000) & (vt > tok) & (p <= 0.92 * pre))
    n = len(C["slot"]); mint = C["mint"]; slot = C["slot"].astype(np.int64); user = C["user"]; buy = C["buy"]
    for k in cand:
        key = (int(slot[k]), int(C["idx"][k]), int(C["j"][k]))
        if key in seen: continue
        seen.add(key)
        u = user[k]; s = slot[k]; m = mint[k]; bs = set(); q = k + 1
        while q < n and mint[q] == m and slot[q] <= s + 2:
            if buy[q] and user[q] != u: bs.add(int(user[q]))
            q += 1
        out[ids[int(u)]].append((int(s), int(C["bt"][k]), len(bs)))
    print(tab, len(cand), f"{time.time() - t0:.0f}s", flush=True)

if __name__ == "__main__":
    out = collections.defaultdict(list); seen = set()
    for tab in sys.argv[2:]: one(tab, out, seen)
    for k in out: out[k].sort()
    pickle.dump(dict(out), open(sys.argv[1], "wb"))
    print("sellers", len(out), "dumps", sum(len(v) for v in out.values()))
