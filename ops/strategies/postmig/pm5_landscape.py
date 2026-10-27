#!/usr/bin/env python3
# Where does post-migration money go? P&L of all post-migration round trips by token type and entry delay (MEASURED).
import json, numpy as np, collections, pickle, sys
OUT="/home/moiz/sniper-data/strategies/postmig"
SMS=212.0
def typ(t):
    if t["mayhem"]: return "mayhem"
    if t.get("age_s") is not None and t["age_s"]<=1.0: return "instant"
    return "fast" if (t.get("age_s") or 1e9)<300 else "slow"
def load(run):
    T=[json.loads(l) for l in open(f"{OUT}/{run}_tokens.jsonl")]
    st=pickle.load(open(f"{OUT}/{run}_strs.pkl","rb")); strs=st["strs"]; gid={x:j for j,x in enumerate(strs)}
    tr=dict(np.load(f"{OUT}/{run}_trips.npz")); du=dict(np.load(f"{OUT}/{run}_dumps.npz"))
    return T,strs,gid,tr,du
if __name__=="__main__":
    for run in sys.argv[1:] or ["R2","R3","R4"]:
        T,strs,gid,tr,du=load(run)
        tmap={gid[t["mint"]]:t for t in T if t["mint"] in gid}
        ty=np.array([typ(tmap[m]) if m in tmap else "?" for m in tr["mint"].tolist()])
        pnl=(tr["proceeds"]+tr["mark"]-tr["cost"]-tr["txcost"])/1e9
        d=tr["delay"]*SMS/1000
        bins=[(-1,0.25,"slot0"),(0.25,1,"<1s"),(1,10,"1-10s"),(10,60,"10-60s"),(60,600,"1-10m"),(600,3600,"10-60m"),(3600,1e9,">1h")]
        print(f"== {run}: trips {len(pnl)}  sum pnl {pnl.sum():.1f} SOL  (open {int(tr['open'].sum())})")
        for k in ["instant","fast","slow","mayhem"]:
            m=ty==k
            row=[]
            for lo,hi,nm in bins:
                mm=m&(d>lo)&(d<=hi)
                row.append(f"{nm}:{mm.sum()}/{pnl[mm].sum():+.0f}")
            print(f"  {k:8s} trips {m.sum():7d} pnl {pnl[m].sum():+8.1f}  vol {tr['cost'][m].sum()/1e9:9.0f}  | "+"  ".join(row))
        # curve-holder dumps
        dty=np.array([typ(tmap[m]) if m in tmap else "?" for m in du["mint"].tolist()])
        dp=(du["proceeds"]-du["curve_cost"]-du["txcost"])/1e9
        for k in ["instant","fast","slow","mayhem"]:
            m=dty==k
            print(f"  dumps {k:8s} n {m.sum():7d} proceeds {du['proceeds'][m].sum()/1e9:9.1f} curve_cost {du['curve_cost'][m].sum()/1e9:9.1f} pnl {dp[m].sum():+9.1f}")
