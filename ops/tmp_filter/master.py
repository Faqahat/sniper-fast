import json, statistics as st
tape=json.load(open("/root/mirror/his_tape.json"))
d500=json.load(open("/root/last500/his_500.json"))
tb={r["mint"]:r for r in tape}
# master: one record per mint, prefer d500 create-features, attach outcome
M={}
for r in d500:
    m=r["mint"]; rec=dict(r); rec["peak_r"]=r.get("peak_r")
    t=tb.get(m)
    if t:
        rec["realized_sol"]=t.get("realized_sol"); rec["realized_R"]=t.get("realized_R")
        if t.get("peak_r"): rec["peak_r"]=max(rec.get("peak_r") or 0, t["peak_r"])
    M[m]=rec
# add tape-only mints
for m,t in tb.items():
    if m not in M:
        rec={"mint":m,"dev_buy":t.get("dev_buy_sol"),"buy_delta":t.get("delta"),
             "vanilla":1 if t.get("vanilla") else 0,"peak_r":t.get("peak_r"),
             "realized_sol":t.get("realized_sol"),"realized_R":t.get("realized_R"),
             "creator":t.get("creator"),"create_slot":t.get("create_slot")}
        M[m]=rec
recs=[r for r in M.values() if r.get("peak_r")]
N=len(recs)
print("MASTER records with peak_r:",N,"(of",len(M),"mints)")

def runner(r): return r["peak_r"]>=1.5
def dump(r):   return r["peak_r"]<1.1
nrun=sum(1 for r in recs if runner(r)); ndump=sum(1 for r in recs if dump(r))
print("RUNNER(peak>=1.5x): %d (%.1f%%)  DUMP(peak<1.1x): %d (%.1f%%)  mid: %d"%(
    nrun,100*nrun/N,ndump,100*ndump/N,N-nrun-ndump))
pr=[r["peak_r"] for r in recs]
print("peak_r dist: p25=%.3f p50=%.3f p75=%.3f p90=%.3f max=%.2f"%(
    sorted(pr)[N//4],st.median(pr),sorted(pr)[3*N//4],sorted(pr)[int(.9*N)],max(pr)))
print()

def bucket_report(name, keyfn, buckets):
    print("=== %s ==="%name)
    print("  %-14s  n    %%    runner%%  dump%%  meanPeak  medPeak"%"bucket")
    for lbl,lo,hi in buckets:
        b=[r for r in recs if lo<=(keyfn(r) if keyfn(r) is not None else -999)<hi]
        if not b: 
            print("  %-14s  0"%lbl); continue
        bn=len(b); rr=sum(1 for r in b if runner(r)); dd=sum(1 for r in b if dump(r))
        mp=st.mean([r["peak_r"] for r in b]); md=st.median([r["peak_r"] for r in b])
        print("  %-14s  %-4d %4.1f%% %5.1f%%  %5.1f%%  %.3f    %.3f"%(
            lbl,bn,100*bn/N,100*rr/bn,100*dd/bn,mp,md))
    print()

bucket_report("DEV_BUY (SOL)", lambda r:r.get("dev_buy"),
    [("0",0,0.001),("0-0.5",0.001,0.5),("0.5-1",0.5,1),("1-2",1,2),("2-3",2,3),("3-5",3,5),("5-8",5,8),("8+",8,1e9)])
bucket_report("COSNIPERS_slot0", lambda r:r.get("cosnipers_slot0"),
    [("0",0,1),("1",1,2),("2",2,3),("3-4",3,5),("5+",5,1e9)])
bucket_report("N_TRADES_slot0", lambda r:r.get("n_trades_slot0"),
    [("0",0,1),("1",1,2),("2",2,3),("3-4",3,5),("5+",5,1e9)])
bucket_report("N_TRADES_0_3", lambda r:r.get("n_trades_0_3"),
    [("0-1",0,2),("2",2,3),("3-4",3,5),("5-9",5,10),("10+",10,1e9)])
bucket_report("BUY_DELTA (his land vs create)", lambda r:r.get("buy_delta"),
    [("0 same-slot",0,1),("1",1,2),("2",2,3),("3+",3,1e9)])
