#!/usr/bin/env python3
# How does HkQ7hMjy EXIT its dip backruns? For each round trip (its buy right after a >=1 SOL sell, then its next own sell):
# hold time, P&L, and what happened right before its sell (previous trade: buy/sell, size, delay), the price path during
# the hold (did it sell near the top?), and whether it sells right after the first sizeable follower buy. Local data only.
import sys, os, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
U = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * rp.SLOT_MS + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * rp.SLOT_MS
ms = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:10] == "HkQ7hMjy": ms.add(json.loads(l)[1])
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in ms: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    for m, tr in rp.read_bucket(run, b, byb[key]).items():
        mine = [k for k, t in enumerate(tr) if t["user"] == U]
        for k in mine:
            t = tr[k]
            if not t["buy"] or k == 0: continue
            pv = tr[k - 1]
            if pv["buy"] or pv["sol"] < 1e9: continue                      # dip backruns only
            ks = next((j for j in mine if j > k and not tr[j]["buy"]), None)
            if ks is None: continue
            x = tr[ks]; px = lambda z: z["vsol"] / z["vtok"]
            p_in = px(t); path = [px(z) for z in tr[k + 1:ks]]
            buys = [z for z in tr[k + 1:ks] if z["buy"] and z["user"] != U]
            fb = next((z for z in buys if z["sol"] >= 0.3e9), None)
            prev = tr[ks - 1]
            out.append(dict(m=m, hold=x["s"] - t["s"], ratio=x["sol"] / t["sol"] if t["sol"] else None, full=x["tok"] == t["tok"],
                            prev_buy=int(prev["buy"]), prev_sol=prev["sol"] / 1e9, prev_dt=round(arr(x) - arr(prev), 1), prev_same_slot=int(prev["s"] == x["s"]),
                            prev_is_entry=int(ks - 1 == k), n_buys=len(buys), buy_sol=sum(z["sol"] for z in buys) / 1e9,
                            peak=max(path) / p_in if path else 1.0, exit_px=px(prev) / p_in if ks - 1 > k else 1.0,
                            fb_slot=(fb["s"] - t["s"]) if fb else None, fb_to_exit_ms=round(arr(x) - arr(fb), 1) if fb else None))
    return out
if __name__ == "__main__":
    R = []
    with Pool(4) as p:
        for o in p.imap_unordered(work, sorted(byb)): R += o
    json.dump(R, open("/home/moiz/sniper/ops/overnight/census/hk_exits.json", "w"))
    n = len(R); full = [r for r in R if r["full"] and r["ratio"]]
    print(f"HkQ7hMjy dip round trips: {n} (full exits {len(full)}); median hold {statistics.median(r['hold'] for r in R)} slots; "
          f"hold p25/p75 {statistics.quantiles([r['hold'] for r in R], n=4)[0]:.0f}/{statistics.quantiles([r['hold'] for r in R], n=4)[2]:.0f}")
    print(f"  sell/buy SOL (full exits): median {statistics.median(r['ratio'] for r in full):.3f}, mean {statistics.mean(r['ratio'] for r in full):.3f}")
    print(f"  trade right before its sell: buy {sum(r['prev_buy'] for r in R) / n:.0%} (by someone else, not its own entry: {sum(1 for r in R if r['prev_buy'] and not r['prev_is_entry']) / n:.0%}); same slot {sum(r['prev_same_slot'] for r in R) / n:.0%}; "
          f"median delay after it {statistics.median(r['prev_dt'] for r in R):.1f} ms")
    pb = [r["prev_sol"] for r in R if r["prev_buy"] and not r["prev_is_entry"]]
    if pb: print(f"  size of that buy: median {statistics.median(pb):.3f} SOL, share >= 0.3 SOL {sum(1 for v in pb if v >= 0.3) / len(pb):.0%}")
    wf = [r for r in R if r["fb_slot"] is not None]
    print(f"  a >=0.3 SOL follower buy came during the hold: {len(wf) / n:.0%}; it came {statistics.median(r['fb_slot'] for r in wf)} slots after entry (median); "
          f"HkQ7 sold {statistics.median(r['fb_to_exit_ms'] for r in wf):.0f} ms after it (median); within 1 slot of it: {sum(1 for r in wf if r['fb_to_exit_ms'] <= 212) / len(wf):.0%}")
    print(f"  price at exit vs entry: median {statistics.median(r['exit_px'] for r in R):.3f}; peak during hold: median {statistics.median(r['peak'] for r in R):.3f}; "
          f"exit within 1% of the peak: {sum(1 for r in R if r['exit_px'] >= r['peak'] * 0.99) / n:.0%}")
    for lo, hi in ((0, 3), (3, 6), (6, 10), (10, 20), (20, 60), (60, 10 ** 6)):
        g = [r for r in full if lo <= r["hold"] < hi]
        if g: print(f"   hold {lo:2d}-{hi:<7d} slots: n {len(g):4d} median ratio {statistics.median(r['ratio'] for r in g):.3f} mean {statistics.mean(r['ratio'] for r in g):.3f}")
