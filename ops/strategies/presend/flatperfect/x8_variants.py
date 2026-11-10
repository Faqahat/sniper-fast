"""variants of the nobot model, leave-one-block-out, bagged over 3 seeds; threshold = (1-q) quantile of the TRAIN blocks' OOF scores.
Prints per kind: tot saved, w/o5, blocks with saved>0, flats/wins blocked."""
import sys; sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np, lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
P,cols,X=ftab.table(); ci={c:i for i,c in enumerate(cols)}
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
BL={"r37":1,"r38":1,"r39":1,"r40":1,"r41":1,"r42":2}
blk=np.array([BL.get(p["run"],3 if p["run"]<="r48" else 4) for p in P])
DROP={"o_n","o_run_min","v_ring","wh_age","cov"}
pn=np.array([p["pnl"] for p in P]); cl=np.array([p["cls"] for p in P]); kd=np.array([p["kind"] for p in P])
lab=X[:,ci["L_bot2"]]; y=(lab==0).astype(int)
ELIG=np.array([not q3a(p) for p in P])&~np.isnan(lab)
ALLF=[c for c in cols if not c.startswith("L_") and c not in DROP]
def mk(model,seed):
    if model=="gbm": return lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1,random_state=seed)
    if model=="gbm_s": return lgb.LGBMClassifier(n_estimators=200,learning_rate=0.03,num_leaves=4,min_child_samples=60,subsample=0.8,subsample_freq=1,colsample_bytree=0.8,reg_lambda=10,verbose=-1,random_state=seed)
    if model=="lr": return make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),LogisticRegression(C=0.05,max_iter=2000))
def fitpred(model,Xtr,ytr,Xte,seeds=(0,1,2)):
    ss=[]
    for sd in (seeds if model!="lr" else (0,)):
        m=mk(model,sd).fit(Xtr,ytr); ss.append(m.predict_proba(Xte)[:,1])
    return np.mean(ss,0)
def cv(feats,kinds,model="gbm",pooled=False,qs=(0.1,0.15,0.2,0.25)):
    fj=[ci[c] for c in feats]
    out={}
    for kind in kinds:
        res={q:[] for q in qs}
        for b in (1,2,3,4):
            trm=ELIG&(blk!=b)&((kd==kind) if not pooled else True); tem=ELIG&(blk==b)&(kd==kind)
            Xa=X[:,fj]
            s=fitpred(model,Xa[trm],y[trm],Xa)
            idx=np.nonzero(trm)[0]; oof=np.empty(len(idx)); h=len(idx)//2
            for a,bb in ((idx[:h],idx[h:]),(idx[h:],idx[:h])):
                oof[np.searchsorted(idx,bb)]=fitpred(model,Xa[a],y[a],Xa[bb],seeds=(0,))
            kk=(kd[idx]==kind)
            for q in qs:
                t=np.quantile(oof[kk],1-q); B=tem&(s>=t); sv=-pn[B]
                res[q].append((B.sum(),(cl[B]=="flat").sum(),(cl[B]=="win").sum(),pn[B&(cl=="win")].sum(),sv.sum(),sv.sum()-np.sort(sv)[::-1][:5].sum()))
        out[kind]=res
    return out
def show(name,out):
    for kind,res in out.items():
        line=[]
        for q,r in res.items():
            line.append(f"q{q:.2f}: n{sum(x[0] for x in r)} fl{sum(x[1] for x in r)} w{sum(x[2] for x in r)}({sum(x[3] for x in r):+.2f}) sv{sum(x[4] for x in r):+.2f} w/o5 {sum(x[5] for x in r):+.2f} pos{sum(x[4]>0 for x in r)}/4 w5pos{sum(x[5]>=0 for x in r)}/4")
        print(f"{name:28s} {kind:5s} | "+" | ".join(line), flush=True)
if __name__=="__main__":
    import itertools
    PF=[c for c in ALLF if c.startswith("pf_")]
    TOP_T2=["pf_n","wh_q50","top1","bot_hold_pct","pf_bsol","wh_q10","pf_bfail","a_pct","bot_w_n","a_sol","pf_vmax","wh_mints","bot_tr_n","o_lastwin_min","q_wh_fol","top5","nbuyer_100","nbuyer_20","g_bsol_1m","o_mean20"]
    TOP_RE=["pf_bfail","pf_bot_buys","pf_vmax","bfail_pre","o_mean5","o_sum_60m","g_buys_1m","fail_all_pre","g_core_last","pf_slots","o_win_60m","pf_bsol","wh_q10","o_fol5","wh_n","wh_q50","g_bfail_30m","s_mean_15m","s_mean30","dd_ath"]
    show("gbm all sep",cv(ALLF,("T2","rearm")))
    show("gbm all pooled",cv(ALLF,("T2","rearm"),pooled=True))
    show("gbm_s all sep",cv(ALLF,("T2","rearm"),model="gbm_s"))
    show("lr all sep",cv(ALLF,("T2","rearm"),model="lr"))
    show("gbm top20 T2",cv(TOP_T2,("T2",)))
    show("gbm top20 RE",cv(TOP_RE,("rearm",)))
    show("gbm noPF sep",cv([c for c in ALLF if not c.startswith("pf_")],("T2","rearm")))
    show("gbm noOWN sep",cv([c for c in ALLF if not c.startswith(("o_","s_"))],("T2","rearm")))
