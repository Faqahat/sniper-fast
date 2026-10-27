#!/usr/bin/env python3
# e11: how sensitive is the learned exit to its decision threshold? Every final e04b model (seeds / horizons) and their ensemble
# (mean prediction of the three h1248 seeds), at theta = -2 .. +2 mSOL, TRAIN (in-sample for the model) and TEST (out of sample),
# M2 and IMIT1, engine SOL/day at our measured landing; plus our real live fills (test hours).
# -> /home/moiz/sniper-data/exits/e11_theta.txt
import sys, os, json, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_gbdt as GT, e04_learn as L4

TAGS = ["h1248", "h1248s2", "h1248s3", "h12", "h24816"]
THS = [-0.002, -0.001, -0.0005, 0.0, 0.0005, 0.001, 0.002]


def preds(d, X, tag):
    M = pickle.load(open(f"{E.DATA}/e04b_{tag}_model.pkl", "rb")); mm = M["models"][0]
    return GT.predict(mm["model"], GT.binize(X, mm["edges"])).reshape(len(d.t_did), d.K - 1), M


def ticks(pr, th, cap=20):
    N = len(pr); sell = np.concatenate([pr <= th, np.ones((N, 1), bool)], 1); sell[:, cap - 1:] = True
    return sell.argmax(1) + 1


if __name__ == "__main__":
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); N = len(d.t_did)
    dl = V.Data(paths=f"{E.DATA}/paths/paths_live.npz")
    idx = [x for x in json.load(open(f"{E.DATA}/paths/live_index.json")) if x["st"] == 0]
    te_live = np.array([x["t"] for x in idx]) >= V.SPLIT
    X, _ = L4.build_matrix(d); XL, _ = L4.build_matrix(dl)
    PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    base = {}
    for pn in PER:
        for w in ("M2", "IMIT1"): base[(pn, w)] = L4.engine_eval(d, np.full(N, 4), PER[pn], w)[0]
    p4l = dl.pnl(dl.tick_policy(np.full(len(dl.s_in), 4))[0], 0)
    L(f"TODAY c4: TRAIN M2 {base[('train', 'M2')]:+.2f} IMIT1 {base[('train', 'IMIT1')]:+.2f} | TEST M2 {base[('test', 'M2')]:+.2f} IMIT1 {base[('test', 'IMIT1')]:+.2f} SOL/day")
    L("each cell: learned minus c4 (SOL/day) TRAIN M2 / IMIT1 | TEST M2 / IMIT1 | live fills TEST hours (SOL, 62 fills)")
    P = {}; PL = {}
    for tg in TAGS:
        P[tg], M = preds(d, X, tg); PL[tg], _ = preds(dl, XL, tg)
    P["ENS3"] = (P["h1248"] + P["h1248s2"] + P["h1248s3"]) / 3; PL["ENS3"] = (PL["h1248"] + PL["h1248s2"] + PL["h1248s3"]) / 3
    for tg in TAGS + ["ENS3"]:
        L(f"\n{tg}" + (f" (VAL-chosen theta {pickle.load(open(f'{E.DATA}/e04b_{tg}_model.pkl', 'rb'))['theta'] * 1000:+.1f} mSOL)" if tg != "ENS3" else " (mean of the 3 h1248 seeds)"))
        for th in THS:
            ks = ticks(P[tg], th); s = f"   theta {th * 1000:+.1f}:"
            for pn in PER:
                for w in ("M2", "IMIT1"):
                    s += f" {L4.engine_eval(d, ks, PER[pn], w)[0] - base[(pn, w)]:+5.2f}"
                s += " |"
            kl = ticks(PL[tg], th); pl = dl.pnl(dl.tick_policy(kl)[0], 0)
            s += f" live {pl[te_live].sum() - p4l[te_live].sum():+.3f}   (mean hold tick TEST {ks[(d.D['t'][d.t_did] >= V.SPLIT)].mean():.1f})"
            L(s)
    open(f"{E.DATA}/e11_theta.txt", "w").write("\n".join(lines) + "\n")
