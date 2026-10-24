#!/usr/bin/env python3
# FORWARD test of the frozen DIP4 models (frozen_dip4_L20.json, frozen_dip4_L35.json): only dips AFTER the freeze, rebuilt from
# the dry-run extraction with dipbuy4 (follower slippage imputed, our sell 75 ms into its slot), sell 4 slots later.
import sys, os, json, time, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["SLIPIMP"] = "1"; os.environ["SELL_LAT"] = "75"; os.environ["DIP_LATS"] = "20,35,50,75"; os.environ["DIP_B"] = "0.5"
FX = os.environ.get("FWD_EXIT", "4"); os.environ.setdefault("DIP_HS", FX)
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
import gbdt_np as G
from dipcv import fv
from multiprocessing import Pool
STEMS = os.environ.get("FWD_MODELS", "dip4_L20,dip4_L35").split(",")
M = {st.split("_L")[1]: json.load(open(f"/home/moiz/sniper/ops/overnight/dip/frozen_{st}.json")) for st in STEMS}
T0 = min(m["frozen_at"] for m in M.values())
D.byb.clear()
for m, c in D.L.items():
    if c.get("bt") and c["bt"] >= T0 - 130: D.byb[(c["run"], D.rp.bucket(m))].add(m)
def score(model, R):
    X = np.array([fv(r) for r in R]) if R else np.zeros((0, len(model["features"])))
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
    ev = [r for r in ev if r["bt"] + r["age"] > T0]; ev.sort(key=lambda r: r["bt"] + r["age"])
    span = ((ev[-1]["bt"] + ev[-1]["age"] - T0) / 3600) if ev else 0
    print(f"FORWARD {next(iter(M.values()))['name'].split('-L')[0].replace('FRZ-', '')} test{os.environ.get('FWD_LABEL', '')}, evaluated {time.strftime('%Y-%m-%d %H:%M', time.gmtime(time.time() + 18000))} PKT | frozen {next(iter(M.values()))['frozen_at_pkt']} | forward dips {len(ev)} over {span:.2f} h of data")
    for lat, model in M.items():
        f = score(model, ev)
        for q in ("2%", "5%", "10%"):
            sel = [r for r, s in zip(ev, f) if s >= model["thresholds"][q]]
            cells = []
            for Lm in ("20", "35", "50", "75"):
                v = [r["pnl"][Lm][FX] for r in sel if Lm in r["pnl"]]
                if v: cells.append(f"L{Lm}: n {len(v)} mean {np.mean(v):+.4f} total {np.sum(v):+.2f} (+0.002/tx {np.sum(v) - 0.004 * len(v):+.2f}) win {np.mean([x > 0 for x in v]):.0%}")
            print(f"  DIP{FX} model L{lat} top {q:>3}: " + (" | ".join(cells) if cells else "no trades"))
            if q == "5%":
                g = []
                for Lm in ("20", "35", "50", "75"):
                    vv = [(r["pnl"][Lm][FX] if r["px"].get(Lm, 1.0) <= 1.02 else -0.0002) for r in sel if Lm in r["pnl"]]
                    if vv: g.append(f"L{Lm}: {np.sum(vv):+.2f}")
                print(f"  DIP{FX} model L{lat} top  5% with 2% guard: " + " | ".join(g))
        sel = [r for r, s in zip(ev, f) if s >= model["thresholds"]["5%"]]
        H = collections.defaultdict(list)
        for r in sel:
            if lat in r["pnl"]: H[int(((r["bt"] + r["age"] + 18000) % 86400) // 3600)].append(r["pnl"][lat][FX])
        print(f"  DIP{FX} model L{lat} top 5% by PKT hour (entry {lat} ms): " + " ".join(f"{h:02d}h n{len(v)} {sum(v):+.2f}" for h, v in sorted(H.items())))
