#!/usr/bin/env python3
"""REAL replay check: the variant pipeline (detected triggers, the engine's skip rules, no forced arming) on the two PROBE periods,
with each probe's own settings, next to live. Shows whether the test-hour results and the probe hours come from the same machine.
usage: probehours.py [--draws 40]"""
import sys, os, json, pickle, argparse, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib, sim, variants

OUT = "/home/moiz/sniper-data/presend_real"
SPANS = {"P1": ("10-25 08:49", "10-25 09:50"), "P2": ("10-25 15:30", "10-25 17:30")}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--draws", type=int, default=40); A = ap.parse_args()
    tp = rlib.Tape()
    D = pickle.load(open(f"{OUT}/donors.pkl", "rb"))
    land = sim.Landing(D); model = sim.Model(D, tp); view = sim.View(); ck = tp.clock()
    for name, wp in (("P1", 5), ("P2", 6)):
        c = D[name]["cfg"]
        a, b = SPANS[name]
        t_lo = rlib.pk(a); t_hi = rlib.pk(b)
        # the live engine followed only tokens created after it started
        t_start = D[name]["start"]["t"] / 1e9
        trig = pickle.load(open(f"{OUT}/trig_{wp}.pkl", "rb"))
        ws = []
        for d in trig:
            if not (t_lo <= d["bt"] < t_hi): continue
            if tp.creates[d["mint"]]["bt"] < t_start: continue
            sw = None
            if d["sells"]:
                k = d["sells"][0]; sw = (int(tp.s[k]), int(tp.i[k]))
            ws.append(dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=d["v2"], cashback=d["cashback"], whale=d["whale"],
                           whale_sell=sw, pred=None, quick=0, bt=d["bt"], half=1))
        store = sim.build_store(tp, variants.spans_for(ws))
        cfg = sim.Cfg(slot_ms=(214.1 if name == "P1" else 211.7), size=c["spend"], k=c["k"], paths=[(c["path_max_per_sec"], c["path_max_per_sec"])],
                      global_rate=c["max_per_sec"], whale_pct=c["whale_pct"])
        hours = (t_hi - t_lo) / 3600
        nets = []; fills = []; armed = []
        for sd in range(A.draws):
            res = sim.run(ck, store, ws, cfg, land, model, view, np.random.default_rng(sd))
            nets.append(sum(r.get("net", 0) for r in res if r["armed"]) / 1e9); fills.append(sum(r.get("filled", False) for r in res if r["armed"]))
            armed.append(sum(1 for r in res if r["armed"]))
        live = [W for W in D[name]["wins"] if t_lo <= W["trig"]["t"] / 1e9 < t_hi]
        live_net = sum(W["realized"]["pnl"] for W in live if W["fill"]) / 1e9 - sum((t["fee"] or 5120) for W in live for t in W["tries"] if t["res"] in ("6042", "deadline", "ata_exists", "other")) / 1e9
        print(f"{name} {a}-{b} PKT ({hours:.2f} h): replay armed {np.mean(armed):.0f} (live {len(live)}), fills {np.mean(fills):.1f} (live {sum(1 for W in live if W['fill'])}), "
              f"net {np.mean(nets):+.4f} SOL [p5 {np.percentile(nets, 5):+.4f}, p95 {np.percentile(nets, 95):+.4f}] (live {live_net:+.4f}) = {np.mean(nets) / hours * 24:+.2f} SOL/day")
