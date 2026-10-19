import json, statistics as st
tape=json.load(open("/root/mirror/his_tape.json"))
d500=json.load(open("/root/last500/his_500.json"))
tb={r["mint"]:r for r in tape}
M={}
for r in d500:
    rec=dict(r); t=tb.get(r["mint"])
    if t:
        rec["realized_sol"]=t.get("realized_sol")
        if t.get("peak_r"): rec["peak_r"]=max(rec.get("peak_r") or 0,t["peak_r"])
    M[r["mint"]]=rec
recs=[r for r in M.values() if r.get("peak_r")]
N=len(recs)
def runner(r): return r["peak_r"]>=1.5
def dump(r): return r["peak_r"]<1.1
RUN=[r for r in recs if runner(r)]; DUMP=[r for r in recs if dump(r)]
ov=[r for r in recs if r.get("realized_sol") is not None]
base_pnl=st.mean([r["realized_sol"] for r in ov])
print("BASELINE: N=%d runners=%d dumps=%d  overlap-pnl n=%d mean=%+.4f tot=%+.2f"%(
    N,len(RUN),len(DUMP),len(ov),base_pnl,sum(r["realized_sol"] for r in ov)))
print()

def test(name, keep):
    kept=[r for r in recs if keep(r)]
    if not kept: print(name,"keeps 0"); return
    kr=sum(1 for r in kept if runner(r)); kd=sum(1 for r in kept if dump(r))
    rr=sum(1 for r in RUN if keep(r)); dd=sum(1 for r in DUMP if keep(r))
    kov=[r for r in kept if r.get("realized_sol") is not None]
    pnl=st.mean([r["realized_sol"] for r in kov]) if kov else 0
    tot=sum(r["realized_sol"] for r in kov)
    print("%-42s keep=%d(%.0f%%) RUNretain=%.1f%% DUMPcut=%.1f%% keptPeak=%.3f pnl/trade=%+.4f(n=%d) totPnL=%+.2f"%(
        name,len(kept),100*len(kept)/N,100*rr/len(RUN),100*(len(DUMP)-dd)/len(DUMP),
        st.mean([r["peak_r"] for r in kept]),pnl,len(kov),tot))

print("RULE TESTS (keep = pass filter):")
test("no filter", lambda r:True)
test("dev_buy<=8", lambda r:(r.get("dev_buy") or 0)<=8)
test("n_trades_0_3>=3", lambda r:(r.get("n_trades_0_3") or 0)>=3)
test("n_trades_0_3>=5", lambda r:(r.get("n_trades_0_3") or 0)>=5)
test("n_trades_slot0>=1", lambda r:(r.get("n_trades_slot0") or 0)>=1)
test("cosnipers_slot0>=1", lambda r:(r.get("cosnipers_slot0") or 0)>=1)
test("cosnipers_slot0>=2", lambda r:(r.get("cosnipers_slot0") or 0)>=2)
test("n03>=3 AND dev<=8", lambda r:(r.get("n_trades_0_3") or 0)>=3 and (r.get("dev_buy") or 0)<=8)
test("n03>=3 AND dev<=8 AND n_trades_slot0>=1", lambda r:(r.get("n_trades_0_3") or 0)>=3 and (r.get("dev_buy") or 0)<=8 and (r.get("n_trades_slot0") or 0)>=1)
test("SKIP(n03<=2 OR dev>8)", lambda r:not((r.get("n_trades_0_3") or 0)<=2 or (r.get("dev_buy") or 0)>8))
test("cosnip>=2 AND dev<=8", lambda r:(r.get("cosnipers_slot0") or 0)>=2 and (r.get("dev_buy") or 0)<=8)
test("n03>=5 AND dev<=8", lambda r:(r.get("n_trades_0_3") or 0)>=5 and (r.get("dev_buy") or 0)<=8)
print()
# how many runners live in the skip zone (false negatives of aggressive rule)
print("Runners that WOULD be skipped by n03<=2:", sum(1 for r in RUN if (r.get("n_trades_0_3") or 0)<=2),"of",len(RUN))
print("Runners skipped by dev>8:", sum(1 for r in RUN if (r.get("dev_buy") or 0)>8))
print("Runners skipped by cosnipers_slot0==0:", sum(1 for r in RUN if (r.get("cosnipers_slot0") or 0)==0),"of",len(RUN))
