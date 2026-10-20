# READ-ONLY aggregation of tipsize.py output: does paying more put you earlier in the create slot?
# Position = txs after the creator's glued bundle (same block). Paid = priority fee + every tip (SOL).
# usage: python3 tipagg.py <tipsize json> [our wallets comma-separated]
import sys, json, statistics as st, collections

R = json.load(open(sys.argv[1]))
OURS = set((sys.argv[2] if len(sys.argv) > 2 else "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE,FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS").split(","))
BUCKETS = [(0, 0.002), (0.002, 0.01), (0.01, 0.03), (0.03, 0.1), (0.1, 0.3), (0.3, 99)]


def path(r):
    if not r["tips"]: return "prio-only"
    return max(r["tips"], key=lambda t: t[1])[0]


def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None


buys = []
for L in R:
    rows = [r for r in L["rows"] if r["ok"] and r["buy"] and r["wallet"] not in OURS]
    for n, r in enumerate(rows):
        buys.append(dict(r, rank=n + 1, lc=L.get("leader_client") or "?", mint=L["mint"], paid=r["prio"] + sum(t[1] for t in r["tips"]), path=path(r)))
print(f"launches {len(R)}, outside buys inside the create slot {len(buys)}")
print("\nPAID (prio + tips)       n   pos p25  median  p75   in first 20   first outside buyer")
for lo, hi in BUCKETS:
    b = [x for x in buys if lo <= x["paid"] < hi]
    if not b: continue
    pos = [x["pos"] for x in b]
    print(f"  {lo:5.3f}-{hi if hi < 99 else '':5}    {len(b):4} {q(pos, .25):8} {q(pos, .5):7} {q(pos, .75):5} {sum(1 for p in pos if p <= 20) / len(b):11.0%} {sum(1 for x in b if x['rank'] == 1) / len(b):14.0%}")

print("\nBY LEADER CLIENT x PATH (median position, n)")
by = collections.defaultdict(list)
for x in buys: by[(x["lc"], x["path"])].append(x["pos"])
for (lc, p), v in sorted(by.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
    if len(v) >= 3: print(f"  {lc:20} {p:12} n {len(v):4}  median +{q(v, .5)}  p25 +{q(v, .25)}  paid median {st.median([x['paid'] for x in buys if x['lc'] == lc and x['path'] == p]):.4f}")

print("\nFIRST OUTSIDE BUYER per launch (launches with >=1 outside buy in the create slot)")
firsts = [x for x in buys if x["rank"] == 1]
fp = [x["paid"] for x in firsts]
print(f"  n {len(firsts)}  paid p25 {q(fp, .25):.4f}  median {q(fp, .5):.4f}  p75 {q(fp, .75):.4f}  max {max(fp):.3f}; position median +{q([x['pos'] for x in firsts], .5)}")
w = collections.Counter(x["wallet"] for x in firsts)
print("  most frequent first buyers:")
for wal, c in w.most_common(10):
    xs = [x for x in firsts if x["wallet"] == wal]
    print(f"    {wal[:8]}  first {c:3}x  median pos +{q([x['pos'] for x in xs], .5):<4} paid median {st.median([x['paid'] for x in xs]):.4f}  paths {collections.Counter(x['path'] for x in xs).most_common(2)}")
allw = collections.Counter(x["wallet"] for x in buys)
print("\nMOST ACTIVE create-slot buyers (any rank):")
for wal, c in allw.most_common(12):
    xs = [x for x in buys if x["wallet"] == wal]
    print(f"    {wal[:8]}  buys {c:3}  median pos +{q([x['pos'] for x in xs], .5):<4} first {sum(1 for x in xs if x['rank'] == 1):3}  paid median {st.median([x['paid'] for x in xs]):.4f}  size median {st.median([x['sol'] for x in xs]):.2f}  paths {collections.Counter(x['path'] for x in xs).most_common(2)}")
