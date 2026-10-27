#!/usr/bin/env python3
# PORT.md tables (agent 10-25): Stage A with the ported top25 model as the ENGINE would run it, per split and landing latency.
#  - "study"      : every in-envelope dump (dd15)
#  - "as built"   : gate mode with --dip-m2-extra on (default): every dump the engine evaluates (IMIT1 dump events + M2 extra
#                   dumps = all but tokens whose create tx has no buy, ~0.3%), dev-list tokens on IMIT1 top4 (unchanged rule)
#  - "extra off"  : only IMIT1 dump events (first big sell of a slot), dev-list tokens on IMIT1 top4
#  - exits c4_tpnone_slnone and c4_tpnone_sl30 (the prod script allows --sl <= 0.5; -30% is the grid's closest stop)
# FRA + AMS (dd_lib.sim), 0.55 SOL.   usage: python3 dd23_port_tables.py
import json
import numpy as np
import dd_lib as L
from dd16_visible import visible
DAYS = ("R2", "R3", "R1", "R4")
if __name__ == "__main__":
    P = np.load(f"{L.OUT}/pred_v3_reg4_top25.npy"); thr = json.load(open(f"{L.OUT}/dd15_stageA.json"))["thr_top25"]
    D = {}; PP = {}; o = 0
    for day in DAYS:
        D[day] = L.load(day); n = len(D[day]["k"]); PP[day] = P[o:o + n]; o += n
    cut = np.quantile(D["R2"]["t"], 0.70); out = {}
    for day in DAYS:
        d = D[day]; w = (d["t"] >= cut) if day == "R2" else np.ones(len(d["t"]), bool); h = L.hours(d) * (0.3 if day == "R2" else 1)
        vis = visible(day, d); dev = L.feat(d, "dev_tok") > 0
        m2 = (PP[day] >= thr) & d["env"]; imit = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"])
        V = {"Stage A study (all dumps)": m2, "Stage A as built (extra on, dev list IMIT1)": np.where(dev, imit, m2),
             "Stage A as built (extra off, dev list IMIT1)": np.where(dev, imit, m2 & vis), "IMIT1 top4 (today)": imit}
        print(f"{day}{'val' if day == 'R2' else ''} ({h:.1f} h)")
        for nm, sel in V.items():
            for exn in (("c4_tpnone_slnone", "c4_tpnone_sl30") if nm != "IMIT1 top4 (today)" else ("c6_tpnone_sl10", "c4_tpnone_slnone")):
                e = L.EXI[exn]; cells = []
                for li, lat in enumerate((35, 50, 75)):
                    r = L.sim(d, sel & w, li, e); out[f"{nm}|{exn}|{day}|{lat}"] = [r["pnl"], r["fill"], r["att"], h]
                    cells.append(f"{lat}ms {r['pnl']:+6.2f} ({r['fill']}/{r['att']})")
                print(f"   {nm:46s} {exn:17s} " + " | ".join(cells), flush=True)
    print("\npooled SOL 35 / 50 / 75 ms: R3+R4 | R3+R1+R4")
    keys = sorted({k.rsplit("|", 2)[0] for k in out})
    for k in keys:
        a = [sum(out[f"{k}|{dd}|{lat}"][0] for dd in ("R3", "R4")) for lat in (35, 50, 75)]
        b = [sum(out[f"{k}|{dd}|{lat}"][0] for dd in ("R3", "R1", "R4")) for lat in (35, 50, 75)]
        print(f"  {k:66s} {a[0]:+6.2f} / {a[1]:+6.2f} / {a[2]:+6.2f} | {b[0]:+6.2f} / {b[1]:+6.2f} / {b[2]:+6.2f}")
    json.dump(out, open(f"{L.OUT}/dd23_port_tables.json", "w"))
