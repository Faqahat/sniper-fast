import json, statistics as st, itertools
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
G=lambda r,f: (r.get(f) or 0)
def evaluate(pred,name):
    kept=[r for r in recs if pred(r)]
    if not kept: return None
    ret=sum(1 for r in kept if r["peak_r"]>=1.5)/nRUN
    rej=1-sum(1 for r in kept if r["peak_r"]<1.1)/nDUMP
    ko=[r for r in kept if r.get("realized_sol") is not None]
    kp=st.mean([r["realized_sol"] for r in ko]) if ko else None
    ks=sum(r["realized_sol"] for r in ko) if ko else None
    return dict(name=name,kept=len(kept),ret=ret,rej=rej,peak=st.mean([r["peak_r"] for r in kept]),pnl=kp,pnlsum=ks,novl=len(ko))
def show(res):
    if not res: return
    pnl=("mPnL=%+.4f sum=%+.2f"%(res["pnl"],res["pnlsum"])) if res["pnl"] is not None else "mPnL=NA"
    print("%-52s keep=%-3d ret=%5.1f%% rej=%5.1f%% peak=%.3f %s"%(res["name"],res["kept"],100*res["ret"],100*res["rej"],res["peak"],pnl))

# SOFT OVERRIDE: keep if n03>=T OR override
print("=== SOFT-OVERRIDE: keep if n_trades_0_3>=T OR <override> ===")
overrides=[
 ("cfee>0", lambda r: G(r,"creator_fee_bps")>0),
 ("dev>=2.5", lambda r: G(r,"dev_buy")>=2.5),
 ("dev>=3", lambda r: G(r,"dev_buy")>=3),
 ("hr>0", lambda r: G(r,"holder_reward")>0),
 ("vanilla==0", lambda r: G(r,"vanilla")==0),
 ("cfee>0|dev>=2.5", lambda r: G(r,"creator_fee_bps")>0 or G(r,"dev_buy")>=2.5),
 ("cfee>0|hr>0", lambda r: G(r,"creator_fee_bps")>0 or G(r,"holder_reward")>0),
 ("cfee>0|dev>=2.5|hr>0", lambda r: G(r,"creator_fee_bps")>0 or G(r,"dev_buy")>=2.5 or G(r,"holder_reward")>0),
]
for T in [2,3,4,5]:
    for onm,ofn in overrides:
        show(evaluate(lambda r,T=T,ofn=ofn: G(r,"n_trades_0_3")>=T or ofn(r), "n03>=%d OR %s"%(T,onm)))
    print()

# AND combos
print("=== AND combos ===")
andtests=[
 ("n03>=4 AND cosnip>=1", lambda r: G(r,"n_trades_0_3")>=4 and G(r,"cosnipers_slot0")>=1),
 ("n03>=4 AND nsl0>=1", lambda r: G(r,"n_trades_0_3")>=4 and G(r,"n_trades_slot0")>=1),
 ("n03>=3 AND dev>=0.3", lambda r: G(r,"n_trades_0_3")>=3 and G(r,"dev_buy")>=0.3),
 ("n03>=4 AND dev<10", lambda r: G(r,"n_trades_0_3")>=4 and G(r,"dev_buy")<10),
]
for nm,fn in andtests: show(evaluate(fn,nm))
print()

# OR combos (demand from either slot0 or 0_3) 
print("=== OR combos (recover via alt demand) ===")
ortests=[
 ("n03>=4 OR nsl0>=3", lambda r: G(r,"n_trades_0_3")>=4 or G(r,"n_trades_slot0")>=3),
 ("n03>=4 OR cosnip>=3", lambda r: G(r,"n_trades_0_3")>=4 or G(r,"cosnipers_slot0")>=3),
]
for nm,fn in ortests: show(evaluate(fn,nm))
print()
print("BASELINE no-filter: keep=%d ret=100%% rej=0%% mPnL=%+.4f sum=%+.2f"%(N,base_pnl,base_pnlsum))
