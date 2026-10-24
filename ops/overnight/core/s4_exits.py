# S4 exit choice: S3 picks + 1% guard, all v2 exit rules at L45/L60/L75 (forward window, 0.5 SOL, fail 0.005 SOL)
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
from run_fwd2 import RULES, NAMES
exec(open("/home/moiz/sniper/ops/overnight/core/ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, bt=c["bt"], res={})
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            o = rp.sim(tr, c, st, ib, 0.5, RULES, fill_pen=0.015) if ok else None
            r["res"][Lm] = [o[n]["pnl"] for n in NAMES] if o else None
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    tab = []
    for i, n in enumerate(NAMES):
        row = []
        for Lm in (45, 60, 75):
            v = [(r["res"][Lm][i] if r["res"].get(Lm) else -0.005) for r in res if Lm in r["res"]]
            a = sum((r["res"][Lm][i] if r["res"].get(Lm) else -0.005) for r in res if Lm in r["res"] and r["bt"] < mid)
            row.append((sum(v), a, sum(v) - a))
        tab.append((row[2][0], n, row))
    tab.sort(reverse=True)
    json.dump([dict(rule=n, cells=[dict(L=Lm, tot=t, h1=a, h2=b) for Lm, (t, a, b) in zip((45, 60, 75), row)]) for _, n, row in tab], open("/home/moiz/sniper/ops/overnight/report/s4_exits.json", "w"))
    print("S4 (1% guard) exits ranked by L75 total; cells: total (half1/half2)")
    for _, n, row in tab[:18] + [t for t in tab if t[1].startswith(("lad", "p", "twap", "trail", "time"))][:12]:
        print(f"   {n:34} " + " | ".join(f"L{Lm} {t:+6.2f} ({a:+.1f}/{b:+.1f})" for Lm, (t, a, b) in zip((45, 60, 75), row)))
