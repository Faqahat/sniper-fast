# Wallet reputation from the census (bonding-curve PnL per wallet-mint): from R1 only (used to make R2 features) and from R1+R2 (for R3).
import gzip, glob, json, collections, pickle
HRS = {"R1": 14.88, "R2": 21.79, "R3": 24.0}
S = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0]))
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        r = json.loads(line)
        if r[16] or not r[13]: continue
        s = S[r[0]][r[2]]; s[0] += 1; s[1] += r[11]; s[2] += r[11] > 0
def rep(runs):
    out = {}
    for u, d in S.items():
        n = sum(d[r][0] for r in runs if r in d)
        if n < 10: continue
        pnl = sum(d[r][1] for r in runs if r in d); win = sum(d[r][2] for r in runs if r in d) / n
        out[u] = (pnl / sum(HRS[r] for r in runs) * 24, win, n)
    return out
R = {"for_R2": rep(["R1"]), "for_R3": rep(["R1", "R2"])}
pickle.dump(R, open("rep.pkl", "wb"))
for k, v in R.items(): print(k, "wallets with >= 10 closed positions:", len(v), "| winners (>= +2 SOL/day, win >= 50%):", sum(1 for x in v.values() if x[0] >= 2 and x[1] >= 0.5))
