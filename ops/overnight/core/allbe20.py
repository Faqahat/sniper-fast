#!/usr/bin/env python3
# Outcome table for EVERY standard launch (R1 + R2) under the FINAL-2 "become them" mechanics, corrected placement
# (verifier fixes in rp.place_bo2; R1 = position proxy): 0.5 SOL, guard 0.5% vs post-bundle, first after the bundle,
# exits t5/t8/t10/t15/idle3_c15, variants slip and proafter_slip, landings 45 / 75 ms. Also bundle composition.
# -> core/allbe.json {mint: {...}}   usage: RP_PHASEA_R2=phaseA_dry python3 -I allbe.py
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
CORE = "/home/moiz/sniper/ops/overnight/core"
L = rp.load_launches(); O = rp.load_obs(); W = json.load(open(f"{CORE}/gf_wallets.json"))
PRO = set()
for p in ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz"):
    c = [u for u in W if u.startswith(p)]
    if c: PRO.add(max(c, key=lambda u: W[u][0]))
EX = [rp.R("s4", [(1.0, ("slot", 3))], 5), rp.R("t2", [(1.0, ("t", 2.0))], 3)] + [rp.R(f"t{h}", [(1.0, ("t", float(h)))], h + 1) for h in (5, 8)]
XN = [e["name"] for e in EX]
G = 1.005; B = 0.5
LANDS = [int(x) for x in os.environ.get("LANDS", "20,35").split(",")]
CWO = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_cw.json")))
byb = collections.defaultdict(set)
for m, c in L.items():
    if c.get("bt") and (c["run"] == "R1" or m in O): byb[(c["run"], rp.bucket(m))].add(m)
SLIP = None
def init():
    global SLIP
    SLIP = rp.load_slip()
def one(tr, c, st, outs, fa, Lm, slip, drop_after):
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
    ib, na = rp.place_bo2(tr, c, st, outs, Lm, fa) if outs is not None else rp.place_proxy(tr, c, st, Lm)
    if ib < 1: return None
    ratio = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b
    if ratio > G: return dict(f=0, r=round(ratio, 3))
    o = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015, delay_slots=1, slip=slip, drop_after=drop_after)
    if not o: return None
    bs = max(c["slot"], tr[ib - 1]["s"]); nb = sum(1 for t in tr[ib:] if t["s"] <= bs + 1 and t["buy"] and not t.get("syn"))
    return dict(f=1, p={x: o[x]["pnl"] for x in XN}, nb=nb)
def work(key):
    run, b = key; out = {}
    tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem"): continue
        st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        outs = O[m]["outs"] if run == "R2" else None; f = fa.get(m, [])
        r = dict(run=run, bt=c["bt"], dep=c.get("user"), creator=c.get("creator"), dev=round(sum(t["sol"] for t in tr[:st["g_end"]] if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 3),
                 glued=len(st["glued"]), gw=sorted({t["user"] for t in st["glued"]}), gsol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 3))
        for Lm in LANDS:
            r[str(Lm)] = dict(slip=one(tr, c, st, outs, f, Lm, SLIP, None), pa=one(tr, c, st, outs, f, Lm, SLIP, PRO), nocw=one(tr, c, st, outs, f, Lm, SLIP, CWO))
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8, initializer=init) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): res.update(o)
    json.dump(res, open(f"{CORE}/allbe20.json", "w"))
    for run in ("R1", "R2"):
        for Lm in [str(x) for x in LANDS]:
            v = [r[Lm]["pa"] for r in res.values() if r["run"] == run and r[Lm]["pa"] is not None]
            f = [x for x in v if x["f"]]
            print(f"{run} {Lm} ms: launches {len(v)} fills {len(f)} | " + " | ".join(f"{x} mean/fill {sum(y['p'][x] for y in f) / max(1, len(f)):+.4f}" for x in XN))
