import json,statistics as st
res=json.load(open("trades.json"))
LAM=1e9
def pct(xs,p):
    if not xs: return None
    xs=sorted(xs); i=min(len(xs)-1,int(p*len(xs))); return xs[i]
rows=[]
for r in res:
    if r.get("error"): continue
    mint=r["mint"]; trades=r["trades"]; bslot=r["buy_slot"]
    buys=[t for t in trades if t["wtok"]>0]
    sells=[t for t in trades if t["wtok"]<0]
    if not buys: continue
    tok_bought=sum(t["wtok"] for t in buys)
    sol_in=-sum(t["wsol"] for t in buys)   # positive lamports spent
    # entry px from primary snipe buy (first buy, at buy_slot)
    pb=min(buys,key=lambda t:t["slot"])
    if pb["wtok"]==0 or pb["csol"]==0: continue
    px_entry=abs(pb["csol"])/abs(pb["wtok"])
    tok_sold=-sum(t["wtok"] for t in sells)
    sol_out=sum(t["wsol"] for t in sells)
    residual=tok_bought-tok_sold
    realized=sum(t["wsol"] for t in trades)/LAM   # net SOL flow (neg buys + pos sells), fees incl
    sell_recs=[]
    for s in sells:
        if s["wtok"]==0 or s["csol"]==0: continue
        px=abs(s["csol"])/abs(s["wtok"])
        sell_recs.append(dict(slot=s["slot"],dslot=s["slot"]-bslot,tok=-s["wtok"],
            frac=(-s["wtok"])/tok_bought, sol=s["wsol"]/LAM, px=px, r=px/px_entry))
    rows.append(dict(mint=mint,bslot=bslot,nbuys=len(buys),nsells=len(sells),
        tok_bought=tok_bought,tok_sold=tok_sold,residual=residual,
        resid_frac=residual/tok_bought if tok_bought else 0,
        sol_in=sol_in/LAM,sol_out=sol_out/LAM,px_entry=px_entry,
        realized=realized,sells=sell_recs,
        last_dslot=(max(s["slot"] for s in sells)-bslot) if sells else None))
json.dump(rows,open("rows.json","w"))
print("positions",len(rows))
print("no sells (never exited):",sum(1 for x in rows if x["nsells"]==0))
print("extra buys (nbuys>1):",sum(1 for x in rows if x["nbuys"]>1))
nsd=[x["nsells"] for x in rows]
print("nsells dist p25/med/p75/max",pct(nsd,.25),st.median(nsd),pct(nsd,.75),max(nsd))
rf=[x["resid_frac"] for x in rows]
print("residual_frac p50/p75/p90/max",round(st.median(rf),3),round(pct(rf,.75),3),round(pct(rf,.9),3),round(max(rf),3))
pnl=[x["realized"] for x in rows]
print("realized PnL/pos: mean",round(sum(pnl)/len(pnl),4),"median",round(st.median(pnl),4),"sum",round(sum(pnl),3))
print("win rate (realized>0):",round(sum(1 for p in pnl if p>0)/len(pnl),3))
