#!/usr/bin/env python3
# apply a saved learned exit (e04 *_model.pkl) to any e_eval.Data object -> sell tick per trajectory
import os, sys, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_gbdt as GT


def apply_saved(d, pkl, theta=None, it=-1):
    import e04_learn as L4
    M = pickle.load(open(pkl, "rb"))
    if "ensemble" in M:                  # mean prediction of several e04b models, own theta / cap
        prs = [apply_saved(d, q, theta=0.0)[1] for q in M["ensemble"]]
        pred = sum(prs) / len(prs); th = M["theta"] if theta is None else theta
        N = len(d.t_did); sell = np.concatenate([pred <= th, np.ones((N, 1), bool)], 1); sell[:, M["cap"] - 1:] = True
        return sell.argmax(1) + 1, pred
    X, names = L4.build_matrix(d)
    assert names == M["names"], "feature list changed"
    mm = M["models"][it]
    Bm = GT.binize(X, mm["edges"])
    pred = GT.predict(mm["model"], Bm).reshape(len(d.t_did), d.K - 1)
    th = M["theta"] if theta is None else theta
    if "cap" in M:                       # e04b models: sell at the first tick with prediction <= theta, forced at the cap
        N = len(d.t_did); sell = np.concatenate([pred <= th, np.ones((N, 1), bool)], 1); sell[:, M["cap"] - 1:] = True
        return sell.argmax(1) + 1, pred
    return L4.policy_ticks(pred, len(d.t_did), d.K, th), pred


def apply_tree(d, pkl):
    """e09 small tree -> sell tick per trajectory"""
    import e04_learn as L4, gbdt_np as GB
    M = pickle.load(open(pkl, "rb"))
    X, names = L4.build_matrix(d)
    assert names == M["names"]
    Bm = GT.binize(X, M["edges"])
    pr = (M["mu"] + GB.pred(M["tree"], Bm)).reshape(len(d.t_did), d.K - 1)
    N = len(d.t_did); sell = np.concatenate([pr <= M["theta"], np.ones((N, 1), bool)], 1); sell[:, M["cap"] - 1:] = True
    return sell.argmax(1) + 1
