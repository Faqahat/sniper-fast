# Leader search: wallets that buy the same token shortly BEFORE the group (0.3–120 s), across the group's tokens. Lift = how much more often
# the wallet appears just before the group than its general presence on these tokens predicts. Also the lag distribution for top candidates.
import pickle, gzip, collections, statistics, json
D = pickle.load(gzip.open("../g3/g3.pkl.gz", "rb")); T = D["tapes"]
G = set(l.strip() for l in open("../g3/grp.txt") if l.strip())
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 0), t["i"] + 1, 380) * 212.0
pre = collections.Counter(); lag = collections.defaultdict(list); anyw = collections.Counter(); n = 0
for m, tr in T.items():
    k0 = next((k for k, t in enumerate(tr) if t["user"] in G and t["buy"]), None)
    if k0 is None: continue
    n += 1; t0 = ms(tr[k0])
    seen = set()
    for t in tr[:k0]:
        if t["buy"] and t["user"] not in G and 300 <= t0 - ms(t) <= 120_000 and t["user"] not in seen:
            seen.add(t["user"]); pre[t["user"]] += 1; lag[t["user"]].append((t0 - ms(t)) / 1000)
    for u in {t["user"] for t in tr if t["buy"]}: anyw[u] += 1
print(f"group tokens: {n}")
print("wallet                                         before-group  on-token-at-all  lift   lag median (s)")
for u, c in sorted(pre.items(), key=lambda kv: -kv[1])[:20]:
    print(f"  {u}  {c:3d} ({c/n:4.0%})   {anyw[u]:3d}            {c/anyw[u]:4.2f}   {statistics.median(lag[u]):6.1f}")
