import sys; sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np
P,cols,X=ftab.table()
pn=np.array([p["pnl"] for p in P]); cl=np.array([p["cls"] for p in P]); fit=np.array([p["run"] in ftab.FIT for p in P])
kind=sys.argv[1] if len(sys.argv)>1 else "T2"
km=np.array([(p["kind"]==kind) or kind=="all" for p in P])
print(kind,"FIT n",(fit&km).sum(),"mean",pn[fit&km].mean()*1e3,"CHECK n",(~fit&km).sum(),pn[~fit&km].mean()*1e3)
for j,c in enumerate(cols):
    if c.startswith("L_"): continue
    v=X[:,j]; m0=km&fit&~np.isnan(v)
    if m0.sum()<100: continue
    qs=np.unique(np.nanquantile(v[m0],[0,.1,.25,.5,.75,.9,1]))
    if len(qs)<3: continue
    out=[]
    for a,b in zip(qs[:-1],qs[1:]):
        last=b==qs[-1]
        s=lambda m: m&km&~np.isnan(v)&(v>=a)&((v<=b) if last else (v<b))
        F=s(fit); Cm=s(~fit)
        if F.sum()<15: continue
        out.append(f"[{a:.3g},{b:.3g}{']' if last else ')'} {F.sum()}:{pn[F].mean()*1e3:+.1f}/fl{(cl[F]=='flat').mean():.2f} | {Cm.sum()}:{(pn[Cm].mean()*1e3 if Cm.sum() else np.nan):+.1f}/fl{((cl[Cm]=='flat').mean() if Cm.sum() else np.nan):.2f}")
    print(f"{c:14s}", "  ".join(out))
