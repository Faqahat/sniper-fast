"""how predictable is 'no follower bot within 2 slots after our fill' (L_bot2==0) at arm time? FIT->CHECK AUC by feature group."""
import sys; sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
P,cols,X=ftab.table(); ci={c:i for i,c in enumerate(cols)}
DROP={"o_n","o_run_min","v_ring","wh_age","cov"}
lab=X[:,ci["L_bot2"]]
pn=np.array([p["pnl"] for p in P]); fit=np.array([p["run"] in ftab.FIT for p in P])
for kind in ("T2","rearm","all"):
    km=np.array([kind=="all" or p["kind"]==kind for p in P])&~np.isnan(lab)
    y=(lab==0).astype(int); F=km&fit; C=km&~fit
    for grp,pref in (("arm",("a_","q_","v_","h_","is_","t_")),("own",("o_","s_")),("pf",("pf_",)),("all",None)):
        fc=[j for j,c in enumerate(cols) if not c.startswith("L_") and c not in DROP and (pref is None or c.startswith(pref) or (grp=="arm" and False))]
        if grp=="chain": pass
        m=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1)
        m.fit(X[F][:,fc],y[F]); s=m.predict_proba(X[:,fc])[:,1]
        print(kind,grp,"base noBot FIT",y[F].mean().round(3),"CHECK",y[C].mean().round(3),"AUC CHECK",round(roc_auc_score(y[C],s[C]),3), "AUC pnl<=0 CHECK", round(roc_auc_score((pn[C]<=0).astype(int),s[C]),3))
    fc=[j for j,c in enumerate(cols) if not c.startswith("L_") and c not in DROP and not c.startswith(("a_","q_","v_","h_","is_","t_","o_","s_","pf_"))]
    m=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1)
    m.fit(X[F][:,fc],y[F]); s=m.predict_proba(X[:,fc])[:,1]
    print(kind,"chain","AUC CHECK",round(roc_auc_score(y[C],s[C]),3))
