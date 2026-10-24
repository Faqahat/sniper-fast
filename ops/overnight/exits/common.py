#!/usr/bin/env python3
# READ-ONLY helpers shared by the exit study scripts (no network unless rpc.py is imported explicitly).
import os, json, base64, math, zlib, gzip, glob

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))

TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])           # pump.fun TradeEvent discriminator
K = 30_000_000_000 * 1_073_000_000_000_000                    # pump.fun curve invariant (lamports x raw token units), measured constant
WALLETS = {"9Sh2fd": "9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspi": "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3"}
LEDGER = "/home/moiz/sniper/ops/snipers/ledger"
EXITS = os.path.dirname(os.path.abspath(__file__))
WSOL = "So11111111111111111111111111111111111111112"
STABLE_PREFIX = ("EPjF", "Es9v", "USD1")
AKBOT_FEE = "AKbotZVF3zr9i4Cz2Lv34s6SydytjdidruoGTnvwPxFh"

def sol_link(sig): return f"https://solscan.io/tx/{sig}"
def gmgn_link(m): return f"https://gmgn.ai/sol/token/{m}"

def decode_events(tx):
    """All pump.fun TradeEvents in a getTransaction(jsonParsed) result, in log order."""
    out = []
    for l in (tx.get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != TD or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58(raw[57:89]), ts=u(89),
                        vsol=u(97), vtok=u(105), fee_bps=u(161), fee=u(169), creator=b58(raw[177:209]), cfee_bps=u(209), cfee=u(217)))
    return out

def pre_state(buy, sol, tok, vsol_after=None, vtok_after=None):
    """Curve state (vsol, vtok) just BEFORE a trade. Exact from the event's post-state when given, else rebuilt from
    (sol, tok) with the constant invariant K (checked against raw events: same to < 1e-6)."""
    if vsol_after is not None:
        return (vsol_after - sol, vtok_after + tok) if buy else (vsol_after + sol, vtok_after - tok)
    if sol <= 0 or tok <= 0: return None
    if buy: vs = (-sol + math.sqrt(sol * sol + 4.0 * K * sol / tok)) / 2.0
    else: vs = (sol * tok + math.sqrt((sol * tok) ** 2 + 4.0 * tok * sol * K)) / (2.0 * tok)
    return (vs, K / vs)

def post_state(buy, sol, tok, pre):
    vs, vt = pre
    return (vs + sol, vt - tok) if buy else (vs - sol, vt + tok)

def mc_sol(vsol, vtok):
    """Market cap in SOL (1e9 supply) from virtual reserves."""
    return vsol / vtok * 1e6

def curve_sell_out(tok, vsol, vtok):
    """Lamports out of the curve for selling `tok` raw units against state (vsol, vtok) (before the 1.25% pump fees)."""
    return vsol - K / (vtok + tok) if vtok + tok > 0 else 0.0

def curve_buy_out(sol, vsol, vtok):
    return vtok - K / (vsol + sol)

# ---------- collector market paths ----------
PHASE_DIRS = ["/home/moiz/sniper-data/collect/phaseA", "/home/moiz/sniper-data/collect/phaseA_fwd"]
LAUNCH_FILES = ["/home/moiz/sniper-data/collect/run_20261021_2207/launches.jsonl", "/home/moiz/sniper-data/collect/run_20261022_1543/launches.jsonl"]
def bucket(m): return zlib.crc32(m.encode()) % 256

def trades_of(m, dirs=PHASE_DIRS):
    """Every pump.fun TradeEvent of mint m from the collector (both runs), chain order (slot, idx, j). Same logic as
    ops/shadow/paper_live.py trades_of(); also returns X marker rows (non-trade txs touching the mint)."""
    tr = []; xs = []; seen = set()
    for d in dirs:
        for f in glob.glob(os.path.join(d, f"b{bucket(m):03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if m not in line: continue
                    r = json.loads(line)
                    if r[1] != m: continue
                    if r[0] == "X":
                        xs.append(dict(s=r[2], i=r[3], bt=r[4], sig=r[5], payer=r[6], ixn=r[13], tb=r[14], progs=r[15])); continue
                    (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                    if (sig, j) in seen: continue
                    seen.add((sig, j))
                    tr.append(dict(s=s, i=i, j=j, bt=bt, sig=sig, payer=payer, user=user, buy=buy == 1, sol=sol, tok=tok, vsol=vsol, vtok=vtok,
                                   fee=fee, tips=tips, err=err))
            except (EOFError, OSError, zlib.error): pass
    tr.sort(key=lambda t: (t["s"], t["i"], t["j"])); xs.sort(key=lambda t: (t["s"], t["i"]))
    return tr, xs

def load_launches(mints=None):
    L = {}
    for f in LAUNCH_FILES:
        if not os.path.exists(f): continue
        for line in open(f):
            try: r = json.loads(line)
            except Exception: continue
            if mints is None or r.get("mint") in mints: L[r["mint"]] = r
    return L
