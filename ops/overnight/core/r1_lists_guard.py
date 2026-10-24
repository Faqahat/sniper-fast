# OLD DATA (R1, block-position landing proxy): guarded flip (1%, hold ~1 s, fail 0.005) for the S4 list, AHwJSnFN list, union
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); A = json.load(open("attempts.json")); AH = json.load(open("attempts_ahw.json")); DC = "/home/moiz/sniper/ops/snipers/devcheck"
def wf(att, wallets, ledger=False):
    ev = []
    if ledger:
        for w in ("9Sh2fd", "DGmspi"):
            for f in (f"devs_{w}.json", f"att_{w}.json"):
                p = os.path.join(DC, f)
                if os.path.exists(p):
                    for m, v in json.load(open(p)).items():
                        if v.get("signer") and v.get("bt") and m not in L: ev.append((v["bt"], v["signer"], 1))
    for m, c in L.items():
        if not c.get("bt"): continue
        ev.append((c["bt"], c["user"], 0))
        if any(w in att.get(m, {}) for w in wallets): ev.append((c["bt"], c["user"], 1))
    ev.sort(); na = collections.Counter(); nl = collections.Counter(); j = 0; keep = set()
    for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt") and c["run"] == "R1"):
        while j < len(ev) and ev[j][0] < bt:
            _, d, a = ev[j]; (na if a else nl)[d] += 1; j += 1
        d = L[m]["user"]
        if na[d] >= 2 and (nl[d] == 0 or na[d] / nl[d] >= 0.10): keep.add(m)
    return keep
S = {"S4 list": wf(A, ("9Sh2fd", "DGmspi"), ledger=True), "AHwJSnFN list": wf(AH, ("AHwJSn",))}
S["union (S5)"] = S["S4 list"] | S["AHwJSnFN list"]
ALLM = set().union(*S.values())
byb = collections.defaultdict(set)
for m in ALLM:
    if "InitializeMayhemState" not in (L[m].get("ixn") or []): byb[rp.bucket(m)].add(m)
EX = [rp.R("hold1s", [(1.0, ("t", 1))], 2)]
def work(b):
    tra = rp.read_bucket("R1", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (35, 45, 60, 75):
            ib, _ = rp.place_proxy(tr, c, st, Lm)
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
    print(f"R1 old data {(t1 - t0) / 3600:.1f} h, guarded flip, landing proxy (pessimistic at 60-75 ms)")
    for name, s in S.items():
        cells = []
        for Lm in (35, 45, 60, 75):
            v = [(res[m][0], res[m][1][Lm]) for m in s if m in res and res[m][1].get(Lm) is not None]
            tot = sum(x for _, x in v); a = sum(x for t, x in v if t < mid); nf = sum(1 for _, x in v if x != -0.005)
            cells.append(f"L{Lm} {tot:+6.2f} ({a:+.1f}/{tot - a:+.1f}) fills {nf}/{len(v)}")
        print(f"   {name:16} " + " | ".join(cells))
    json.dump({k: sorted(v) for k, v in S.items()}, open("r1_lists.json", "w"))
