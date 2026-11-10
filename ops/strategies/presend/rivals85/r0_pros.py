#!/usr/bin/env python3
"""RIVALS85 step 0 [MEASURED on the decoded market tapes, read-only]: auto-detected "pros" per live run window (AMS r34..r39).
A pro = a wallet that BOUGHT a token in the same slot or the next 2 after a >= 1 SOL sell of that token (the token's most recent
>= 1 SOL sell, by another wallet), counted once per (sell, wallet), at least 50 times inside the run window.
(src/obs/select.rs "pro": same rule but a rolling 6 h window and a 64-wallet cap per sell; here the run window, no cap.)
Sources (non-overlapping slot segments):
  presend_quiet3/chain.npz  .. 462708348        (r34, r35, most of r36)
  presend_quiet4/tab37      462708349 .. 463013393 (r36 tail, r37)
  prevent/guards/tab_tail   463013394 .. 463023360 (r37 tail)
  multiarm/tab38f           463021093 .. 463053837 (r38)
  multiarm/tab39            463081489 .. 463111634 (r39)
  rivals85/tab39x           463111635 .. 463117245 (r39, decoded here from the recorder chunks)
Out: /home/it/sniper-data/rivals85/pros.json
usage: r0_pros.py"""
import json, collections
import numpy as np

D = "/home/it/sniper-data"
OUT = f"{D}/rivals85"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
RUNS = {"A34": (462520928, 462574692), "A35": (462574968, 462646113), "A36": (462646721, 462712887),
        "A37": (462713754, 463023440), "A38": (463024367, 463052069), "A39": (463084997, 463117245)}
SEGS = [("chain", f"{D}/presend_quiet3", 0, 462708348), ("tab", f"{D}/presend_quiet4/tab37", 462708349, 463013393),
        ("tab", f"{D}/prevent/guards/tab_tail", 463013394, 463023360), ("tab", f"{D}/multiarm/tab38f", 463021093, 463053837),
        ("tab", f"{D}/multiarm/tab39", 463081489, 463111634), ("tab", f"{D}/rivals85/tab39x", 463111635, 463117245)]
PRO_MIN = 50


def counts(s, i, j, mint, user, buy, sol):
    """per user id: number of distinct >= 1 SOL sells it bought after (same slot or next 2, chain order, not the seller)"""
    n = len(s)
    if n == 0: return {}, 0
    o = np.lexsort((j, i, s, mint))          # by mint, then chain order
    m = mint[o]; ss = s[o]; u = user[o]; b = buy[o].astype(bool); so = sol[o]
    big = (~b) & (so >= 1_000_000_000)
    pos = np.where(big, np.arange(n), -1)
    last = np.maximum.accumulate(pos)
    gs = np.r_[0, np.nonzero(m[1:] != m[:-1])[0] + 1]
    gstart = np.repeat(gs, np.diff(np.r_[gs, n]))
    ok = b & (last >= gstart)
    lc = np.where(ok, last, 0)
    ok &= ss <= ss[lc] + 2
    ok &= u != u[lc]
    pr = np.unique(np.stack([last[ok].astype(np.int64), u[ok].astype(np.int64)]), axis=1)
    c = collections.Counter(pr[1].tolist())
    return c, int(big.sum())


def seg_rows(kind, path, lo, hi):
    if kind == "chain":
        z = np.load(f"{path}/chain.npz"); s = z["s"]; sel = np.nonzero((s >= lo) & (s <= hi))[0]; s = s[sel]
        cols = {k: z[k][sel] for k in ("i", "j", "mint", "user", "buy", "sol")}
        names = json.load(open(f"{path}/ids.json"))["user"]
        return s, cols["i"], cols["j"], cols["mint"], cols["user"], cols["buy"], cols["sol"], names
    T = np.load(f"{path}/trades.npy", mmap_mode="r"); sl = np.asarray(T["slot"])
    sel = np.nonzero((sl >= lo) & (sl <= hi))[0]; t = T[sel]
    names = json.load(open(f"{path}/ids.json"))
    return np.asarray(t["slot"]), np.asarray(t["idx"]), np.asarray(t["j"]), np.asarray(t["mint"]), np.asarray(t["user"]), np.asarray(t["buy"]), np.asarray(t["sol"]), names


if __name__ == "__main__":
    res = {}
    cache = {}
    for run, (a, b) in RUNS.items():
        tot = collections.Counter(); nbig = 0; ntr = 0; segs = []
        for kind, path, lo, hi in SEGS:
            x, y = max(a, lo), min(b, hi)
            if x > y: continue
            key = (path, x, y)
            s, i, j, mint, user, buy, sol, names = seg_rows(kind, path, x, y)
            c, nb = counts(s, i, j, mint, user, buy, sol)
            for k, v in c.items():
                w = names[k]
                if w not in OURS: tot[w] += v
            nbig += nb; ntr += len(s); segs.append([path.split("/")[-1], x, y, len(s)])
            del s, i, j, mint, user, buy, sol
        hrs = (b - a) * 0.2135 / 3600
        res[run] = {"slots": [a, b], "hours_approx": round(hrs, 2), "trades": ntr, "big_sells": nbig, "segs": segs,
                    "counts_ge10": {w: v for w, v in tot.most_common() if v >= 10},
                    "pros": sorted(w for w, v in tot.items() if v >= PRO_MIN)}
        print(run, f"{hrs:.1f} h trades {ntr:,} big sells {nbig:,} pros(>=50) {len(res[run]['pros'])} top", tot.most_common(5), flush=True)
    union = sorted(set().union(*[set(r["pros"]) for r in res.values()]))
    res["union_pros"] = union
    print("union pros", len(union))
    json.dump(res, open(f"{OUT}/pros.json", "w"))
