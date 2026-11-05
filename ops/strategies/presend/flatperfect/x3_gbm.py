"""GBM probes: FIT r37-r42 -> CHECK r43-r54 (eligible: QUIET3-A T2 removed). targets: win, pnl. Report AUC and blocked-set P&L at FIT-quantile cuts."""
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
P,cols,X=ftab.table()
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
DROP={"o_n","o_run_min","v_ring","wh_age","cov"}
groups=sys.argv[2].split(",") if len(sys.argv)>2 else ["all"]
def keep(c):
    if c.startswith("L_") or c in DROP: return False
    if "all" in groups: return True
    g={"arm":c.startswith(("a_","q_","v_","h_","is_","t_")),"own":c.startswith(("o_","s_")),"chain":not c.startswith(("a_","q_","v_","h_","is_","t_","o_","s_","pf_")),"pf":c.startswith("pf_")}
    return any(g[x] for x in groups)
fc=[j for j,c in enumerate(cols) if keep(c)]
kind=sys.argv[1]
el=np.array([not q3a(p) and (kind=="all" or p["kind"]==kind) for p in P])
pn=np.array([p["pnl"] for p in P]); cl=np.array([p["cls"] for p in P]); fit=np.array([p["run"] in ftab.FIT for p in P])
F=el&fit; C=el&~fit
Xf=X[:,fc]
for tgt in ("win","pnl","nonflat"):
    if tgt=="win": y=(pn>=0.025).astype(int)
    elif tgt=="nonflat": y=(cl!="flat").astype(int)
    else: y=np.clip(pn,-0.1,0.2)
    prm=dict(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1)
    m=(lgb.LGBMClassifier if tgt!="pnl" else lgb.LGBMRegressor)(**prm)
    m.fit(Xf[F],y[F])
    sc=(m.predict_proba(Xf)[:,1] if tgt!="pnl" else m.predict(Xf))
    # in-sample-free FIT score via 5-fold by time blocks
    idx=np.nonzero(F)[0]; oof=np.full(len(P),np.nan); k=5
    for i in range(k):
        te=idx[i*len(idx)//k:(i+1)*len(idx)//k]; tr=np.setdiff1d(idx,te)
        mm=(lgb.LGBMClassifier if tgt!="pnl" else lgb.LGBMRegressor)(**prm); mm.fit(Xf[tr],y[tr])
        oof[te]=(mm.predict_proba(Xf[te])[:,1] if tgt!="pnl" else mm.predict(Xf[te]))
    w=(pn>=0.025).astype(int)
    print(f"== {kind} target {tgt} groups {groups}: AUC(win) FIT-oof {roc_auc_score(w[F],oof[F]):.3f} CHECK {roc_auc_score(w[C],sc[C]):.3f}")
    for q in (0.05,0.1,0.15,0.2,0.3):
        t=np.quantile(oof[F],q)
        for nm,M,s in (("FIToof",F,oof),("CHECK",C,sc)):
            b=M&(s<=t)
            print(f"   q{q:.2f} {nm:6s} blocked {b.sum():4d} flats {(cl[b]=='flat').sum():3d} ({pn[b&(cl=='flat')].sum():+.2f}) wins {(cl[b]=='win').sum():3d} ({pn[b&(cl=='win')].sum():+.2f}) small {(cl[b]=='small').sum()} bigl {(cl[b]=='bigloss').sum()} saved {-pn[b].sum():+.3f}")
    imp=sorted(zip(m.feature_importances_,[cols[j] for j in fc]),reverse=True)[:15]
    print("   top feats",[c for _,c in imp])
