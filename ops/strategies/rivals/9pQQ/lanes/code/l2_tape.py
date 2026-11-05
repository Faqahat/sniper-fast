#!/usr/bin/env python3
"""LANES step 2: per raw gz file ->
  tape npz: a int64 [n,14] = s, i, bt, uid, mid, tok, sol, cpre, cpost, cup, tip, fl, pset, ntips   (landed curve/AMM trades, all signers)
            f int64 [k,8]  = s, i, uid, mid, side(1 buy/-1 sell/0), custom err code, cup, tip    (FAILED pump.fun txs)
            users, mints, psets (string tables, per file)
  own lines: raw JSON of every tx whose first signer is 9pQQ -> own/<file>.jsonl
Read-only on the recordings. usage: l2_tape.py RUNDIR ... (3 workers)"""
import sys, os, gzip, json, re
from multiprocessing import Pool
import numpy as np
CURVE = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
OUT = "/home/moiz/sniper-data/rivals/9pQQ/lanes/tape"
SKIP = {"11111111", "ComputeB", "ATokenGP", "TokenkegQ", "Tokenz", "6EF8rrec", "pfeeUxB6", "pAMMBay6", "MemoSq4g", "So111111", "TokenzQd", "Tokenkeg"}
rx = re.compile(r'"Custom":(\d+)')
def job(a):
    src, dst, odst = a
    if os.path.exists(dst): return -1
    U, M, P, rows, frows, own = {}, {}, {}, [], [], []
    with gzip.open(src, "rt", errors="replace") as f:
        try:
            for l in f:
                if W in l:
                    d0 = json.loads(l)
                    if (d0.get("signers") or [None])[0] == W: own.append(l)
                if '"err":null' not in l:
                    if CURVE not in l: continue
                    d = json.loads(l)
                    if d.get("err") is None: continue
                    sg = (d.get("signers") or [None])[0]; ms = d.get("mints") or []
                    if not ms: continue
                    ix = d.get("ixn") or []
                    side = 1 if any(x.startswith("Buy") for x in ix) else (-1 if any(x.startswith("Sell") for x in ix) else 0)
                    m_ = rx.search(json.dumps(d["err"])); code = int(m_.group(1)) if m_ else -1
                    tip = sum(v for _, v in (d.get("tips") or []))
                    frows.append((d["s"], d.get("i") or 0, U.setdefault(sg, len(U)), M.setdefault(ms[0], len(M)), side, code, d.get("cup") or 0, tip))
                    continue
                d = json.loads(l)
                tb = d.get("tb")
                if not tb: continue
                sg = (d.get("signers") or [None])[0]
                sd = d.get("sd") or []
                sol = next((v for a_, v in sd if a_ == sg), 0)
                tps = d.get("tips") or []
                tip = sum(v for _, v in tps)
                pg = d.get("progs") or []
                fl = (1 if CURVE in pg else 0) | (2 if AMM in pg else 0)
                if not fl: continue
                ps = ",".join(sorted(set(p[:8] for p in pg if p[:8] not in SKIP)))
                pid = P.setdefault(ps, len(P))
                for m in d.get("mints") or []:
                    tok, cur = 0, None
                    for mm, ow, pre, post in tb:
                        if mm != m: continue
                        if ow == sg: tok += (post or 0) - (pre or 0)
                        elif cur is None or (pre or 0) > cur[0]: cur = (pre or 0, post or 0)
                    if tok == 0 or cur is None: continue
                    rows.append((d["s"], d.get("i") or 0, d.get("bt") or 0, U.setdefault(sg, len(U)), M.setdefault(m, len(M)),
                                 tok, sol, cur[0], cur[1], d.get("cup") or 0, tip, fl, pid, len(tps)))
        except (EOFError, OSError): pass
    np.savez(dst + ".tmp.npz", a=np.array(rows, dtype=np.int64).reshape(-1, 14), f=np.array(frows, dtype=np.int64).reshape(-1, 8),
             users=np.array(list(U), dtype="U44"), mints=np.array(list(M), dtype="U44"), psets=np.array(list(P), dtype="U200"))
    with open(odst, "w") as fo: fo.writelines(own)
    os.rename(dst + ".tmp.npz", dst)
    return len(rows)
if __name__ == "__main__":
    jobs = []
    for rd in sys.argv[1:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{OUT}/{r}/own", exist_ok=True)
        for fn in sorted(os.listdir(f"{rd}/txs")):
            jobs.append((f"{rd}/txs/{fn}", f"{OUT}/{r}/{fn[:-9]}.npz", f"{OUT}/{r}/own/{fn[:-9]}.jsonl"))
    tot = 0
    with Pool(3) as p:
        for k, n in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 50 == 0: print(k, len(jobs), tot, flush=True)
    print("done", len(jobs), tot, flush=True)
