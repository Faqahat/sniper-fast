#!/usr/bin/env python3
# PumpSwap dip-backrun, first look (local collector data only; no RPC). For each successful pure-PumpSwap tx (AMM program,
# no bonding-curve program): find the pool from the token-balance changes (the owner whose token vault and WSOL vault move in
# opposite directions with the largest balances), its reserves before/after, and so the trade (direction, SOL, tokens).
# Per pool, in chain order: big sells (SOL out >= SMIN) are triggers; replay a buy of B SOL landing L ms after the sell
# (block-position proxy, as the bonding-curve replay), every later trade applied to the reserves (no follower limits: an
# UPPER bound), then sell all after H slots. AMM fee FEE per leg. Reports mean P&L by dump size, and the share positive.
# usage: python3 -I pumpswap_dips.py N_CHUNKS [STEP]
import sys, os, json, gzip, glob, collections, statistics
from multiprocessing import Pool
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
SMS = 212.0
B = 0.5e9; FEE = float(os.environ.get("FEE", "0.003")); SMIN = float(os.environ.get("SMIN", "2")) * 1e9
LATS = (0, 35, 50, 75); HS = (2, 4, 8)
def arr(s, i): return s * SMS + i / max(SS.get(s, 400), i + 1) * SMS
def trades(f):
    # the collector keeps token balances of the tracked mint only (tb) and every account's SOL change (sd). Pool token vault =
    # the tb owner with the largest balance; SOL leg = the pool's quote vault, i.e. the largest SOL outflow (sell) or inflow
    # (buy) among non-signers. Quote reserve q before the trade from the constant product: sell q = out*(b+db)/db, buy
    # q = in*(b-db)/db (fees ignored: a rough estimate).
    out = []
    try:
        for line in gzip.open(f, "rt"):
            if AMM not in line or '"err":null' not in line: continue
            r = json.loads(line); pg = r.get("progs") or []
            if AMM not in pg or PUMP in pg: continue
            tb = r.get("tb") or []
            if len(tb) < 2: continue
            vault = max(tb, key=lambda x: x[2])
            tok, owner, bp, ba = vault
            db = ba - bp
            if db == 0 or bp <= 0: continue
            signers = set(r.get("signers") or [])
            sd = [(a, v) for a, v in (r.get("sd") or []) if a not in signers]
            if not sd: continue
            if db > 0:          # tokens into the pool: a sell; the quote vault pays out
                a, v = min(sd, key=lambda x: x[1])
                if v >= 0: continue
                qo = -v; q = qo * (bp + db) // db; qa = q - qo
                out.append((owner, tok, r["s"], r["i"], False, qo, db, q, bp, qa, ba, next(iter(signers), "?")))
            else:               # tokens out of the pool: a buy; the quote vault takes SOL in
                a, v = max(sd, key=lambda x: x[1])
                if v <= 0: continue
                qi = v; q = qi * (bp + db) // (-db); qa = q + qi
                out.append((owner, tok, r["s"], r["i"], True, qi, -db, q, bp, qa, ba, next(iter(signers), "?")))
    except (EOFError, OSError): pass
    return out
def sim(series, k, L, H):
    # buy B (net of fee) at the reserves just before the first trade that arrives L ms after trigger k, then apply trades
    t = series[k]; a0 = arr(t[2], t[3])
    j = k + 1
    while j < len(series) and arr(series[j][2], series[j][3]) < a0 + L: j += 1
    q, bq = (series[j - 1][9], series[j - 1][10])          # reserves after the last trade ahead of us (quote, base)
    x = B * (1 - FEE); got = bq * x // (q + x); q += x; bq -= got
    s_in = series[j - 1][2]
    for u in series[j:]:
        if u[2] >= s_in + H: break
        if u[4]: q += u[5]; bq -= u[6]
        else: q -= u[5]; bq += u[6]
    out = q * got // (bq + got)
    return (out * (1 - FEE) - B) / 1e9
if __name__ == "__main__":
    n = int(sys.argv[1]); step = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261022_1543/txs/*.jsonl.gz"))[::step][:n]
    with Pool(6) as p: rows = [t for part in p.imap_unordered(trades, files) for t in part]
    pools = collections.defaultdict(list)
    for t in rows: pools[t[0]].append(t)
    for v in pools.values(): v.sort(key=lambda t: (t[2], t[3]))
    print(f"chunks {len(files)}: pool trades {len(rows)} in {len(pools)} pools", flush=True)
    R = collections.defaultdict(list)
    for v in pools.values():
        busy = -1
        for k, t in enumerate(v):
            if t[4] or t[5] < SMIN or t[2] <= busy or k + 1 >= len(v): continue
            busy = t[2] + 5
            size = "2-5" if t[5] < 5e9 else ("5-20" if t[5] < 20e9 else "20+")
            if os.environ.get("BY_DROP"):     # group by the dump's price drop instead of its SOL size
                drop = 1 - (t[9] / t[10]) / (t[7] / t[8])
                size = "drop<2%" if drop < 0.02 else ("drop2-5%" if drop < 0.05 else ("drop5-10%" if drop < 0.10 else "drop10%+"))
            for L in LATS:
                for H in HS: R[(size, L, H)].append(sim(v, k, L, H))
                R[("all", L, 2)].append(R[(size, L, 2)][-1])
    for key in sorted(R):
        v = R[key]
        if key[2] != 2 and key[0] != "all": continue
        print(f"  dump {key[0]:>4} SOL | land {key[1]:3d} ms | exit {key[2]} slots | n {len(v):6d} | mean {statistics.mean(v):+.5f} | total {sum(v):+8.2f} | win {sum(1 for x in v if x > 0) / len(v):.0%}")
