#!/usr/bin/env python3
# FORWARD REPLAY (read-only, offline): every launch our shadow engine watched in the forward run (10-22 17:10 UTC ->),
# our buy at our real place in line for several landing times / sizes, ~90 exit rules each. One row per launch.
import sys, os, json, gzip, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
OUT = sys.argv[1] if len(sys.argv) > 1 else "fwd.jsonl.gz"
L = rp.load_launches(); O = rp.load_obs()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts.json"))
RULES = rp.default_rules(); NAMES = [r["name"] for r in RULES]
CFG = {"L75": dict(L=75, B=0.5), "L60": dict(L=60, B=0.5), "L75_B1": dict(L=75, B=1.0), "L75_d1": dict(L=75, B=0.5, delay=1),
       "L35": dict(L=35, B=0.5), "L0": dict(L=0, B=0.5)}
fw = [m for m in O if m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); rows = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        dk = st["dev_k"]; ref = (tr[dk]["vsol"] / tr[dk]["vtok"]) if dk is not None else 30e9 / 1.073e15
        gend = tr[st["g_end"] - 1] if st["g_end"] > 0 else None
        p_bundle = (gend["vsol"] / gend["vtok"]) if gend else ref
        row = dict(mint=m, bt=c.get("bt"), slot=S, signer=c.get("user"), creator=c.get("creator"), name=c.get("name"), symbol=c.get("symbol"),
                   uri=c.get("uri"), ixn0=(c.get("ixn") or [None])[0], dev_buy=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 4),
                   glued_n=len(st["glued"]), glued_sol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 4), n_trades=len(tr),
                   max_vsol=round(max(t["vsol"] for t in tr) / 1e9, 2), att=A.get(m, {}), decide_ms=O[m].get("dec", {}).get("at_ms"),
                   bundle_px_vs_dev=round(p_bundle / ref, 4), cfg={})
        for k, cf in CFG.items():
            idx, na = rp.place(tr, c, st, O[m]["outs"], cf["L"]) if cf["L"] > 0 else (st["g_end"], 0)
            if idx < 1: continue
            pf = tr[idx - 1]["vsol"] / tr[idx - 1]["vtok"]
            out = rp.sim(tr, c, st, idx, cf["B"], RULES, delay_slots=cf.get("delay", 0), fill_pen=0.015)
            if not out: continue
            row["cfg"][k] = dict(idx=idx, ahead=na, fill_vs_dev=round(pf / ref, 4), fill_vs_bundle=round(pf / p_bundle, 4),
                                 pnl=[out[n]["pnl"] for n in NAMES], grad=[int(out[n]["grad"]) for n in NAMES], nsell=[out[n]["nsell"] for n in NAMES])
        if row["cfg"]: rows.append(row)
    return rows
if __name__ == "__main__":
    n = 0
    with gzip.open(OUT, "wt") as f, Pool(14) as p:
        f.write(json.dumps(dict(rules=NAMES, cfg=CFG)) + "\n")
        for rows in p.imap_unordered(work, sorted(byb)):
            for r in rows: f.write(json.dumps(r) + "\n"); n += 1
    print("rows", n)
