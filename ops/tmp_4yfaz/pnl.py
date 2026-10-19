import json, statistics as st
t=json.load(open("/root/mirror/his_tape.json"))
BASE=365000e-9  # SOL per leg (priority+base)
FEE=0.01        # pump 1%/leg
def recompute(r):
    sol_in=r["sol_in"]              # treat as gross buy outlay
    net_curve=(sol_in-BASE)/(1+FEE) # SOL value in curve at buy
    sells=r.get("sells") or []
    gross_proceeds=sum(net_curve*s.get("frac",0)*s.get("r",0) for s in sells)
    net_proceeds=gross_proceeds*(1-FEE) - len(sells)*BASE
    return net_proceeds - sol_in
# compare recompute vs tape realized_sol
diffs=[]; mine=[]; tape=[]
for r in t:
    m=recompute(r); mine.append(m); tape.append(r["realized_sol"]); diffs.append(m-r["realized_sol"])
print("recompute: sum=%.2f mean=%.4f || tape realized_sol: sum=%.2f mean=%.4f || med|diff|=%.4f"%(
    sum(mine),st.mean(mine),sum(tape),st.mean(tape),st.median([abs(x) for x in diffs])))
