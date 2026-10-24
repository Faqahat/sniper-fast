# STRESS TESTS for S4 (S3 list + 1% price guard, sell lands 500 ms after the create), forward window, 0.5 SOL:
#  imputed  : unseen competitor buys get imputed arrival times (conservative placement)
#  shift+1/2: 1 or 2 more outside trades land ahead of us than the model says (guard re-checked at the new place)
#  drop9    : the case-study wallets' buys after ours are removed (they fail on slippage because of our buy)
#  drop30   : additionally 30% of all outside buys in the first second after ours are removed (random, seed fixed)
#  late sell: our sell lands at 800 ms instead of 500 ms
import sys, json, collections, statistics, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
exec(open("/home/moiz/sniper/ops/overnight/core/ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
CASE = {"9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"}
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
G = 0.01; FAIL = 0.002
def run_one(tr, c, st, ib, p_b, sell_ms, outs):
    if ib < 1 or ib > len(tr): return None
    if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1 + G: return -FAIL
    return rp.flip(tr, ib, rp.place_ms(tr, c, st, outs, sell_ms, ib), 0.5)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = []
    rnd = random.Random(b)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; outs = O[m]["outs"]; r = dict(m=m, bt=c["bt"], res={})
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, outs, Lm, fa.get(m, []))
            r["res"][f"base_{Lm}"] = run_one(tr, c, st, ib, p_b, 500, outs)
            r["res"][f"imputed_{Lm}"] = run_one(tr, c, st, rp.place_imputed(tr, c, st, outs, Lm)[0], p_b, 500, outs)
            r["res"][f"shift1_{Lm}"] = run_one(tr, c, st, rp.shift(tr, c, st, ib, 1), p_b, 500, outs)
            r["res"][f"shift2_{Lm}"] = run_one(tr, c, st, rp.shift(tr, c, st, ib, 2), p_b, 500, outs)
            r["res"][f"sell800_{Lm}"] = run_one(tr, c, st, ib, p_b, 800, outs)
            # drop variants: rebuild the path after our buy without the dropped buys
            S = c["slot"]
            t0 = tr[ib - 1]["s"] if ib >= 1 else S
            keep9 = tr[:ib] + [t for t in tr[ib:] if not (t["buy"] and t["user"] in CASE)]
            r["res"][f"drop9_{Lm}"] = run_one(keep9, c, st, ib, p_b, 500, outs)
            keep30 = tr[:ib] + [t for t in tr[ib:] if not (t["buy"] and (t["user"] in CASE or ((t["s"] - t0) <= 5 and t["user"] not in st["insiders"] and rnd.random() < 0.3)))]
            r["res"][f"drop30_{Lm}"] = run_one(keep30, c, st, ib, p_b, 500, outs)
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    json.dump(res, open("/home/moiz/sniper/ops/overnight/report/stress_s4.json", "w"))
    print(f"S4 stress tests, {len(res)} S3 launches, 0.5 SOL, guard 1%, fail 0.002 SOL")
    for var in ("base", "imputed", "shift1", "shift2", "sell800", "drop9", "drop30"):
        cells = []
        for Lm in (45, 60, 75):
            k = f"{var}_{Lm}"; v = [r["res"][k] for r in res if r["res"].get(k) is not None]
            a = sum(r["res"][k] for r in res if r["res"].get(k) is not None and r["bt"] < mid)
            nf = sum(1 for x in v if x != -FAIL)
            cells.append(f"L{Lm} {sum(v):+6.2f} ({a:+.1f}/{sum(v) - a:+.1f}) fills {nf}")
        print(f"   {var:8} " + " | ".join(cells))
