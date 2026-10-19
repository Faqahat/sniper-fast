import json
t=json.load(open("/root/mirror/his_tape.json"))
d=json.load(open("/root/last500/his_500.json"))
tm={r["mint"]:r for r in t}
dm={r["mint"]:r for r in d}
common=set(tm)&set(dm)
print("common mints:",len(common))
ratios=[]
for m in list(common)[:12]:
    a=tm[m]; b=dm[m]
    # a.his_fill_px native (base units e-05); b.entry_px (SOL/whole e-08)
    r=a["his_fill_px"]/b["entry_px"]
    ratios.append(r)
    print("tape_fillpx=%.4g  500_entrypx=%.4g  ratio=%.1f  tape_dev=%.3f 500_dev=%.3f"%(a["his_fill_px"],b["entry_px"],r,a.get("dev_buy_sol",0),b.get("dev_buy",0)))
import statistics as st
if ratios: print("median tape/500 px ratio = %.1f (expect 1000 if only *1e3 scaling)"%st.median(ratios))
