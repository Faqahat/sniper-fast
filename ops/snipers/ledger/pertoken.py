#!/usr/bin/env python3
# READ-ONLY, offline: per-token results of a wallet (trading txs only, value = SOL + WSOL + stables), and where they come from.
import sys, json, collections, statistics, datetime
SOLUSD = 106.0; WSOL = "So11111111111111111111111111111111111111112"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
STABLE = {USDC, "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"}
D = json.load(open(sys.argv[1])); W = D["wallet"]
tok = collections.defaultdict(lambda: dict(pnl=0.0, buys=0, sells=0, spent=0.0, usdc=False, t0=None, t1=None))
for x in sorted([x for x in D["txs"] if not x.get("missing") and not x.get("err")], key=lambda x: x["slot"]):
    others = [m for m, d in x["tok"].items() if m != WSOL and m not in STABLE and abs(d) > 0]
    ms = {t["mint"] for t in x["trades"]} | set(others)
    if not ms: continue
    v = x["sol_chg"] + x["tok"].get(WSOL, 0) + sum(d for m, d in x["tok"].items() if m in STABLE) / SOLUSD
    for m in ms:
        r = tok[m]; r["pnl"] += v / len(ms)
        d = x["tok"].get(m, 0)
        if d > 0 or any(t["buy"] and t["mint"] == m for t in x["trades"]):
            r["buys"] += 1; r["spent"] += max(0, -v); r["t0"] = r["t0"] or x["bt"]; r["usdc"] |= x["tok"].get(USDC, 0) < -1
        elif d < 0 or any((not t["buy"]) and t["mint"] == m for t in x["trades"]):
            r["sells"] += 1; r["t1"] = x["bt"]
R = [dict(m=m, **r) for m, r in tok.items() if r["buys"] and r["sells"]]
tot = sum(r["pnl"] for r in R)
print(f"{W[:8]}: {len(R)} round-tripped tokens, trading result {tot:+.2f} SOL (before separate bot fees / failed txs); win {sum(r['pnl'] > 0 for r in R) / len(R):.0%}, median {statistics.median(r['pnl'] for r in R):+.4f}")
w = sorted(R, key=lambda r: -r["pnl"]); print(f"   10 best: {[round(r['pnl'], 2) for r in w[:10]]} = {sum(r['pnl'] for r in w[:10]):+.2f}; 10 worst: {[round(r['pnl'], 2) for r in w[-10:]]}")
def grp(name, fx):
    g = collections.defaultdict(list)
    for r in R: g[fx(r)].append(r["pnl"])
    print(f"   by {name}: " + " | ".join(f"{k}: {len(v)} tok {sum(v):+.2f} (med {statistics.median(v):+.3f})" for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))))
grp("quote", lambda r: "USDC" if r["usdc"] else "SOL")
grp("buy size", lambda r: "USDC" if r["usdc"] else ("<0.7" if r["spent"] < 0.7 else ("0.7-1.5" if r["spent"] < 1.5 else ("1.5-2.5" if r["spent"] < 2.5 else ("2.5-4" if r["spent"] < 4 else "4+")))))
grp("sells", lambda r: "1" if r["sells"] == 1 else ("2" if r["sells"] == 2 else ("3-5" if r["sells"] <= 5 else "6+")))
grp("hold", lambda r: "?" if not (r["t0"] and r["t1"]) else ("<=2s" if r["t1"] - r["t0"] <= 2 else ("3-10s" if r["t1"] - r["t0"] <= 10 else ("11-60s" if r["t1"] - r["t0"] <= 60 else ("1-10min" if r["t1"] - r["t0"] <= 600 else ">10min")))))
