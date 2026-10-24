# OLD DATA (R1) check of the price guard on S3 picks: block-position landing proxy (pessimistic at 60-75 ms), eos1 exit
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
exec(open("run_r1.py").read().split("R = rp.R")[0])
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("eos2", [(1.0, ("slot", 2))], 5), rp.R("hold1s", [(1.0, ("t", 1))], 2)]
byb = collections.defaultdict(set)
for m in pick: byb[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R1", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, bt=c["bt"], res={})
        for Lm in (35, 45, 60, 75):
            ib, _ = rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015)
            if o: r["res"][Lm] = ((tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b, {k: o[k]["pnl"] for k in o})
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    json.dump(res, open("/home/moiz/sniper/ops/overnight/report/r1_guard.json", "w"))
    print(f"R1 old data, S3 picks {len(res)} ({(res[-1]['bt'] - res[0]['bt']) / 3600:.1f} h), failed buy costs 0.002 SOL")
    for ex in ("eos1", "eos2", "hold1s"):
        for G in (None, 0.01, 0.03, 0.06):
            cells = []
            for Lm in (35, 45, 60, 75):
                tot = a = 0.0; nf = 0
                for r in res:
                    if Lm not in r["res"]: continue
                    ratio, pn = r["res"][Lm]
                    ok = G is None or ratio <= 1 + G; v = pn[ex] if ok else -0.002
                    tot += v; nf += ok; a += v if r["bt"] < mid else 0
                cells.append(f"L{Lm} {tot:+6.2f} ({a:+.1f}/{tot - a:+.1f}) n{nf}")
            print(f"   {ex:6} guard {'none' if G is None else f'{G:.0%}':>4}: " + " | ".join(cells))
