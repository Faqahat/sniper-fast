import json
from collections import Counter
d=json.load(open("/root/roundtrips.json")); rts=d["roundtrips"]
def perc(a,p):
    a=sorted(a); k=(len(a)-1)*p/100; f=int(k); c=min(f+1,len(a)-1); return a[f]+(a[c]-a[f])*(k-f)
sin=[r["sol_in"] for r in rts]
print("sol_in (buy, incl create+tip+fee) pcts:", {p:round(perc(sin,p),3) for p in (10,25,50,75,90)})
sout=[r["sol_out"] for r in rts]
print("sol_out pcts:", {p:round(perc(sout,p),3) for p in (10,25,50,75,90)})
# same-slot / same-block first sells
hsl=[r["hold_slots"] for r in rts if r["hold_slots"] is not None]
print("first-sell hold_slots==0:", sum(1 for x in hsl if x==0), "/", len(hsl), "(", round(100*sum(1 for x in hsl if x==0)/len(hsl),1),"%)")
print("hold_slots<=1:", round(100*sum(1 for x in hsl if x<=1)/len(hsl),1),"%  <=4:", round(100*sum(1 for x in hsl if x<=4)/len(hsl),1),"%")
# biggest winners and the hold / legs
tops=sorted(rts,key=lambda r:(r["sol_out"]-r["sol_in"]),reverse=True)[:6]
print("TOP winners (mint, pnl, mult, legs, hold_s, full_exit_s):")
for r in tops: print(" ",r["mint"][:8],round(r["sol_out"]-r["sol_in"],2),round(r["mult"],2),r["n_sells"],r["hold_s"],r["full_exit_s"])
worst=sorted(rts,key=lambda r:(r["sol_out"]-r["sol_in"]))[:6]
print("WORST losers:")
for r in worst: print(" ",r["mint"][:8],round(r["sol_out"]-r["sol_in"],2),round(r["mult"],2),r["n_sells"],r["hold_s"],r["full_exit_s"])
# winners full-exit time
win=[r for r in rts if r["mult"]>1]
print("winners full_exit_s pcts:", {p:round(perc([r["full_exit_s"] for r in win],p),1) for p in (25,50,75,90)})
print("winners n_sells median:", perc([r["n_sells"] for r in win],50), "losers n_sells median:", perc([r["n_sells"] for r in rts if r["mult"]<=1],50))
