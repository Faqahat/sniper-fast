import sys; sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import x5_cv as C, numpy as np, lightgbm as lgb
P,cols,X=C.P,C.cols,C.X
for kind in ("T2","rearm","all"):
    el=np.array([not C.q3a(p) and (kind=="all" or p["kind"]==kind) for p in P])&~np.isnan(X[:,C.ci["L_bot2"]])
    fc=[j for j,c in enumerate(cols) if not c.startswith("L_") and c not in C.DROP]
    y=C.tgt("nobot")
    m=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=8,min_child_samples=40,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5,verbose=-1,importance_type="gain")
    m.fit(X[el][:,fc],y[el])
    imp=sorted(zip(m.feature_importances_,[cols[j] for j in fc]),reverse=True)
    tot=sum(i for i,_ in imp)
    print(kind, [(c,round(i/tot,3)) for i,c in imp[:30]])
