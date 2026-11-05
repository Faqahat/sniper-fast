"""does adding chain-wide PAPER triggers (nobot label) to training improve the nobot model on OUR positions? leave-one-block-out,
paper rows used only from the training blocks' slot ranges. Chain(+pf) features only (paper rows have no arm/own fields)."""
import sys, pickle; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import ftab, base, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
P,cols,X=ftab.table(); ci={c:i for i,c in enumerate(cols)}
PC=pickle.load(open(f"{base.OUT}/paper_chain.pkl","rb")); PI={p["key"]:p for p in pickle.load(open(f"{base.OUT}/paper_inputs.pkl","rb"))}
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
BL={"r37":1,"r38":1,"r39":1,"r40":1,"r41":1,"r42":2}
blk=np.array([BL.get(p["run"],3 if p["run"]<="r48" else 4) for p in P])
ts=np.array([p["trig_slot"] or 0 for p in P])
rng={b:(ts[blk==b].min()-3000, ts[blk==b].max()+3000) for b in (1,2,3,4)}
DROP={"o_n","o_run_min","v_ring","wh_age","cov"}
fcn=[c for c in cols if not c.startswith(("L_","a_","q_","v_","h_","is_","t_","o_","s_")) and c not in DROP]
ours={(L_m, s) for L_m, s in ((p["mint"], p["trig_slot"]) for p in P)}
sys.path.insert(0,"/home/moiz/sniper/ops/strategies/presend/flatsig"); import flib as FL
ours64={(FL.pk64(m), s) for m, s in ours}
pk=[k for k,v in PC.items() if v and "L_bot2" in v and (PI[k]["m64"],PI[k]["trig_slot"]) not in ours64]
XP=np.array([[PC[k].get(c,np.nan) for c in fcn] for k in pk]); yP=np.array([PC[k]["L_bot2"]==0 for k in pk]).astype(int)
sP=np.array([PI[k]["trig_slot"] for k in pk])
print("paper rows",len(pk),"nobot rate",yP.mean().round(3))
pn=np.array([p["pnl"] for p in P]); cl=np.array([p["cls"] for p in P]); lab=X[:,ci["L_bot2"]]
fidx=[ci[c] for c in fcn]
prm=dict(n_estimators=400,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1)
for kind in ("T2","rearm"):
    el=np.array([not q3a(p) and p["kind"]==kind for p in P])&~np.isnan(lab)
    y=(lab==0).astype(int)
    for mode in ("pos","pos+paper","paper"):
        a=[]; tot=[]
        for b in (1,2,3,4):
            tr=el&(blk!=b); te=el&(blk==b)
            pm=np.array([not (rng[b][0]<=s<=rng[b][1]) for s in sP])
            if mode=="pos": Xt,yt=X[tr][:,fidx],y[tr]
            elif mode=="paper": Xt,yt=XP[pm],yP[pm]
            else: Xt,yt=np.r_[X[tr][:,fidx],XP[pm]],np.r_[y[tr],yP[pm]]
            m=lgb.LGBMClassifier(**prm).fit(Xt,yt); s=m.predict_proba(X[:,fidx])[:,1]
            a.append(round(roc_auc_score(y[te],s[te]),3))
            # block top 10% / 15% by score quantile on the training positions
            for q in (0.10,0.15):
                t=np.quantile(s[tr],1-q); B=te&(s>=t); sv=-pn[B]
                tot.append((q,b,B.sum(),(cl[B]=="flat").sum(),(cl[B]=="win").sum(),sv.sum(),sv.sum()-np.sort(sv)[::-1][:5].sum()))
        print(kind,mode,"AUC nobot per block",a)
        for q in (0.10,0.15):
            r=[x for x in tot if x[0]==q]
            print(f"   q{q} "+" | ".join(f"B{x[1]} n{x[2]} fl{x[3]} w{x[4]} sv{x[5]:+.2f}/{x[6]:+.2f}" for x in r)+f" || tot {sum(x[5] for x in r):+.2f} w/o5 {sum(x[6] for x in r):+.2f}")
