"""quick crosstab helper: python xq.py KIND 'expr' -> blocked stats FIT/CHECK per expression over eligible positions (f = feature dict, p = position)"""
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import ftab, numpy as np, math
P,cols,X=ftab.table()
ci={c:i for i,c in enumerate(cols)}
def q3a(p):
    if p["kind"]!="T2": return False
    v,q=p.get("v2") or {},p.get("quiet") or {}
    n,wd=v.get("n_120s"),q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n<=15 and wd<=3
class F(dict):
    def __getattr__(s,k):
        v=s.get(k,float("nan")); return v
def stats(sel):
    pn=np.array([p["pnl"] for p in sel]); cl=[p["cls"] for p in sel]
    if not len(sel): return "n0"
    return (f"n{len(sel)} fl{cl.count('flat')}({sum(p['pnl'] for p in sel if p['cls']=='flat'):+.2f}) sm{cl.count('small')} "
            f"win{cl.count('win')}({sum(p['pnl'] for p in sel if p['cls']=='win'):+.2f}) bl{cl.count('bigloss')} saved {-pn.sum():+.3f}")
kind=sys.argv[1]
rows=[(p,F({c:X[i,ci[c]] for c in cols})) for i,p in enumerate(P) if not q3a(p) and (kind=="all" or p["kind"]==kind)]
for ex in sys.argv[2:]:
    fn=eval("lambda f,p: "+ex)
    out=[]
    for nm,cond in (("FIT",lambda p:p["run"] in ftab.FIT),("CHECK",lambda p:p["run"] not in ftab.FIT)):
        sel=[p for p,f in rows if cond(p) and fn(f,p)]
        out.append(f"{nm} {stats(sel)}")
    print(f"{ex:50s} | "+" | ".join(out))
