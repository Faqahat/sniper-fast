"""merged DEV table: positions + chain features (fp1) + own features (fp2). FIT = r37..r42, CHECK = r43..r54."""
import pickle, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import base
FIT = {"r37","r38","r39","r40","r41","r42"}
def table(chain_pkl=None):
    P = pickle.load(open(f"{base.OUT}/dev_pos.pkl","rb"))
    C = pickle.load(open(chain_pkl or f"{base.OUT}/dev_chain.pkl","rb"))
    O = pickle.load(open(f"{base.OUT}/dev_own.pkl","rb"))
    rows=[]
    for p in P:
        k=p["key"]; f=dict(O[k]); c=C.get(k)
        if c: f.update(c)
        else: f["cov"]=0
        rows.append((p,f))
    cols=sorted({c for _,f in rows for c in f})
    X=np.array([[f.get(c,np.nan) for c in cols] for _,f in rows],float)
    return [p for p,_ in rows], cols, X
