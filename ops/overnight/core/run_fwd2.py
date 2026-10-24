#!/usr/bin/env python3
# FORWARD REPLAY v2 (read-only, offline): more landing times, sell delays, sizes, a pessimistic "they fail after us"
# variant, quick-flip exits and many partial-sell ladders. One row per launch with pnl per (config, rule).
import sys, os, json, gzip, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
OUT = sys.argv[1] if len(sys.argv) > 1 else "fwd2.jsonl.gz"
L = rp.load_launches(); O = rp.load_obs()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts.json"))
R = rp.R
RULES = rp.default_rules() + [
    R("eos0", [(1.0, ("slot", 0))], 5), R("eos1", [(1.0, ("slot", 1))], 5), R("eos2", [(1.0, ("slot", 2))], 5), R("eos4", [(1.0, ("slot", 4))], 5),
    R("fsell_any_c2", [(1.0, ("ev", "any_sell"))], 2), R("fsell_any_c5", [(1.0, ("ev", "any_sell"))], 5),
    R("tp1.1_sl0.9_c2", [(1.0, ("x", 1.1)), (1.0, ("sl", 0.9))], 2), R("tp1.2_sl0.9_c5", [(1.0, ("x", 1.2)), (1.0, ("sl", 0.9))], 5),
    R("tp1.1_eos2", [(1.0, ("x", 1.1)), (1.0, ("slot", 2))], 5),
    # partial ladders: sell in pieces while watching the price / over time
    R("pA_50eos1_50@2x_c30", [(0.5, ("slot", 1)), (1.0, ("x", 2.0))], 30),
    R("pB_50fsell_50trail1.3_.2_c60", [(0.5, ("ev", "any_sell")), (1.0, ("dd", 1.3, 0.2)), (1.0, ("sl", 0.7))], 60),
    R("pC_33@1.2_33@1.5_34@2_sl.85_c30", [(0.33, ("x", 1.2)), (0.33, ("x", 1.5)), (0.34, ("x", 2.0)), (1.0, ("sl", 0.85))], 30),
    R("pD_25at_slots1_3_6_10", [(0.25, ("slot", 1)), (0.25, ("slot", 3)), (0.25, ("slot", 6)), (0.25, ("slot", 10))], 5),
    R("pH_77@1.3_rest_trail.3_c300", [(0.77, ("x", 1.3)), (1.0, ("dd", 1.3, 0.3)), (1.0, ("sl", 0.75))], 300),
    R("pI_50eos0_50hold10s", [(0.5, ("slot", 0)), (1.0, ("t", 10))], 11),
    R("pJ_50eos1_25@1.5_25trail.25_c60", [(0.5, ("slot", 1)), (0.25, ("x", 1.5)), (1.0, ("dd", 1.5, 0.25)), (1.0, ("sl", 0.7))], 60),
    R("pK_20pct_each_new_high_10pct", [(0.2, ("x", 1.1)), (0.2, ("x", 1.21)), (0.2, ("x", 1.33)), (0.2, ("x", 1.46)), (0.2, ("x", 1.61)), (1.0, ("sl", 0.85))], 60),
]
NAMES = [r["name"] for r in RULES]
CASE = {"9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"}
CFG = {"L0": dict(L=0), "L25": dict(L=25), "L35": dict(L=35), "L45": dict(L=45), "L60": dict(L=60), "L75": dict(L=75), "L90": dict(L=90),
       "L35_d1": dict(L=35, delay=1), "L60_d1": dict(L=60, delay=1), "L75_d1": dict(L=75, delay=1),
       "L35_drop": dict(L=35, drop=True), "L60_drop": dict(L=60, drop=True),
       "L35_B025": dict(L=35, B=0.25), "L35_B1": dict(L=35, B=1.0), "L60_B025": dict(L=60, B=0.25)}
fw = [m for m in O if m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
def gaps(tr, S):
    n = 0
    for a, t in zip(tr, tr[1:]):
        if (t["s"] - S) * rp.SLOT_MS > 60000: break
        V, T = a["vsol"], a["vtok"]
        if t["buy"]: eV = V + t["sol"]; eT = T - T * t["sol"] // (V + t["sol"])
        else: eV = V - V * t["tok"] // (T + t["tok"]); eT = T + t["tok"]
        n += abs(eV - t["vsol"]) > 2 or abs(eT - t["vtok"]) > 2
    return n
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); rows = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        dk = st["dev_k"]; ref = (tr[dk]["vsol"] / tr[dk]["vtok"]) if dk is not None else 30e9 / 1.073e15
        row = dict(mint=m, bt=c.get("bt"), slot=S, signer=c.get("user"), creator=c.get("creator"), name=c.get("name"), symbol=c.get("symbol"),
                   uri=c.get("uri"), ixn0=(c.get("ixn") or [None])[0], create_sig=c.get("sig"),
                   dev_buy=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 4),
                   glued_n=len(st["glued"]), glued_sol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 4), n_trades=len(tr), gaps60=gaps(tr, S),
                   max_vsol=round(max(t["vsol"] for t in tr) / 1e9, 2), att=A.get(m, {}), decide_ms=O[m].get("dec", {}).get("at_ms"), cfg={})
        for k, cf in CFG.items():
            idx, na = rp.place(tr, c, st, O[m]["outs"], cf["L"]) if cf["L"] > 0 else (st["g_end"], 0)
            if idx < 1: continue
            pf = tr[idx - 1]["vsol"] / tr[idx - 1]["vtok"]
            out = rp.sim(tr, c, st, idx, cf.get("B", 0.5), RULES, delay_slots=cf.get("delay", 0), fill_pen=0.015, drop_after=CASE if cf.get("drop") else None)
            if not out: continue
            row["cfg"][k] = dict(idx=idx, ahead=na, after_sig=tr[idx - 1]["sig"], fill_vs_dev=round(pf / ref, 4),
                                 pnl=[out[n]["pnl"] for n in NAMES], grad=[int(out[n]["grad"]) for n in NAMES], nsell=[out[n]["nsell"] for n in NAMES],
                                 hold=[out[n]["hold_s"] for n in NAMES])
        if row["cfg"]: rows.append(row)
    return rows
if __name__ == "__main__":
    n = 0
    with gzip.open(OUT, "wt") as f, Pool(14) as p:
        f.write(json.dumps(dict(rules=NAMES, cfg=CFG)) + "\n")
        for rows in p.imap_unordered(work, sorted(byb)):
            for r in rows: f.write(json.dumps(r) + "\n"); n += 1
    print("rows", n)
