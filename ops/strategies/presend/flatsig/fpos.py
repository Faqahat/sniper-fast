"""FLATSIG: join live positions with their chain trigger features (f4) -> list of dicts with feature dict 'f'."""
import pickle, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L

def positions():
    T = pickle.load(open(f"{L.D}/trig.pkl", "rb")); X = T["X"]; M = T["meta"]; C = T["cols"]
    P = L.all_positions()
    byid = {p["id"]: p for p in P}
    for k, m in enumerate(M):
        for pid in m["ours"]:
            byid[pid]["f"] = dict(zip(C, X[k].tolist())); byid[pid]["lab"] = m
    for p in P:
        p["q3a"] = L.q3a(p); p["q3a_live"] = L.q3a_live(p["run"])
    return P
