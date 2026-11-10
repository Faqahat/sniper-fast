"""Bot ON/OFF mask: a slot is ON if 9pQQ landed any buy or sell within +-1,500 slots (~5 min)."""
import numpy as np, pickle, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
def own_slots(run):
    R = pickle.load(open(f"{llib.D}/trips_{run}.pkl", "rb"))["rows"]
    return np.sort(np.array([r["bs"] for r in R] + [r["ss"] for r in R]))
def on(run, slots, win=1500):
    o = own_slots(run); k = np.searchsorted(o, slots)
    left = np.where(k > 0, slots - o[np.maximum(k - 1, 0)], 10**9); right = np.where(k < len(o), o[np.minimum(k, len(o) - 1)] - slots, 10**9)
    return np.minimum(left, right) <= win
def mom_slots(run):
    z = np.load(f"{llib.D}/mom_{run}.npz"); s = np.load(f"{llib.D}/tape_{run}.npz")["s"]
    # tape rows in mom ids index the curve-only arrays; rebuild curve mask
    fl = np.load(f"{llib.D}/tape_{run}.npz")["fl"]
    sc = s[(fl & 1) == 1]
    return sc[z["ids"][:, 1]]
