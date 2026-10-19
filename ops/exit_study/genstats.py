import json,statistics as st
rows=json.load(open("rows2.json")); paths=json.load(open("paths.json"))
def pct(xs,p):
    xs=sorted([x for x in xs if x is not None]); 
    return xs[min(len(xs)-1,int(round(p*(len(xs)-1))))] if xs else None
def med(xs): xs=[x for x in xs if x is not None]; return st.median(xs) if xs else None
W=[r for r in rows if r["realized"]>0]; L=[r for r in rows if r["realized"]<=0]
S={}
S["n"]=len(rows); S["nW"]=len(W); S["nL"]=len(L)
S["his_sum"]=round(sum(r["realized"] for r in rows),3)
S["his_mean"]=round(sum(r["realized"] for r in rows)/len(rows),4)
S["his_win"]=round(len(W)/len(rows),3)
S["firstsell_frac_med_all"]=round(med([r["sells"][0]["frac"] for r in rows if r["sells"]]),3)
S["firstsell_frac_med_W"]=round(med([r["sells"][0]["frac"] for r in W if r["sells"]]),3)
S["firstsell_frac_med_L"]=round(med([r["sells"][0]["frac"] for r in L if r["sells"]]),3)
S["firstsell_dslot_med_W"]=med([r["sells"][0]["dslot"] for r in W if r["sells"]])
S["firstsell_dslot_med_L"]=med([r["sells"][0]["dslot"] for r in L if r["sells"]])
S["firstsell_r_med_W"]=round(med([r["sells"][0]["r"] for r in W if r["sells"]]),3)
S["firstsell_r_med_L"]=round(med([r["sells"][0]["r"] for r in L if r["sells"]]),3)
S["nsells_med_W"]=med([r["nsells"] for r in W]); S["nsells_med_L"]=med([r["nsells"] for r in L])
S["lastdslot_med_W"]=med([r["last_dslot"] for r in W]); S["lastdslot_p75_W"]=pct([r["last_dslot"] for r in W],.75); S["lastdslot_p90_W"]=pct([r["last_dslot"] for r in W],.9)
S["lastdslot_med_L"]=med([r["last_dslot"] for r in L]); S["lastdslot_p75_L"]=pct([r["last_dslot"] for r in L],.75)
S["peak_r_med_W"]=round(med([r["peak_r"] for r in W if r["peak_r"]]),3); S["peak_r_p75_W"]=round(pct([r["peak_r"] for r in W],.75),3); S["peak_r_p90_W"]=round(pct([r["peak_r"] for r in W],.9),3)
S["peak_r_med_L"]=round(med([r["peak_r"] for r in L if r["peak_r"]]),3)
tr=[r["wexit_r"]/r["peak_r"] for r in W if r.get("peak_r") and r["wexit_r"]]
S["trail_med_W"]=round(med(tr),3); S["trail_p25_W"]=round(pct(tr,.25),3)
S["cut_wexit_med_L"]=round(med([r["wexit_r"] for r in L if r["wexit_r"]]),3)
S["cut_wexit_p10_L"]=round(pct([r["wexit_r"] for r in L if r["wexit_r"]],.1),3)
chunks=[s["frac"] for r in rows if r["nsells"]>=2 for s in r["sells"][1:]]
S["ladder_chunk_med"]=round(med(chunks),3)
S["resid_any"]=sum(1 for r in rows if r["resid_frac"]>0.001)
json.dump(S,open("stats.json","w"),indent=1)
for k,v in S.items(): print(k,"=",v)
