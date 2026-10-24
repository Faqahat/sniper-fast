#!/usr/bin/env python3
# Labels for a "become them" selection model: for every launch where our guarded buy fills (0.5% guard vs the
# post-bundle price) at 45 / 75 ms, 0.5 SOL, the PnL of time exits 3/5/8/10/15 s and eos1 under
#   base (real path), slip (followers we price out dropped), ps (slip + every PRO buy after our entry dropped),
#   ns (slip + every SNIPER/PRO buy after our entry dropped).
# R2 = block-order placement on our engine's timelines; R1 = position proxy. -> allres_bt.json
# usage: RP_PHASEA_R2=phaseA_gf python3 -I precompute_bt.py
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
CORE = "/home/moiz/sniper/ops/overnight/core"
L = rp.load_launches(); O = rp.load_obs(); W = json.load(open(f"{CORE}/gf_wallets.json"))
LS = json.load(open(f"{CORE}/gf_launches.json"))
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO = set()
for p in ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz"):
    c = [u for u in W if u.startswith(p)]
    if c: PRO.add(max(c, key=lambda u: W[u][0]))
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)] + [rp.R(f"t{h}", [(1.0, ("t", float(h)))], h + 1) for h in (3, 5, 8, 10, 15)]
XN = [e["name"] for e in EX]; G = 1.005
todo = [m for m in LS if m in L and (LS[m]["run"] == "R1" or m in O)]
byb = collections.defaultdict(set)
for m in todo: byb[(LS[m]["run"], rp.bucket(m))].add(m)
SL = None
def init():
    global SL
    SL = rp.load_slip()
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(run=run, bt=c["bt"])
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, [])) if run == "R2" else rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > G: r[str(Lm)] = None; continue
            d = {}
            for var, kw in (("base", {}), ("slip", dict(slip=SL)), ("ps", dict(slip=SL, drop_after=PRO)), ("ns", dict(slip=SL, drop_after=SNIPER | PRO))):
                o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015, delay_slots=1, **kw)
                if o: d[var] = [round(o[x]["pnl"], 5) for x in XN]
            bs = max(c["slot"], tr[ib - 1]["s"]); d["nb"] = sum(1 for t in tr[ib:] if t["s"] <= bs + 1 and t["buy"])
            d["pro_ahead"] = any(t["user"] in PRO for t in tr[st["g_end"]:ib])
            r[str(Lm)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8, initializer=init) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(dict(exits=XN, res=res), open(f"{CORE}/allres_bt.json", "w"))
    n = collections.Counter((v["run"], Lm) for v in res.values() for Lm in ("45", "75") if v.get(Lm))
    print("launches", len(res), "guarded fills:", dict(n))
