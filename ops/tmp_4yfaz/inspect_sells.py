import json
t=json.load(open("/root/mirror/his_tape.json"))
print("his_tape N=",len(t))
# how many have sells / realized_sol
hs=[r for r in t if r.get("nsells",0)>0]
print("with >=1 sell:",len(hs),"with realized_sol field:",sum(1 for r in t if r.get("realized_sol") is not None))
r=t[0]
print("keys:",list(r.keys()))
print("sample sol_in:",r.get("sol_in"),"realized_sol:",r.get("realized_sol"),"nsells:",r.get("nsells"),"sells:",r.get("sells"))
# check whether realized_sol already = proceeds-cost net
import statistics as st
rs=[r["realized_sol"] for r in t if r.get("realized_sol") is not None]
print("realized_sol present for",len(rs),"recs; sum=",round(sum(rs),3),"mean=",round(st.mean(rs),4))
# sells frac - fully closed?
fc=[r for r in t if r.get("sells") and sum(s.get("frac",0) for s in r["sells"])>=0.95]
print("fully-closed (sold>=95%):",len(fc))
# does his_500 have sells?
d=json.load(open("/root/last500/his_500.json"))
print()
print("his_500 N=",len(d),"keys have realized/sell?:", [k for k in d[0].keys() if "sell" in k.lower() or "realiz" in k.lower() or "pnl" in k.lower() or "net" in k.lower() or "proceed" in k.lower()])
