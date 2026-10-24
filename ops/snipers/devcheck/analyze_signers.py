#!/usr/bin/env python3
# READ-ONLY, offline: "does the wallet follow a specific set of devs?" with dev = the wallet that SIGNED the create
# (pump.fun lets the signer put any other wallet in the creator field). Uses bought tokens and, if given, failed attempts.
# usage: analyze_signers.py <ledger.json> <devs.json> [att.json]
import sys, json, collections, statistics, datetime
SOLUSD = 106.0; WSOL = "So11111111111111111111111111111111111111112"; STABLE = ("EPjF", "Es9v", "USD1")
D = json.load(open(sys.argv[1])); V = json.load(open(sys.argv[2])); A = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}; W = D["wallet"]
tok = collections.defaultdict(lambda: dict(pnl=0.0, sells=0, spent=0.0, usdc=False))
for x in sorted([x for x in D["txs"] if not x.get("missing") and not x.get("err")], key=lambda x: x["slot"]):
    others = [m for m, d in x["tok"].items() if m != WSOL and not m.startswith(STABLE) and abs(d) > 0]
    ms = {t["mint"] for t in x.get("trades") or []} | set(others)
    if not ms: continue
    v = x["sol_chg"] + x["tok"].get(WSOL, 0) + sum(d for m, d in x["tok"].items() if m.startswith(STABLE)) / SOLUSD
    for m in ms:
        r = tok[m]; r["pnl"] += v / len(ms)
        if x["tok"].get(m, 0) > 0 or any(t["buy"] and t["mint"] == m for t in x.get("trades") or []):
            r["spent"] += max(0, -v); r["usdc"] |= any(x["tok"].get(s, 0) < -1 for s in x["tok"] if s.startswith(STABLE))
        else: r["sells"] += 1
day = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d")
R = []; import os; MS = int(os.environ.get("MIN_SLOT", "0"))
for src, S in (("bought", V), ("failed", A)):
    for m, v in S.items():
        if v["buy_slot"] <= MS: continue
        dev = v.get("signer") or v.get("creator")
        if not dev: continue
        t = tok.get(m, {}) if src == "bought" else {}
        R.append(dict(m=m, src=src, dev=dev, cf=v.get("creator_field"), d=v["delta"], bt=v["bt"], pnl=t.get("pnl", 0.0), spent=t.get("spent", 0.0), usdc=t.get("usdc", False)))
R.sort(key=lambda r: r["bt"] or 0)
B = [r for r in R if r["src"] == "bought"]; snipe = lambda r: r["d"] is not None and r["d"] <= 1
print(f"== {W[:8]}: bought {len(B)} pump.fun tokens ({sum(map(snipe, B))} snipes = create slot or next)" + (f"; failed attempts on {len(R) - len(B)} more launches ({sum(1 for r in R if r['src'] == 'failed' and snipe(r))} snipe-time)" if A else ""))
mis = [r for r in B if r["cf"] and r["cf"] != r["dev"]]
print(f"   create signer != creator field on {len(mis)} of {len(B)} bought launches ({len(mis) / max(1, len(B)):.0%})")
def block(name, G, allc):
    if not G: return
    c = collections.Counter(r["dev"] for r in G); n = len(G)
    seen = set(); per = collections.defaultdict(lambda: [0, 0])
    for r in G:
        d = day(r["bt"]); per[d][0] += 1
        if r["dev"] not in seen: per[d][1] += 1; seen.add(r["dev"])
    print(f"   {name}: {n} launches from {len(c)} signers; signers seen once: {sum(1 for k in c.values() if k == 1)}; top 5 = {sum(k for _, k in c.most_common(5)) / n:.0%}, top 10 = {sum(k for _, k in c.most_common(10)) / n:.0%}, top 20 = {sum(k for _, k in c.most_common(20)) / n:.0%}")
    print(f"      per day, launches / from a signer never seen before: " + " | ".join(f"{d} {a}/{b}" for d, (a, b) in sorted(per.items())))
    return c
Sn = [r for r in R if snipe(r)]
allc = collections.Counter(r["dev"] for r in Sn)
block("BOUGHT snipes", [r for r in Sn if r["src"] == "bought"], allc)
if A: block("ALL snipe ATTEMPTS (bought + failed)", Sn, allc)
G = [r for r in Sn if r["src"] == "bought"]
f = lambda L: f"{len(L)} tok {sum(r['pnl'] for r in L):+.2f} SOL (median {statistics.median([r['pnl'] for r in L]) if L else 0:+.3f}, win {sum(r['pnl'] > 0 for r in L) / max(1, len(L)):.0%})"
print(f"   result of bought snipes by how often the signer shows up in attempts: 10+: {f([r for r in G if allc[r['dev']] >= 10])} | 3-9: {f([r for r in G if 3 <= allc[r['dev']] < 10])} | 1-2: {f([r for r in G if allc[r['dev']] < 3])}")
big = [r for r in G if r["spent"] >= 2.5 and not r["usdc"]]
print(f"   big SOL buys (>= 2.5 SOL): {f(big)}; from signers with 10+ attempts: {sum(1 for r in big if allc[r['dev']] >= 10)}, 3-9: {sum(1 for r in big if 3 <= allc[r['dev']] < 10)}, 1-2: {sum(1 for r in big if allc[r['dev']] < 3)}")
top = allc.most_common(15)
print("   top signers (attempts, bought, result):")
for k, v in top:
    b = [r for r in G if r["dev"] == k]
    print(f"      {k}  attempts {v:4}  bought {len(b):3}  {sum(r['pnl'] for r in b):+.2f} SOL")
json.dump(dict(top=top, n=len(Sn)), open(f"sig_summary_{W[:6]}.json", "w"))
