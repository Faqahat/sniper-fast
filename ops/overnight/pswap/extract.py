#!/usr/bin/env python3
# PumpSwap (post-graduation AMM) trade tapes from the raw recordings (read-only). Per successful tx that calls the PumpSwap program and moves
# one tracked mint: signer, side, base amount, quote (SOL) amount into/out of the pool vault, pool base reserve before (from token balances),
# and the implied pool quote reserve before (constant product solved from the trade). One output pickle per input file.
import sys, os, json, gzip, pickle, glob
from multiprocessing import Pool
PS = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
def one(f):
    out = os.path.join("parts", os.path.basename(os.path.dirname(os.path.dirname(f))) + "_" + os.path.basename(f).replace(".jsonl.gz", ".pkl"))
    if os.path.exists(out): return 0
    rows = []
    try:
        for line in gzip.open(f, "rt"):
            if PS not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            if str(r.get("err")) not in ("None", "null") or PS not in (r.get("progs") or []): continue
            sg = (r.get("signers") or [None])[0]; tb = r.get("tb") or []; sd = r.get("sd") or []
            mints = r.get("mints") or []
            if len(mints) != 1: continue
            m = mints[0]
            ub = [x for x in tb if x[0] == m and x[1] == sg]; pb = [x for x in tb if x[0] == m and x[1] != sg]
            if not ub or not pb: continue
            du = ub[0][3] - ub[0][2]
            pool = max(pb, key=lambda x: abs(x[3] - x[2])); dp = pool[3] - pool[2]
            if du == 0 or dp == 0 or (du > 0) == (dp > 0): continue
            buy = du > 0
            us = sum(d for a, d in sd if a == sg)
            other = [(a, d) for a, d in sd if a != sg]
            if not other: continue
            vault = max(other, key=lambda x: x[1]) if buy else min(other, key=lambda x: x[1])
            q = abs(vault[1]); base = abs(dp); Bpre = pool[2]
            if q == 0 or base == 0 or Bpre <= 0: continue
            Qpre = q * (Bpre - base) / base if buy else q * (Bpre + base) / base
            rows.append(dict(s=int(r["s"]), i=int(r["i"]), bt=int(r.get("bt") or 0), sig=r["sig"], m=m, user=sg, buy=buy, base=base, q=q, user_sol=us,
                             Bpre=Bpre, Qpre=Qpre, pool_owner=pool[1], ixn=(r.get("ixn") or [])[:4], cup=r.get("cup"), tips=r.get("tips")))
    except (EOFError, OSError): pass
    pickle.dump(rows, open(out, "wb")); return len(rows)
if __name__ == "__main__":
    os.makedirs("parts", exist_ok=True)
    files = []
    for run in sys.argv[1:]: files += sorted(glob.glob(f"/home/moiz/sniper-data/collect/{run}/txs/*.jsonl.gz"))
    n = 0
    with Pool(8) as p:
        for x in p.imap_unordered(one, files): n += x
    print("PumpSwap trades extracted:", n)
