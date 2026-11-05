"""per-block crosstab: python xqb.py KIND 'expr' ... (eligible = QUIET3-A T2 removed; chain-covered only)"""
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np
P,cols,X=ftab.table(); ci={c:i for i,c in enumerate(cols)}
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
BL={"r37":1,"r38":1,"r39":1,"r40":1,"r41":1,"r42":2}
class F(dict):
    def __getattr__(s,k): return s.get(k,float("nan"))
kind=sys.argv[1]
rows=[(p,F({c:X[i,ci[c]] for c in cols}),BL.get(p["run"],3 if p["run"]<="r48" else 4)) for i,p in enumerate(P) if not q3a(p) and (kind=="all" or p["kind"]==kind) and X[i,ci["cov"]]==1]
for ex in sys.argv[2:]:
    fn=eval("lambda f,p: "+ex); out=[]; T=[0,0,0,0.0,0.0,0.0]
    for b in (1,2,3,4):
        sel=[p for p,f,bb in rows if bb==b and fn(f,p)]; nb=sum(1 for p,f,bb in rows if bb==b)
        sv=sorted([-p["pnl"] for p in sel],reverse=True)
        fl=sum(p["cls"]=="flat" for p in sel); w=sum(p["cls"]=="win" for p in sel); ws=sum(p["pnl"] for p in sel if p["cls"]=="win")
        out.append(f"B{b} {len(sel)}/{nb} fl{fl} w{w} sv{sum(sv):+.2f}/{sum(sv[5:]):+.2f}")
        T[0]+=len(sel);T[1]+=fl;T[2]+=w;T[3]+=ws;T[4]+=sum(sv);T[5]+=sum(sv[5:])
    print(f"{ex[:60]:60s} | "+" | ".join(out)+f" || n{T[0]} fl{T[1]} w{T[2]}({T[3]:+.2f}) sv{T[4]:+.2f} w/o5 {T[5]:+.2f}")
