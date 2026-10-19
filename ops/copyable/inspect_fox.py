import json, statistics as st, datetime as dt, sys
w=sys.argv[1]
T=json.load(open(f"/root/copyable/tapes/{w}.json"))
pos=[p for p in T["positions"] if p["sell_tok"]>0 and p["buy_sol"]>0]
print("closed positions:",len(pos))
print("%-12s %8s %8s %7s %8s %3s %3s"%("mint","buySOL","sellSOL","rmult","holdS","nB","nS"))
tot=0
for p in sorted(pos,key=lambda x:-(x["pnl_sol"])):
    print("%-12s %8.3f %8.3f %7.2f %8.0f %3d %3d"%(
        p["mint"][:10],p["buy_sol"],p["sell_sol"],(p["r_mult"] or 0),
        (p["hold_s"] or -1),p["n_buys"],p["n_sells"]))
    tot+=p["pnl_sol"]
print("sum pnl SOL",round(tot,3))
bs=[p["buy_sol"] for p in pos]
print("buy size SOL p25/med/p75:",round(sorted(bs)[len(bs)//4],2),round(st.median(bs),2),round(sorted(bs)[len(bs)*3//4],2))
hd=[p["hold_s"] for p in pos if p["hold_s"] is not None]
print("hold sec p25/med/p75:",sorted(hd)[len(hd)//4],st.median(hd),sorted(hd)[len(hd)*3//4] if hd else None)
bts=[t["bt"] for t in T["trades"] if t["bt"]]
print("span:",dt.datetime.utcfromtimestamp(min(bts)).isoformat(),"..",dt.datetime.utcfromtimestamp(max(bts)).isoformat())
print("n_sigs",T.get("n_sigs"),"n_succ",T.get("n_succ"))
