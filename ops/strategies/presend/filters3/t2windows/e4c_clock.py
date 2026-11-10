#!/usr/bin/env python3
"""T2-WINDOWS step 4c [MEASURED]: calibrate the simulated tries' clock on the REAL tries of live windows (tape covered).
  * signing view: the engine signs on a curve state that already holds trades placed LATER on the block clock (the block clock spreads
    a slot's txs evenly; the feed delivers them earlier). For each real try: is the tape state at tau + lead (trades with cc < tau + lead)
    = the engine's signing state (vtok)? -> agreement per lead, per run and kind.
  * landing: L_eff = cc(landing) - tau (tau = send on the block clock = t_send - (anchor arrival - cc(anchor))): the pool the sim draws.
Out: /home/it/sniper-data/filters3/t2windows/clock.pkl"""
import sys, pickle, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L

LEADS = [0, 10, 20, 30, 40, 50, 60, 80, 100, 130, 160, 200]
RUNS = [39, 40, 41, 42, 44, 45, 46, 47, 48, 49]
G = {}


def init():
    G["clk"] = L.Clock(pickle.load(open(f"{L.D}/maxi.pkl", "rb")))
    G["wins"] = collections.defaultdict(list)
    for r in RUNS:
        for w in pickle.load(open(f"{L.D}/rec_{r}.pkl", "rb"))["wins"]:
            G["wins"][L.bucket(w["mint"])].append((r, w))


def job(b):
    clk = G["clk"]; tapes = L.load_bucket(b)
    agree = collections.defaultdict(lambda: np.zeros(len(LEADS) + 1)); leff = collections.defaultdict(list)
    for r, w in G["wins"].get(b, []):
        a = w.get("trig") if w["kind"] == "t2" else w.get("dump")
        tp = tapes.get(w["mint"])
        if not a or not tp or a["slot"] not in clk.maxi: continue
        ka = next((k for k, x in enumerate(tp["rows"]) if x["sig"] == a["sig"]), None)
        if ka is None: continue
        seg = L.Seg(tp, ka, clk, 80)
        off = a["t"] / 1e6 - clk.cc(a["slot"], a["idx"])
        kind = w["kind"]
        for t in w["tries"]:
            tau = t["t"] / 1e6 - off
            Ld = t.get("land") or {}
            if Ld.get("idx") is not None and Ld.get("res") not in (None, "unseen") and Ld["slot"] in clk.maxi:
                leff[(r, kind)].append(clk.cc(Ld["slot"], Ld["idx"]) - tau)
            elif Ld.get("res") == "unseen":
                leff[(r, kind)].append(None)
            if not t.get("vtok"): continue
            ys = np.array([tau + x for x in LEADS])
            Ts = seg.T_before_cc(ys)
            hit = np.abs(Ts - t["vtok"]) / t["vtok"] < 1e-7
            agree[(r, kind)][:len(LEADS)] += hit; agree[(r, kind)][-1] += 1
    return dict(agree), dict(leff)


if __name__ == "__main__":
    AG = collections.defaultdict(lambda: np.zeros(len(LEADS) + 1)); LE = collections.defaultdict(list)
    with Pool(3, initializer=init) as p:
        for ag, le in p.imap_unordered(job, range(L.NB)):
            for k, v in ag.items(): AG[k] += v
            for k, v in le.items(): LE[k] += v
    for k in sorted(AG):
        v = AG[k]; n = v[-1]
        le = [x for x in LE[k] if x is not None]
        print(k, int(n), " ".join(f"{l}:{v[j] / n:.2f}" for j, l in enumerate(LEADS)), f"| L_eff n {len(le)} p25/50/75 {np.percentile(le, 25):.0f}/{np.median(le):.0f}/{np.percentile(le, 75):.0f}")
    pickle.dump({"leads": LEADS, "agree": {k: v.tolist() for k, v in AG.items()}, "leff": dict(LE)}, open(f"{L.D}/clock.pkl", "wb"))
