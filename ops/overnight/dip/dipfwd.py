#!/usr/bin/env python3
# FORWARD test of the frozen dip-buy models (frozen_dip_L35.json, frozen_dip_L50.json): only dips that happen AFTER the freeze.
# Events are rebuilt from the dry-run extraction (phaseA_dry) with dipbuy2's code; scored with the frozen bins + trees.
# Report: selected trades at the frozen top-2/5/10% thresholds, PnL at entries 35 / 50 / 75 ms after the sell, exit 8 slots,
# at 0.0008 SOL/tx and with +0.002 SOL/tx; by PKT hour. -> appended to dip/fwd_dip.log by fwd_dip_loop.sh
import sys, os, json, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry")
import dipbuy2 as D
import gbdt_np as G
from dipfreeze import fv
from multiprocessing import Pool
M = {lat: json.load(open(f"/home/moiz/sniper/ops/overnight/dip/frozen_dip_L{lat}.json")) for lat in ("20", "35", "50")}
T0 = min(m["frozen_at"] for m in M.values())
keys = [k for k, c in D.L.items() if c.get("bt") and c["bt"] >= T0 - 130]
D.byb.clear()
for m in keys: D.byb[(D.L[m]["run"], D.rp.bucket(m))].add(m)
def score(model, R):
    X = np.array([fv(r, set(model["sn8"])) for r in R]) if R else np.zeros((0, len(model["features"])))
    Bm = np.zeros(X.shape, np.int16)
    for j in range(X.shape[1]):
        b = np.searchsorted(np.array(model["edges"][j]), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
    f = np.full(len(R), model["F0"])
    for t in model["trees"]: f += model["lr"] * G.pred(t, Bm)
    return f
if __name__ == "__main__":
    ev = []
    with Pool(8) as p:
        for o, _ in p.imap_unordered(D.work, sorted(D.byb), chunksize=1): ev += o
    ev = [r for r in ev if r["bt"] + r["age"] > T0]
    ev.sort(key=lambda r: r["bt"] + r["age"])
    now = time.time()
    span = ((ev[-1]["bt"] + ev[-1]["age"] - T0) / 3600) if ev else 0
    print(f"FORWARD dip test, evaluated {time.strftime('%Y-%m-%d %H:%M', time.gmtime(now + 18000))} PKT | frozen {M['35']['frozen_at_pkt']} | forward dips {len(ev)} over {span:.2f} h of data")
    for lat, model in M.items():
        f = score(model, ev)
        for q in ("2%", "5%", "10%"):
            sel = [r for r, s in zip(ev, f) if s >= model["thresholds"][q]]
            cells = []
            for Lm in ("20", "35", "50", "75"):
                v = [r["pnl"][Lm]["8"] for r in sel if Lm in r["pnl"]]
                if v: cells.append(f"L{Lm}: n {len(v)} mean {np.mean(v):+.4f} total {np.sum(v):+.2f} (+0.002/tx {np.sum(v) - 0.004 * len(v):+.2f}) win {np.mean([x > 0 for x in v]):.0%}")
            print(f"  model L{lat} top {q:>3}: " + (" | ".join(cells) if cells else "no trades"))
        sel = [r for r, s in zip(ev, f) if s >= model["thresholds"]["5%"]]
        H = collections.defaultdict(list)
        for r in sel:
            if lat in r["pnl"]: H[int(((r["bt"] + r["age"] + 18000) % 86400) // 3600)].append(r["pnl"][lat]["8"])
        print(f"  model L{lat} top 5% by PKT hour (entry {lat} ms): " + " ".join(f"{h:02d}h n{len(v)} {sum(v):+.2f}" for h, v in sorted(H.items())))
