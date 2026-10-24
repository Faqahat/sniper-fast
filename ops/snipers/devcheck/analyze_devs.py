#!/usr/bin/env python3
# READ-ONLY, offline: does a wallet follow a fixed set of devs? Splits its pump.fun buys into snipes (create slot or next) and later
# buys, and per group counts distinct creators, one-time creators, new creators per day, and the trading result per creator group.
import sys, json, collections, statistics, datetime
SOLUSD = 106.0; WSOL = "So11111111111111111111111111111111111111112"; STABLE = ("EPjF", "Es9v", "USD1")
D = json.load(open(sys.argv[1])); V = json.load(open(sys.argv[2])); W = D["wallet"]
tok = collections.defaultdict(lambda: dict(pnl=0.0, sells=0, spent=0.0, usdc=False))
for x in sorted([x for x in D["txs"] if not x.get("missing") and not x.get("err")], key=lambda x: x["slot"]):
    others = [m for m, d in x["tok"].items() if m != WSOL and not m.startswith(STABLE) and abs(d) > 0]
    ms = {t["mint"] for t in x["trades"]} | set(others)
    if not ms: continue
    v = x["sol_chg"] + x["tok"].get(WSOL, 0) + sum(d for m, d in x["tok"].items() if m.startswith(STABLE)) / SOLUSD
    for m in ms:
        r = tok[m]; r["pnl"] += v / len(ms)
        if x["tok"].get(m, 0) > 0 or any(t["buy"] and t["mint"] == m for t in x["trades"]):
            r["spent"] += max(0, -v); r["usdc"] |= any(x["tok"].get(s, 0) < -1 for s in x["tok"] if s.startswith(STABLE))
        else: r["sells"] += 1
R = []
for m, v in V.items():
    if not v["creator"]: continue
    t = tok.get(m, {}); d = v["delta"]
    R.append(dict(m=m, c=v["creator"], d=d, bt=v["bt"], nb=v["n_before_ok"], pnl=t.get("pnl", 0.0), spent=t.get("spent", 0.0), sells=t.get("sells", 0),
                  usdc=t.get("usdc", False), cls="snipe (create slot or next)" if d is not None and d <= 1 else "later buy"))
R.sort(key=lambda r: r["bt"] or 0)
dist = collections.Counter("0" if r["d"] == 0 else "1" if r["d"] == 1 else "2-10" if r["d"] is not None and r["d"] <= 10 else "11-150" if r["d"] is not None and r["d"] <= 150 else ">150 slots / >=1000 txs before" for r in R)
print(f"== {W[:8]}: {len(R)} pump.fun tokens with creator; buy slot minus create slot: " + ", ".join(f"{k}: {dist[k]}" for k in ["0", "1", "2-10", "11-150", ">150 slots / >=1000 txs before"]))
allc = collections.Counter(r["c"] for r in R)
for cls in ["snipe (create slot or next)", "later buy"]:
    G = [r for r in R if r["cls"] == cls]
    if not G: continue
    c = collections.Counter(r["c"] for r in G); n = len(G)
    seen = set(); per = collections.defaultdict(lambda: [0, 0])
    for r in G:
        day = datetime.datetime.fromtimestamp(r["bt"], datetime.timezone.utc).strftime("%m-%d"); per[day][0] += 1
        if r["c"] not in seen: per[day][1] += 1; seen.add(r["c"])
    rep = [r for r in G if allc[r["c"]] >= 3]; one = [r for r in G if allc[r["c"]] == 1]; mid = [r for r in G if allc[r["c"]] == 2]
    f = lambda L: f"{len(L)} tok {sum(r['pnl'] for r in L):+.2f} SOL (median {statistics.median([r['pnl'] for r in L]) if L else 0:+.3f}, win {sum(r['pnl'] > 0 for r in L) / max(1, len(L)):.0%})"
    print(f"   {cls}: {n} tokens from {len(c)} devs; devs bought once: {sum(1 for k in c.values() if k == 1)}; top 5 devs {sum(k for _, k in c.most_common(5)) / n:.0%}, top 10 {sum(k for _, k in c.most_common(10)) / n:.0%} of buys")
    print(f"      per day (buys / from a dev never bought before in this group): " + " | ".join(f"{d} {a}/{b}" for d, (a, b) in sorted(per.items())))
    print(f"      result by dev group (dev's buys over all 6 days): repeat dev (3+): {f(rep)} | 2 buys: {f(mid)} | one-time dev: {f(one)}")
    big = [r for r in G if r["spent"] >= 2.5 and not r["usdc"]]
    print(f"      big SOL buys (>= 2.5): {f(big)}; of them from repeat devs: {sum(1 for r in big if allc[r['c']] >= 3)}")
    print(f"      top devs: " + "; ".join(f"{k[:8]} {v} buys {sum(r['pnl'] for r in G if r['c'] == k):+.2f}" for k, v in c.most_common(8)))
