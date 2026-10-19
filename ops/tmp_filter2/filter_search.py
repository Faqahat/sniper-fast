import json, statistics as st, itertools
tape=json.load(open("/root/mirror/his_tape.json"))
h5=json.load(open("/root/last500/his_500.json"))
tb={r["mint"]:r for r in tape}
M={}
for r in h5:
    rec=dict(r); t=tb.get(r["mint"])
    if t:
        rec["realized_sol"]=t.get("realized_sol")
        rec["sol_in"]=t.get("sol_in")
        if t.get("peak_r"): rec["peak_r"]=max(rec.get("peak_r") or 0,t["peak_r"])
    M[r["mint"]]=rec
# add tape-only rows (have realized + peak but maybe no buy-time feats)
recs=[r for r in M.values() if r.get("peak_r") is not None]
N=len(recs)

def is_runner(r): return r["peak_r"]>=1.5
def is_dump(r): return r["peak_r"]<1.1
RUN=[r for r in recs if is_runner(r)]
DUMP=[r for r in recs if is_dump(r)]
nRUN,nDUMP=len(RUN),len(DUMP)
base_peak=st.mean([r["peak_r"] for r in recs])
ov=[r for r in recs if r.get("realized_sol") is not None]
base_pnl=st.mean([r["realized_sol"] for r in ov])
base_pnl_sum=sum(r["realized_sol"] for r in ov)
print("N=%d runners=%d dumps=%d base_peak=%.3f | overlap(P&L)=%d base_meanPnL=%+.4f sumPnL=%+.2f"%(
    N,nRUN,nDUMP,base_peak,len(ov),base_pnl,base_pnl_sum))
print()

def evaluate(pred,name):
    kept=[r for r in recs if pred(r)]
    if not kept: return None
    kr=sum(1 for r in kept if is_runner(r))
    kd=sum(1 for r in kept if is_dump(r))
    ret=kr/nRUN                      # runner retention
    rej=1-kd/nDUMP                   # dump rejection
    keptpeak=st.mean([r["peak_r"] for r in kept])
    ko=[r for r in kept if r.get("realized_sol") is not None]
    keptpnl=st.mean([r["realized_sol"] for r in ko]) if ko else None
    keptpnlsum=sum(r["realized_sol"] for r in ko) if ko else None
    return dict(name=name,kept=len(kept),ret=ret,rej=rej,keptpeak=keptpeak,
                keptpnl=keptpnl,keptpnlsum=keptpnlsum,novl=len(ko),kr=kr,kd=kd)

def show(res):
    if not res: return
    pnl = ("meanPnL=%+.4f sumPnL=%+.2f(n=%d)"%(res["keptpnl"],res["keptpnlsum"],res["novl"])) if res["keptpnl"] is not None else "meanPnL=NA"
    print("%-42s keep=%-3d ret=%5.1f%% rej=%5.1f%% peak=%.3f %s"%(
        res["name"],res["kept"],100*res["ret"],100*res["rej"],res["keptpeak"],pnl))

# ---- SINGLE FEATURE SWEEPS (>= threshold) ----
print("=== SINGLE-FEATURE: keep if feature >= T ===")
sweeps={
 "n_trades_0_3":[1,2,3,4,5,6,7,8,10,12,15],
 "n_trades_slot0":[1,2,3,4,5,6,8],
 "cosnipers_slot0":[1,2,3,4,5,6],
 "dev_buy":[0.1,0.3,0.5,0.8,1.0,1.5,2.0,3.0],
}
results=[]
for f,Ts in sweeps.items():
    for T in Ts:
        r=evaluate(lambda x,f=f,T=T: (x.get(f) is not None and x[f]>=T), "%s>=%g"%(f,T))
        if r: results.append(r); show(r)
    print()

# dev_buy==0 keep/reject both directions, flags
print("=== FLAG / BOOLEAN filters ===")
flagtests=[
 ("dev_buy>0", lambda x: (x.get("dev_buy") or 0)>0),
 ("dev_buy==0(keep only 0)", lambda x: (x.get("dev_buy") or 0)==0),
 ("has_image False", lambda x: not x.get("has_image")),
 ("creator_fee_bps>0", lambda x: (x.get("creator_fee_bps") or 0)>0),
 ("holder_reward>0", lambda x: (x.get("holder_reward") or 0)>0),
 ("vanilla==0", lambda x: (x.get("vanilla") or 0)==0),
]
for nm,fn in flagtests:
    show(evaluate(fn,nm))
print()
