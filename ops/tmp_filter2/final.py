import json, statistics as st
tape=json.load(open("/root/mirror/his_tape.json"))
h5=json.load(open("/root/last500/his_500.json"))
tb={r["mint"]:r for r in tape}
M={}
for r in h5:
    rec=dict(r); t=tb.get(r["mint"])
    if t:
        rec["realized_sol"]=t.get("realized_sol")
        if t.get("peak_r"): rec["peak_r"]=max(rec.get("peak_r") or 0,t["peak_r"])
    M[r["mint"]]=rec
recs=[r for r in M.values() if r.get("peak_r") is not None]
N=len(recs)
RUN=[r for r in recs if r["peak_r"]>=1.5]; nRUN=len(RUN)
DUMP=[r for r in recs if r["peak_r"]<1.1]; nDUMP=len(DUMP)
ov=[r for r in recs if r.get("realized_sol") is not None]
base_pnl=st.mean([r["realized_sol"] for r in ov]); base_pnlsum=sum(r["realized_sol"] for r in ov)
G=lambda r,f:(r.get(f) or 0)
def ev(pred,name):
    kept=[r for r in recs if pred(r)]
    if not kept: return None
    ret=sum(1 for r in kept if r["peak_r"]>=1.5)/nRUN
    rej=1-sum(1 for r in kept if r["peak_r"]<1.1)/nDUMP
    ko=[r for r in kept if r.get("realized_sol") is not None]
    return dict(name=name,kept=len(kept),ret=ret,rej=rej,peak=st.mean([r["peak_r"] for r in kept]),
        pnl=st.mean([r["realized_sol"] for r in ko]) if ko else None,
        pnlsum=sum(r["realized_sol"] for r in ko) if ko else None,novl=len(ko))
cands=[
 ("A: n03>=4 OR vanilla==0", lambda r: G(r,"n_trades_0_3")>=4 or G(r,"vanilla")==0),
 ("B: n03>=3 OR vanilla==0", lambda r: G(r,"n_trades_0_3")>=3 or G(r,"vanilla")==0),
 ("C: n03>=5 OR vanilla==0 OR dev>=2.5", lambda r: G(r,"n_trades_0_3")>=5 or G(r,"vanilla")==0 or G(r,"dev_buy")>=2.5),
 ("D: (van0 OR n03>=4) AND n03>=1", lambda r: (G(r,"vanilla")==0 or G(r,"n_trades_0_3")>=4) and G(r,"n_trades_0_3")>=1),
 ("E: van0 OR n03>=4 OR dev>=3", lambda r: G(r,"vanilla")==0 or G(r,"n_trades_0_3")>=4 or G(r,"dev_buy")>=3),
 ("F: van0 OR hr>0 OR cfee>0 OR n03>=4", lambda r: G(r,"vanilla")==0 or G(r,"holder_reward")>0 or G(r,"creator_fee_bps")>0 or G(r,"n_trades_0_3")>=4),
 ("G: n03>=4 OR cfee>0 OR hr>0 OR dev>=2.5", lambda r: G(r,"n_trades_0_3")>=4 or G(r,"creator_fee_bps")>0 or G(r,"holder_reward")>0 or G(r,"dev_buy")>=2.5),
]
print("%-42s keep ret%%  rej%%  peak   mPnL      sumPnL   pnl_uplift"%"FILTER")
for nm,fn in cands:
    r=ev(fn,nm)
    up=(r["pnl"]/base_pnl-1)*100 if r["pnl"] else 0
    print("%-42s %-4d %5.1f %5.1f %.3f %+.4f %+.2f  %+.0f%%"%(nm,r["kept"],100*r["ret"],100*r["rej"],r["peak"],r["pnl"],r["pnlsum"],up))
print()
print("BASELINE keep=%d ret=100 rej=0 peak=%.3f mPnL=%+.4f sum=%+.2f"%(N,st.mean([r["peak_r"] for r in recs]),base_pnl,base_pnlsum))

# ===== CEILING ANALYSIS =====
print("\n=== CEILING: his realized P&L decomposition ===")
allp=[r["realized_sol"] for r in ov]
print("All %d overlap trades: sumP&L=%+.2f meanP&L=%+.4f median=%+.4f win%%=%.0f"%(
    len(ov),sum(allp),st.mean(allp),st.median(allp),100*sum(1 for x in allp if x>0)/len(ov)))
# P&L of runners vs dumps vs mid (his realized)
for lbl,fn in [("RUNNERS(peak>=1.5)",lambda r:r["peak_r"]>=1.5),("DUMPS(peak<1.1)",lambda r:r["peak_r"]<1.1),("MID",lambda r:1.1<=r["peak_r"]<1.5)]:
    b=[r["realized_sol"] for r in ov if fn(M[[k for k,v in M.items() if v is r][0]]) if False] # skip
for lbl,fn in [("RUNNERS",lambda r:r["peak_r"]>=1.5),("DUMPS",lambda r:r["peak_r"]<1.1),("MID",lambda r:1.1<=r["peak_r"]<1.5)]:
    b=[r["realized_sol"] for r in ov if fn(r)]
    if b: print("  %-9s n=%-3d sumP&L=%+.2f meanP&L=%+.4f median=%+.4f win%%=%.0f"%(lbl,len(b),sum(b),st.mean(b),st.median(b),100*sum(1 for x in b if x>0)/len(b)))
# KEY: his P&L on DUMPS - does he lose money on the tokens a filter would reject?
dumps_ov=[r["realized_sol"] for r in ov if r["peak_r"]<1.1]
print("\n  His realized P&L on DUMP tokens (peak<1.1): n=%d sum=%+.2f mean=%+.4f win%%=%.0f"%(
    len(dumps_ov),sum(dumps_ov),st.mean(dumps_ov),100*sum(1 for x in dumps_ov if x>0)/len(dumps_ov)))
print("  --> This is the MAX a perfect dump-filter could save a HOLD clone (he exits them near flat).")
