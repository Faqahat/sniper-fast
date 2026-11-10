#!/usr/bin/env python3
"""QUIET4 step 5 [MEASURED, read-only]: token-level 'who traded it BEFORE the trigger' from the raw-recording chain rows that T2-WINDOWS
bucketed per mint (filters3/t2windows/bk, recordings run_20261029_1400 .. run_20261103_1245; NOT recorded 11-01 19:06 -> 11-02 17:50).
For every live position whose mint is in the buckets: rows strictly before the trigger (slot, idx) ->
  pre_n, pre_n120 (rows in the last ~566 slots ~ 120 s), dip bots that traded it (any time / last 50 slots), distinct signers,
  and post-hoc (label only): which known bots bought in our hold.
A position whose mint has no row in the buckets, or whose trigger falls in the unrecorded gap, gets covered=False.
Out: /home/it/sniper-data/filters3/quiet4/tokbots.pkl {position id: dict}.   usage: x5_tokbots.py WORKERS"""
import sys, json, pickle, zlib, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/quiet4")
import q4lib as L
BK = "/home/it/sniper-data/filters3/t2windows/bk"
NB = 64
BOTS = {"8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3": "8yYM", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN": "9pQQ",
        "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb": "E2x1", "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7",
        "haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq": "haqq6", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC",
        "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqi", "2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg": "2Vgg",
        "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d": "sssss", "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E": "sssss",
        "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ": "sssss", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi": "sssss",
        "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ": "Groz", "EUkuD2J2KPcsbEFcSdm7SnkEXw6vAXr6XVB5FhFoziAo": "EUku"}
G = {}


def init(want): G["want"] = want


def job(b):
    want = G["want"].get(b, {})
    if not want: return {}
    rows = collections.defaultdict(list)
    with open(f"{BK}/b{b:02d}.jsonl") as f:
        for l in f:
            s, i, sig, sg, cl, tb = json.loads(l)
            for m in {x[0] for x in tb}:
                if m in want: rows[m].append((s, i, sg, tb))
    out = {}
    for m, ps in want.items():
        rr = sorted(set((s, i, sg, json.dumps(tb)) for s, i, sg, tb in rows.get(m, [])))
        rr = [(s, i, sg, json.loads(tb)) for s, i, sg, tb in rr]
        for pid, ts, ti, fs, endk in ps:
            if not rr: out[pid] = {"covered": False}; continue
            pre = [r for r in rr if (r[0], r[1]) < (ts, ti)]
            d = {"covered": True, "first_s": rr[0][0], "pre_n": len(pre), "pre_n120": sum(1 for r in pre if r[0] >= ts - 566),
                 "pre_signers": len({r[2] for r in pre}),
                 "bots_any": sorted({BOTS[r[2]] for r in pre if r[2] in BOTS}),
                 "bots_50": sorted({BOTS[r[2]] for r in pre if r[2] in BOTS and r[0] >= ts - 50}),
                 "bots_hold": sorted({BOTS[r[2]] for r in rr if r[2] in BOTS and (fs, 0) <= (r[0], r[1]) <= endk})}
            out[pid] = d
    return out


if __name__ == "__main__":
    nw = int(sys.argv[1])
    P = L.baseline(L.all_positions())
    want = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in P:
        if not p["trig_slot"]: continue
        idx = 0
        # trigger position in chain order: T2 trig idx / re-arm dump idx are in the arm record; we kept slot only -> use (slot, 0) for
        # 'strictly before the trigger slot' plus same-slot rows before it are unknown -> conservative: rows in slots < trigger slot
        fs = p["fill_slot"] or p["trig_slot"]
        want[zlib.crc32(p["mint"].encode()) % NB][p["mint"]].append((p["id"], p["trig_slot"], idx, fs, (fs + 6, 1 << 30)))
    want = {b: dict(v) for b, v in want.items()}
    res = {}
    with Pool(nw, initializer=init, initargs=(want,)) as pool:
        for o in pool.imap_unordered(job, range(NB)): res.update(o)
    pickle.dump(res, open(f"{L.D}/tokbots.pkl", "wb"))
    cov = collections.Counter((p["per"], (res.get(p["id"]) or {}).get("covered", False)) for p in P)
    print("positions", len(P), "coverage", sorted(cov.items()))
