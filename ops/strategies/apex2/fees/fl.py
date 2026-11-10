"""loader: columns as numpy arrays (object for strings)"""
import pickle, numpy as np
D = "/home/it/sniper-data/apex2/fees"
def load():
    z = pickle.load(open(D + "/T.pkl", "rb")); F = z["fields"]; R = z["rows"]
    C = {}
    for k, f in enumerate(F):
        col = [r[k] for r in R]
        if f in ("cs", "ci", "so", "i", "rel", "sol", "nsig", "fee", "prio", "tips", "tipsa", "ntip", "bt", "ntr", "buyk"):
            C[f] = np.array(col, np.int64)
        elif f in ("pick", "unseen", "wl", "landed"): C[f] = np.array(col, bool)
        elif f == "cupe": C[f] = np.array(col, float)
        elif f == "rank": C[f] = np.array([-1 if v is None else v for v in col], np.int64)
        elif f in ("cu", "cul", "cup"): C[f] = np.array([-1 if v is None else v for v in col], np.int64)
        else: C[f] = np.array(col, dtype=object)
    del R
    L = pickle.load(open(D + "/L.pkl", "rb"))
    return C, L
