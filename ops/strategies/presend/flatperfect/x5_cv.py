"""leave-one-block-out CV over the DEV runs. Blocks: B1 r37-r41 | B2 r42 | B3 r43-r48 | B4 r49-r54. Eligible = QUIET3-A T2 removed.
Model scores -> block the top q (by the TRAIN blocks' score quantile). Prints per held-out block: blocked, flats, wins, saved, w/o top5."""
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
P,cols,X=ftab.table(); ci={c:i for i,c in enumerate(cols)}
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
BL={"r37":1,"r38":1,"r39":1,"r40":1,"r41":1,"r42":2}
blk=np.array([BL.get(p["run"],3 if p["run"]<="r48" else 4) for p in P])
DROP={"o_n","o_run_min","v_ring","wh_age","cov"}
SETS={"all":lambda c: True,
      "nochain":lambda c: c.startswith(("a_","q_","v_","h_","is_","t_","o_","s_")),
      "arm+pf":lambda c: c.startswith(("a_","q_","v_","h_","is_","t_","pf_")),
      "noown":lambda c: not c.startswith(("o_","s_")),
      "nopf":lambda c: not c.startswith("pf_")}
pn=np.array([p["pnl"] for p in P]); cl=np.array([p["cls"] for p in P])
nob=(X[:,ci["L_bot2"]]==0)
def tgt(name):
    return {"le0":(pn<=0).astype(int),"nobot":nob.astype(int),"nowin":(pn<0.025).astype(int),"flat":(cl=="flat").astype(int)}[name]
def run(kind,fset,tname,qs=(0.05,0.1,0.15,0.2,0.25),verbose=True,seed=0):
    el=np.array([not q3a(p) and (kind=="all" or p["kind"]==kind) for p in P])
    if tname=="nobot": el=el&~np.isnan(X[:,ci["L_bot2"]])
    fc=[j for j,c in enumerate(cols) if not c.startswith("L_") and c not in DROP and SETS[fset](c)]
    y=tgt(tname); res={q:[] for q in qs}; aucs=[]
    for b in (1,2,3,4):
        tr=el&(blk!=b); te=el&(blk==b)
        m=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1,random_state=seed)
        m.fit(X[tr][:,fc],y[tr]); s=m.predict_proba(X[:,fc])[:,1]
        # train-score quantile from inner OOF (2-fold on train) to avoid in-sample over-confidence
        idx=np.nonzero(tr)[0]; oof=np.empty(len(idx))
        h=len(idx)//2
        for a,bb in ((idx[:h],idx[h:]),(idx[h:],idx[:h])):
            mm=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1,random_state=seed)
            mm.fit(X[a][:,fc],y[a]); oof[np.searchsorted(idx,bb)]=mm.predict_proba(X[bb][:,fc])[:,1]
        aucs.append(roc_auc_score((pn[te]<=0).astype(int),s[te]))
        for q in qs:
            t=np.quantile(oof,1-q); B=te&(s>=t)
            sv=-pn[B]; sv_sorted=np.sort(sv)[::-1]
            res[q].append((B.sum(),(cl[B]=="flat").sum(),pn[B&(cl=="flat")].sum(),(cl[B]=="win").sum(),pn[B&(cl=="win")].sum(),sv.sum(),sv.sum()-sv_sorted[:5].sum(),te.sum()))
    if verbose:
        print(f"== {kind} {fset} target={tname} AUC(pnl<=0) per block", [round(a,3) for a in aucs])
        for q in qs:
            r=res[q]
            print(f"  q{q:.2f} " + " | ".join(f"B{b+1} n{x[0]}/{x[7]} fl{x[1]} w{x[3]}({x[4]:+.2f}) sv{x[5]:+.2f} w/o5 {x[6]:+.2f}" for b,x in enumerate(r)) + f" || tot sv {sum(x[5] for x in r):+.2f} w/o5 {sum(x[6] for x in r):+.2f}")
    return res,aucs
if __name__=="__main__":
    for kind in sys.argv[1].split(","):
        for fset in sys.argv[2].split(","):
            for t in sys.argv[3].split(","):
                run(kind,fset,t)
