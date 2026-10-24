# guarded quick flip (1% guard, hold ~1 s) on the forward window for different deployer-list sources (walk-forward)
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
SRC = {"9S+DG": json.load(open("attempts.json")), "AHW": json.load(open("attempts_ahw.json"))}
def wf_lists(att, wallets, rate=0.10, k=2):
    ev = []
    for m, c in L.items():
        if not c.get("bt"): continue
        ev.append((c["bt"], c["user"], 0))
        if any(w in att.get(m, {}) for w in wallets): ev.append((c["bt"], c["user"], 1))
    ev.sort(); na = collections.Counter(); nl = collections.Counter(); j = 0; keep = {}
    for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt") and c["run"] == "R2"):
        while j < len(ev) and ev[j][0] < bt:
            _, d, a = ev[j]; (na if a else nl)[d] += 1; j += 1
        d = L[m]["user"]
        keep[m] = na[d] >= k and (nl[d] == 0 or na[d] / nl[d] >= rate)
    return keep
SEL = {"S4: 9Sh2fd+DGmspi list": wf_lists(SRC["9S+DG"], ("9Sh2fd", "DGmspi")), "AHwJSnFN list": wf_lists(SRC["AHW"], ("AHwJSn",)),
       "AHwJSnFN list (rate>=30%)": wf_lists(SRC["AHW"], ("AHwJSn",), rate=0.3)}
SEL["union"] = {m: SEL["S4: 9Sh2fd+DGmspi list"].get(m, False) or SEL["AHwJSnFN list"].get(m, False) for m in SEL["AHwJSnFN list"]}
SEL["ORACLE AHwJSnFN attempts"] = {m: "AHwJSn" in SRC["AHW"].get(m, {}) for m in L}
ALL = {m for s in SEL.values() for m, v in s.items() if v}
fw = [m for m in ALL if m in O and m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
EX = [rp.R("hold1s", [(1.0, ("t", 1))], 2)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[Lm] = -0.005
            else:
                o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015); r[Lm] = o["hold1s"]["pnl"] if o else None
        out[m] = (c["bt"], r)
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    t0 = min(v[0] for v in res.values()); t1 = max(v[0] for v in res.values()); mid = t0 + (t1 - t0) / 2
    for name, s in SEL.items():
        ms = [m for m in res if s.get(m)]
        cells = []
        for Lm in (45, 60, 75):
            v = [(res[m][0], res[m][1][Lm]) for m in ms if res[m][1].get(Lm) is not None]
            tot = sum(x for _, x in v); a = sum(x for t, x in v if t < mid); nf = sum(1 for _, x in v if x != -0.005)
            cells.append(f"L{Lm} {tot:+6.2f} ({a:+.1f}/{tot - a:+.1f}) fills {nf}/{len(v)}")
        print(f"{name:28} " + " | ".join(cells))
