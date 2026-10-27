#!/usr/bin/env python3
# loader for the episode / tick pickles (h5_episodes.py output)
import pickle, glob, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
def load(with_ticks=True):
    eps = []; TI = []; TF = []; feats = None
    for f in sorted(glob.glob(f"{H.OUT}/ep/b*.pkl")):
        d = pickle.load(open(f, "rb")); base = len(eps); eps += d["eps"]; feats = d["feats"]
        if with_ticks and len(d["TI"]):
            ti = d["TI"].copy(); ti[:, 0] += base; TI.append(ti); TF.append(d["TF"])
    if with_ticks:
        TI = np.vstack(TI); TF = np.vstack(TF)
        return eps, TI, TF, feats
    return eps
