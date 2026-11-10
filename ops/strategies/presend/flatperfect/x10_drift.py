"""cohort drift: per ~6h window, distinct cohort/named wallets active, their buys, their share of 'dip buys' (buy <= 2 slots after a >=1 SOL sell)."""
import numpy as np, json, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatsig"); import flib as L
D=L.D; z=np.load(f"{D}/chain.npz"); S,M,U,B,SOL=z["slot"],z["mint"],z["user"],z["buy"],z["sol"]
n=len(S); gstart=np.r_[0,np.nonzero(M[1:]!=M[:-1])[0]+1]; gid=np.zeros(n,np.int64); gid[gstart[1:]]=1; gid=np.cumsum(gid)
big=(B==0)&(SOL>=1e9); OFF=np.int64(1)<<34; v=gid*OFF+np.where(big,S,0); acc=np.maximum.accumulate(v); lastbig=np.r_[0,(acc-gid*OFF)[:-1]]; lastbig[gstart]=0
dip=(B==1)&(lastbig>0)&(S-lastbig<=2)
COH=np.array(sorted({int(x) for x in json.load(open(f"{D}/cohort.json"))["ids"]}),dtype=np.uint64); NAM=np.array(sorted(L.NAMED64),dtype=np.uint64)
isF=np.isin(U,COH)|np.isin(U,NAM)
W=100000  # ~6h
for a in range(int(S.min())//W*W, int(S.max())+1, W):
    m=(S>=a)&(S<a+W)
    if m.sum()<1000: continue
    d=m&dip
    # heavy dip-buyers in this window (>= 40 dip buys)
    uu,cnt=np.unique(U[d],return_counts=True); heavy=uu[cnt>=40]
    hv=np.isin(U[d],heavy)
    print(L.pkt(int(z["bt"][np.argmax(m)])*1e9 if False else 0)[:0], a, "dipbuys",d.sum(),"cohort share",round((d&isF).sum()/max(d.sum(),1),3),
          "heavy wallets",len(heavy),"of which cohort",int(np.isin(heavy,np.r_[COH,NAM]).sum()),"heavy share",round(hv.mean(),3),
          "cohort active",len(np.unique(U[m&isF])))
