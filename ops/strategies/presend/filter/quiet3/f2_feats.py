#!/usr/bin/env python3
"""QUIET3 step 3: arm-time QUIET signal VALUES recomputed causally from the raw recording for every window and every QUIET skip
(logic = quiet2/x3_features.py, which matched the engine's logged signals 2663/2664), plus stop-rule inputs (other wallets' trades
after the trigger per slot offset) and alternative whale-history values (6 h / 24 h / all-span, distinct vs total). Read-only."""
import json, collections, time
import numpy as np
D="/home/it/sniper-data/presend_quiet3"
COHORT="/home/it/sniper-data/overnight/sel/cohort_train.json"; FBOTS="/home/it/sniper/ops/strategies/presend/filter/fbots_frozen.json"
OURS={"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR","2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
t0=time.time()
C=np.load(f"{D}/chain.npz"); I=json.load(open(f"{D}/ids.json"))
S,IX,BT,BUY,SOL,TOK,VS,VT,MI,UI=(C[k] for k in ("s","i","bt","buy","sol","tok","vsol","vtok","mint","user"))
S=S.astype(np.int64); n=len(S)
mid={m:k for k,m in enumerate(I["mint"])}; uid={u:k for k,u in enumerate(I["user"])}
coh={uid[u] for u in json.load(open(COHORT)) if u in uid}; fb={uid[u] for u in json.load(open(FBOTS)) if u in uid}
ours={uid[u] for u in OURS if u in uid}
morder=np.argsort(MI,kind="stable"); mstart=np.searchsorted(MI[morder],np.arange(len(I["mint"])+1))
inv=np.empty(n,np.int64); inv[morder]=np.arange(n)
BT0=int(BT.min()); print("chain",n,"first bt",BT0,f"{time.time()-t0:.0f}s",flush=True)
m=(BUY==0)&(SOL>=300_000_000)&(VS<100_000_000_000)&(VT>TOK)
idx=np.nonzero(m)[0]
post=VS[idx].astype(float)/np.maximum(VT[idx].astype(float),1); pre=(VS[idx]+SOL[idx]).astype(float)/np.maximum((VT[idx]-TOK[idx]).astype(float),1)
idx=idx[~(post>0.92*pre)]
book=collections.defaultdict(list)
for r in idx.tolist():
    mk=int(MI[r]); e=mstart[mk+1]; p=int(inv[r]); s=int(S[r]); u=int(UI[r]); bs=set(); nb=0; q=p+1
    while q<e:
        rr=morder[q]
        if S[rr]>s+2: break
        if BUY[rr] and UI[rr]!=u: bs.add(int(UI[rr])); nb+=1
        q+=1
    book[u].append((s,int(BT[r]),len(bs),nb))
for v in book.values(): v.sort()
print("dumps",len(idx),f"{time.time()-t0:.0f}s",flush=True)

def feats(x):
    f={}; mk=mid.get(x["mint"]); wh=uid.get(x["whale"],-1)
    if mk is None: return {"ok":False}
    rows=morder[mstart[mk]:mstart[mk+1]]
    k=np.nonzero((S[rows]==x["slot"])&(IX[rows]==x["idx"])&(BUY[rows]==1))[0]
    if len(k)>1:
        kk=[a for a in k if UI[rows[a]]==wh]; k=kk or list(k)
    if len(k)==0: return {"ok":False}
    kt=int(k[0]); s0=x["slot"]; bt0=int(BT[rows[kt]]); R0=rows[:kt]
    sl=S[R0]; U=UI[R0]; B=BUY[R0]; Tk=TOK[R0].astype(np.int64)
    f["ok"]=True; f["bt"]=bt0
    f["since_last"]=int(s0-sl[-1]) if len(sl) else 9999
    bal=collections.defaultdict(int)
    for u,b,t in zip(U.tolist(),B.tolist(),Tk.tolist()): bal[u]+=t if b else -t
    seen=set(U.tolist())
    f["coh_hold"]=sum(1 for u in seen if u in coh and bal[u]>0); f["fb_n"]=len(seen&fb); f["n_prev"]=int(len(R0))
    f["coh_ever"]=len(seen&coh)
    H=book.get(wh,[])
    for tag,h in (("24",86400),("6",21600),("2",7200)):
        hist=[d for d in H if d[0]+2<s0 and d[1]>=bt0-h]
        f[f"wd{tag}"]=len(hist); f[f"wf{tag}"]=float(np.mean([d[2] for d in hist])) if hist else -1.0
    hist=[d for d in H if d[0]+2<s0 and d[1]>=bt0-86400]
    f["wf24_last"]=hist[-1][2] if hist else -1
    f["wf24_med"]=float(np.median([d[2] for d in hist])) if hist else -1.0
    f["hist_h"]=(bt0-BT0)/3600
    # stop rule inputs: other wallets' (not whale, not us) trades after the trigger, cumulative through slot s0+o
    RA=rows[kt+1:]; ua=UI[RA]; sa=S[RA]; oth=(ua!=wh)&~np.isin(ua,list(ours))
    f["oth"]=[int(((sa<=s0+o)&oth).sum()) for o in range(0,13)]
    return f

J=json.load(open(f"{D}/windows.json")); miss=0
for lst in (J["windows"],J["skips"]):
    for x in lst:
        x["c"]=feats(x); miss+= not x["c"]["ok"]
print("miss",miss,f"{time.time()-t0:.0f}s")
json.dump(J,open(f"{D}/windows_feats.json","w"))
