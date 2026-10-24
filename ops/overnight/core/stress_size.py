# stress for the size-up variant: S4 picks (forward window, 75 ms, block-order placement, 1% guard, eos1 exit) at 0.5 and
# 1.0 SOL when the case-study wallets' later buys fail (drop9) and when also 30% of other early buyers vanish (drop30)
import sys, json, collections, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
FW = json.load(open("/home/moiz/sniper/ops/overnight/report/s4_forward.json"))
L = rp.load_launches(); O = rp.load_obs()
CASE = {"9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"}
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
byb = collections.defaultdict(set)
for r in FW: byb[rp.bucket(r["mint"])].add(r["mint"])
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}; rnd = random.Random(b)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], 75, fa.get(m, []))
        if ib < 1: continue
        if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: out[m] = None; continue
        t0 = tr[ib - 1]["s"]; r = {}
        for var in ("base", "drop9", "drop30"):
            if var == "base": path = tr
            elif var == "drop9": path = tr[:ib] + [t for t in tr[ib:] if not (t["buy"] and t["user"] in CASE)]
            else: path = tr[:ib] + [t for t in tr[ib:] if not (t["buy"] and (t["user"] in CASE or ((t["s"] - t0) <= 5 and t["user"] not in st["insiders"] and rnd.random() < 0.3)))]
            for B in (0.5, 1.0):
                o = rp.sim(path, c, st, ib, B, EX, fill_pen=0.015); r[f"{var}_{B}"] = o["eos1"]["pnl"] if o else 0
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    fills = {m: v for m, v in res.items() if v}
    nf = len(res) - len(fills)
    print(f"S4 at 75 ms: {len(res)} attempts, {len(fills)} fills, {nf} guard fails (-0.005 each)")
    for var in ("base", "drop9", "drop30"):
        print(f"   {var:7} 0.5 SOL: {sum(v[f'{var}_0.5'] for v in fills.values()) - 0.005 * nf:+.2f} | 1.0 SOL: {sum(v[f'{var}_1.0'] for v in fills.values()) - 0.005 * nf:+.2f}")
