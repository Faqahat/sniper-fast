#!/usr/bin/env python3
# Same dumps where we AND a dip pro bought: block-time ms after the dump for our buy and the best pro's, with REAL block sizes
# (public RPC getBlock signatures, ~1 req/s; never the engine's key). ms = (buy slot - dump slot) x 212.6 + (i_buy / size_buyslot - i_dump / size_dumpslot) x 212.6
import json, collections, urllib.request, time, statistics
R = json.load(open("race_buys.json")); EP = "https://api.mainnet-beta.solana.com"; SL = 212.6; NONCE_T = 1792869120
g = collections.defaultdict(list)
for x in R: g[(x["s0"], x["dump_i"], x["cl"])].append(x)
cases = [(k, [x for x in v if x["who"] == "ours"], [x for x in v if x["who"] == "pro"]) for k, v in g.items()]
cases = [c for c in cases if c[1] and c[2]]
sz = {}
def size(s):
    if s in sz: return sz[s]
    for k in range(5):
        try:
            req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": [s, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 0, "rewards": False}]}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=60)); time.sleep(1.1)
            if r.get("result"): sz[s] = len(r["result"]["signatures"]); return sz[s]
            time.sleep(4)
        except Exception: time.sleep(4)
    sz[s] = None; return None
res = []
for (s0, di, cl), o, p in cases:
    n0 = size(s0)
    if not n0: continue
    def ms(x):
        n = n0 if x["bs"] == s0 else size(x["bs"])
        return None if not n else (x["bs"] - s0) * SL + (x["bi"] / n - di / n0) * SL
    om = [m for m in map(ms, o) if m is not None]; pm = [m for m in map(ms, p) if m is not None]
    if om and pm: res.append(dict(cl=cl, era="nonce" if o[0]["bt"] and o[0]["bt"] >= NONCE_T else "multi", ours=min(om), pro=min(pm), dump_frac=di / n0))
json.dump(res, open("blockms.json", "w"))
med = lambda v: round(statistics.median(v), 1) if v else None
print(f"same dumps with real block sizes: {len(res)} (blocks fetched {len(sz)})")
for cl in sorted({r["cl"] for r in res}):
    for era in ("multi", "nonce"):
        v = [r for r in res if r["cl"] == cl and r["era"] == era]
        if len(v) < 3: continue
        print(f"  {cl:20s} {era:6s} n={len(v):3d} | ours median {med([r['ours'] for r in v])} ms | best pro {med([r['pro'] for r in v])} ms | ours-pro {med([r['ours']-r['pro'] for r in v])} ms")
a = [r for r in res]
print(f"  ALL n={len(a)} | ours {med([r['ours'] for r in a])} ms | best pro {med([r['pro'] for r in a])} ms | best pro under 30 ms on {sum(1 for r in a if r['pro'] < 30)/len(a):.0%} of dumps, ours {sum(1 for r in a if r['ours'] < 30)/len(a):.0%}")
