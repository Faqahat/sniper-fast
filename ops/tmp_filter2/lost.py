import json
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
RUN=[r for r in recs if r["peak_r"]>=1.5]
print("Total runners=%d"%len(RUN))
print("Runners with n_trades_0_3 < 4 (lost by demand>=4 filter):")
for r in sorted(RUN,key=lambda x:x.get("n_trades_0_3",0)):
    if (r.get("n_trades_0_3") or 0) < 4:
        print("  %s peak=%.2f n03=%s nsl0=%s cosnip=%s dev=%.2f cfee=%s hr=%s van=%s img=%s realPnL=%s"%(
            r["mint"][:8],r["peak_r"],r.get("n_trades_0_3"),r.get("n_trades_slot0"),
            r.get("cosnipers_slot0"),r.get("dev_buy") or 0,r.get("creator_fee_bps"),
            r.get("holder_reward"),r.get("vanilla"),r.get("has_image"),
            ("%+.3f"%r["realized_sol"]) if r.get("realized_sol") is not None else "NA"))
