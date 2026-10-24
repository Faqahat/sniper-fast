# DGmspi-style ladders on OUR S4 entries (1% guard, block-order placement) vs the single sell at the end of the next slot
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
FW = json.load(open("/home/moiz/sniper/ops/overnight/report/s4_forward.json"))
L = rp.load_launches(); O = rp.load_obs()
byb = collections.defaultdict(set)
for r in FW: byb[rp.bucket(r["mint"])].add(r["mint"])
LAD = {
  "single sell, end of next slot (S4)": dict(light_frac=1.0, light_slot=1, steps=[], twap_every=10 ** 6, twap_frac=0, twap_max_s=2),
  "WORLD copy: 25% @1, 8%/10%/10% of left @2/8/13, then 5% of left / 5 s, 6 min": dict(light_frac=.25, light_slot=1, steps=[(2, .08), (8, .10), (13, .10)], twap_every=24, twap_frac=.05, twap_max_s=384),
  "same + stop at 0.8x": dict(light_frac=.25, light_slot=1, steps=[(2, .08), (8, .10), (13, .10)], twap_every=24, twap_frac=.05, twap_max_s=384, stop_mult=0.8),
  "75% @1, then 5% of left / 5 s, 60 s, stop 0.85x": dict(light_frac=.75, light_slot=1, steps=[], twap_every=24, twap_frac=.05, twap_max_s=60, stop_mult=0.85),
  "75% @1, then 25% of left / 5 s, 30 s": dict(light_frac=.75, light_slot=1, steps=[], twap_every=24, twap_frac=.25, twap_max_s=30),
  "50% @1, then 10% of left / 5 s, 120 s, stop 0.85x": dict(light_frac=.5, light_slot=1, steps=[], twap_every=24, twap_frac=.10, twap_max_s=120, stop_mult=0.85),
  "70% @1, TP 40% of left @1.3x, 30% @1.5x, rest 60 s, stop 0.85x": dict(light_frac=.7, light_slot=1, steps=[], twap_every=10 ** 6, twap_frac=0, twap_max_s=60, stop_mult=0.85, tp=[(1.3, .4), (1.5, .3)]),
  "90% @1, rest rides 5% / 5 s, 6 min, stop 0.8x": dict(light_frac=.9, light_slot=1, steps=[], twap_every=24, twap_frac=.05, twap_max_s=384, stop_mult=0.8),
  "AEgZa5k3 copy: 10% of left / ~10 s, 70 s": dict(light_frac=.1, light_slot=59, steps=[], twap_every=48, twap_frac=.10, twap_max_s=70),
}
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, bt=c["bt"], res={})
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r["res"][Lm] = None; continue
            r["res"][Lm] = {k: rp.sim_dg(tr, c, st, ib, 0.5, **v) for k, v in LAD.items()}
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    print(f"S4 picks, 7.4 h, 0.5 SOL, failed guard -0.005; total SOL (halves), avg sells per fill")
    J = {}
    for k in LAD:
        cells = []
        for Lm in (45, 75):
            v = [(r["bt"], r["res"][Lm][k][0] if r["res"].get(Lm) else -0.005, r["res"][Lm][k][1] if r["res"].get(Lm) else 0) for r in res if Lm in r["res"]]
            tot = sum(x for _, x, _ in v); a = sum(x for t, x, _ in v if t < mid); ns = [n for _, _, n in v if n]
            cells.append(f"L{Lm} {tot:+6.2f} ({a:+.2f}/{tot - a:+.2f}) {sum(ns) / max(1, len(ns)):.1f} sells")
            J.setdefault(k, {})[Lm] = dict(tot=tot, h1=a, h2=tot - a, sells=sum(ns) / max(1, len(ns)))
        print(f"   {k:72} " + " | ".join(cells))
    json.dump(J, open("/home/moiz/sniper/ops/overnight/report/dg_ladders.json", "w"))
