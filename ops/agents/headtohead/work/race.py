# race reconstruction around a dump (read-only)
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/agents/headtohead/work")
from lib import *
STD_PROGS = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
             "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", PUMP}
SHORT = {"L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95": "L2TE", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pAMM",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "JUP6", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ": "pfee"}
def pshort(progs): return ",".join(SHORT.get(p, p[:4]) for p in progs if p not in STD_PROGS)
def is_buy_attempt(r, mint):
    """True if tx is a (successful or failed) buy attempt on mint"""
    if any(t["mint"] == mint and t["buy"] for t in r["tr"]): return True
    if r["ec"]:
        ix = " ".join(r.get("ixn") or [])
        if "Buy" in ix or "buy" in ix: return True
    return False
def race(txs, dump_sig, sol_in, min_out, horizon=5):
    """txs: all records of the mint sorted by (s,i). Returns dict with dump, sequence rows after the dump (up to S+horizon)."""
    k0 = next((k for k, r in enumerate(txs) if r["sig"] == dump_sig), None)
    if k0 is None: return None
    D = txs[k0]
    dt = [t for t in D["tr"] if not t["buy"]]
    if not dt: return None
    mint = dt[0]["mint"]
    dtr = [t for t in D["tr"] if t["mint"] == mint][-1]
    V, T = dtr["vsol"], dtr["vtok"]
    p0 = V / T
    S = D["s"]
    rows = []; crossed = None
    for r in txs[k0 + 1:]:
        if r["s"] > S + horizon: break
        trs = [t for t in r["tr"] if t["mint"] == mint]
        pre_ok = tokens_out(V, T, sol_in) >= min_out
        for t in trs: V, T = t["vsol"], t["vtok"]
        post_ok = tokens_out(V, T, sol_in) >= min_out
        row = dict(r=r, trs=trs, pre_ok=pre_ok, post_ok=post_ok, pmult=(V / T) / p0)
        if crossed is None and pre_ok and not post_ok: crossed = len(rows)
        rows.append(row)
    return dict(D=D, S=S, iD=D["i"], p0=p0, rows=rows, crossed=crossed, mint=mint)
