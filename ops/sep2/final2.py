import json,statistics as st
from collections import Counter
rows=json.load(open("/root/sep2/rows_enriched.json"))
lab={r["mint"]:r for r in json.load(open("/root/sep2/labels.json"))}
for r in rows:
    L=lab.get(r["mint"],{}); r["peak"]=L.get("peak"); r["floor"]=L.get("floor")
def g(r,k,d=0):
    v=r.get(k); return d if v is None else v
WL=[r for r in rows if r["label"] in ("WIN","LOSE")]
kf=lambda r: g(r,"sol_cobuy_slot01")>=2.0
print("=== WINNERS SACRIFICED by sol_cobuy_slot01>=2.0 ===")
fn=[(r["mint"][:8],round(r["peak"],2),round(r["floor"],3),round(g(r,"sol_cobuy_slot01"),2),r.get("n_cobuy_slot01"),round(g(r,"dev_share_slot01",1),2),r.get("uri_host")) for r in WL if not kf(r) and r["label"]=="WIN"]
for x in sorted(fn,key=lambda z:z[1]): print("  mint=%s peak=%.2f floor=%.3f solcb=%.2f ncb=%s devshare=%.2f host=%s"%x)
print("peak_r of sacrificed winners:",sorted(round(x[1],2) for x in fn))
print("\n=== FULL POP (incl MID) applying sol_cobuy_slot01>=2.0 ===")
allk=[r for r in rows if kf(r)]; allr=[r for r in rows if not kf(r)]
print("KEEP:",dict(Counter(r["label"] for r in allk))," REJECT:",dict(Counter(r["label"] for r in allr)))
L=[r for r in rows if r["label"]=="LOSE"]; W=[r for r in rows if r["label"]=="WIN"]
print("\n=== PROFILES (median) ===")
print("LOSE: dev_share=%.2f sol_cobuy01=%.2f n_cobuy01=%d max_cobuy=%.2f"%(st.median(g(r,"dev_share_slot01",1) for r in L),st.median(g(r,"sol_cobuy_slot01") for r in L),st.median(g(r,"n_cobuy_slot01") for r in L),st.median(g(r,"max_cobuy_slot01") for r in L)))
print("WIN:  dev_share=%.2f sol_cobuy01=%.2f n_cobuy01=%d max_cobuy=%.2f"%(st.median(g(r,"dev_share_slot01",1) for r in W),st.median(g(r,"sol_cobuy_slot01") for r in W),st.median(g(r,"n_cobuy_slot01") for r in W),st.median(g(r,"max_cobuy_slot01") for r in W)))
print("\n=== serial-rug cluster host=md.sdfgsdfsdf.uk ===")
cl=[r for r in rows if r.get("uri_host")=="md.sdfgsdfsdf.uk"]
print("labels:",dict(Counter(r["label"] for r in cl)),"creators:",dict(Counter((r.get("creator") or "")[:6] for r in cl)),"funders:",dict(Counter((r.get("funder") or "none")[:6] for r in cl)))
print("their sol_cobuy01:",sorted(round(g(r,"sol_cobuy_slot01"),2) for r in cl))
print("\n=== how many of 19 losers does the cluster explain vs the demand rule ===")
print("losers with sol_cobuy01<2.0:",sum(1 for r in L if g(r,"sol_cobuy_slot01")<2.0),"/ 19")
print("losers from md.sdfgsdfsdf.uk:",sum(1 for r in L if r.get("uri_host")=="md.sdfgsdfsdf.uk"),"/ 19")
