#!/usr/bin/env python3
# READ-ONLY, offline: per-token results split by VENUE of the buy (pump.fun SOL curve / pump.fun with a USDC-PUMP-USD1 quote /
# Raydium LaunchLab (Stonk.fun-type launchpad) / AMM pools = older tokens), and by how many sells (cut losers vs ladders).
import sys, os, json, collections, statistics
SOLUSD = 106.0; WSOL = "So11111111111111111111111111111111111111112"; STABLE = ("EPjF", "Es9v", "USD1")
f, cachedir = sys.argv[1], sys.argv[2]
D = json.load(open(f)); W = D["wallet"]
V = {"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap", "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "launchlab",
     "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "swap", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "swap", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "swap",
     "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "amm", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "amm"}
def venue(sig):
    p = os.path.join(cachedir, sig + ".json")
    if not os.path.exists(p): return None
    t = json.load(open(p)); m = t["transaction"]["message"]
    progs = {ix.get("programId", "") for ix in m["instructions"]} | {ix.get("programId", "") for inn in (t["meta"].get("innerInstructions") or []) for ix in inn["instructions"]}
    v = {V[p] for p in progs if p in V}
    if "launchlab" in v: return "LaunchLab (Stonk.fun-type)"
    if "pump" in v and "swap" in v: return "pump.fun, USDC/PUMP-quoted"
    if "pump" in v: return "pump.fun, SOL-quoted"
    if "pumpswap" in v or "amm" in v or "swap" in v: return "AMM pool (older token)"
    return "other"
tok = collections.defaultdict(lambda: dict(pnl=0.0, sells=0, seg=None, spent=0.0))
for x in sorted([x for x in D["txs"] if not x.get("missing") and not x.get("err")], key=lambda x: x["slot"]):
    others = [m for m, d in x["tok"].items() if m != WSOL and not m.startswith(STABLE) and abs(d) > 0]
    ms = {t["mint"] for t in x["trades"]} | set(others)
    if not ms: continue
    v = x["sol_chg"] + x["tok"].get(WSOL, 0) + sum(d for m, d in x["tok"].items() if m.startswith(STABLE)) / SOLUSD
    for m in ms:
        r = tok[m]; r["pnl"] += v / len(ms)
        if x["tok"].get(m, 0) > 0 or any(t["buy"] and t["mint"] == m for t in x["trades"]):
            if r["seg"] is None: r["seg"] = venue(x["sig"]) or "unknown (not cached)"
            r["spent"] += max(0, -v)
        else: r["sells"] += 1
R = [r for r in tok.values() if r["seg"] and r["sells"]]
g = collections.defaultdict(list)
for r in R: g[r["seg"]].append(r)
print(f"== {W[:8]}: {len(R)} round-tripped tokens, {sum(r['pnl'] for r in R):+.2f} SOL before separate bot fees / failed txs")
for k, v in sorted(g.items(), key=lambda kv: -sum(r["pnl"] for r in kv[1])):
    big = [r for r in v if r["spent"] >= 2.5]; lad = [r for r in v if r["sells"] >= 6]
    print(f"   {k:30} {len(v):4} tokens {sum(r['pnl'] for r in v):+8.2f} SOL (median {statistics.median(r['pnl'] for r in v):+.3f}, win {sum(r['pnl'] > 0 for r in v) / len(v):.0%}) | "
          f"buys >= 2.5 SOL: {len(big)} -> {sum(r['pnl'] for r in big):+.2f} | 6+ sells: {len(lad)} -> {sum(r['pnl'] for r in lad):+.2f}")
