"""single-feature threshold rules on eligible DEV positions (r55's live filters applied: QUIET3-A T2 removed). FIT r37-r42, CHECK r43-r54."""
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np
P,cols,X=ftab.table()
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
kind=sys.argv[1]
el=np.array([not q3a(p) and (kind=="all" or p["kind"]==kind) for p in P])
pn=np.array([p["pnl"] for p in P]); cl=np.array([p["cls"] for p in P]); fit=np.array([p["run"] in ftab.FIT for p in P])
res=[]
for j,c in enumerate(cols):
    if c.startswith("L_") or c in ("o_n","o_run_min","v_ring","cov","wh_age"): continue
    v=X[:,j]
    F=el&fit&~np.isnan(v)
    if F.sum()<200: continue
    for q in (0.03,0.05,0.08,0.1,0.15,0.2,0.3):
        for side in ("lo","hi"):
            t=np.nanquantile(v[F], q if side=="lo" else 1-q)
            blk=(v<=t) if side=="lo" else (v>=t)
            blk=blk&~np.isnan(v)&el
            bf=blk&fit; bc=blk&~fit
            if bf.sum()<25: continue
            sf=-pn[bf].sum(); sc=-pn[bc].sum()
            res.append((sf,c,side,t,bf.sum(),(cl[bf]=="flat").sum(),(cl[bf]=="win").sum(),sc,bc.sum(),(cl[bc]=="flat").sum(),(cl[bc]=="win").sum(), (el&~fit&~np.isnan(v)).sum()))
res.sort(key=lambda r:-r[0])
print("kind",kind,"eligible FIT",(el&fit).sum(),"CHECK",(el&~fit).sum())
print("saved_FIT feat side thr | nF flF winF | saved_CHK nC flC winC (CHK covered)")
seen=set()
for r in res[:80]:
    print(f"{r[0]:+.3f} {r[1]:14s} {r[2]} {r[3]:.4g} | {r[4]} {r[5]} {r[6]} | {r[7]:+.3f} {r[8]} {r[9]} {r[10]} ({r[11]})")
