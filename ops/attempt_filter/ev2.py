import sys,json,statistics as st,random
sys.path.insert(0,"/root/econ_102"); import econ102 as E
random.seed(1)
pop=json.load(open("/root/profit_backtest/creates.json"))
TRAJ={t["mint"]:t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
ao=[r for r in json.load(open("/root/attempt_filter/att_outcomes.json")) if r.get("net_R") is not None]
def mean(xs): return sum(xs)/len(xs) if xs else float('nan')
def winr(xs): return sum(1 for x in xs if x>0)/len(xs) if xs else float('nan')
def ci(xs,n=2000):
    bs=sorted(mean([random.choice(xs) for _ in xs]) for _ in range(n)); return (bs[int(.025*n)],bs[int(.975*n)])
def outc(c):
    t=TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"): return None
    e=t["entry_px"]*E.ENTRY_MULT; s=[(a,b) for a,b in t["series"]]
    return (E.simulate(e,t["create_slot"],s,E.SHIP,0.5)[0], E.gross_only(e,t["create_slot"],s,E.SHIP))
def van(c): return (c.get("mayhem") or 0)==0 and (c.get("holder_reward") or 0)==0 and (c.get("cashback") or 0)==0
def bk(name,sel):
    xs=[];gs=[]
    for c in pop:
        if not sel(c): continue
        o=outc(c)
        if o: xs.append(o[0]);gs.append(o[1])
    c95=ci(xs) if xs else (0,0)
    print(f"{name:40} n={len(xs):4d} netR={mean(xs):+.4f} [{c95[0]:+.3f},{c95[1]:+.3f}] win={100*winr(xs):3.0f}% grosswin={100*winr(gs):3.0f}%")
print("EV buckets (econ102 shipped ladder, SIZE=0.5, favorable backtest regime):")
bk("ALL population (fee0 incl)",lambda c:True)
bk("PRODUCTION filter: wire-dev>=2 & fee0",lambda c:E.passes_shipped(c))
bk("  of which: wire SENTINEL (u64MAX)",lambda c:E.passes_shipped(c) and (c.get('dev_buy_wire') or 0)>=1e17)
bk("CURVE-TRUTH dev>=2 & fee0",lambda c:(c.get('dev_buy') or 0)>=2 and (c.get('creator_fee_bps') or 0)==0)
bk("CURVE dev>=1 & vanilla (near his median)",lambda c:(c.get('dev_buy') or 0)>=1 and van(c))
bk("CURVE dev>=0.5 & vanilla (his ~p25)",lambda c:(c.get('dev_buy') or 0)>=0.5 and van(c))
print(f"{'HIS ACTUAL ATTEMPTS (13h, built traj)':40} n={len(ao):4d} netR={mean([r['net_R'] for r in ao]):+.4f} {tuple(round(x,3) for x in ci([r['net_R'] for r in ao]))} win={100*winr([r['net_R'] for r in ao]):3.0f}% grosswin={100*winr([r['gross_R'] for r in ao]):3.0f}%")
# his attempts dev distribution + overlap
dv=sorted(r['dev_buy'] for r in ao if r.get('dev_buy') is not None)
print(f"\nhis attempts curve dev_buy: p25={dv[len(dv)//4]:.2f} med={dv[len(dv)//2]:.2f} p75={dv[3*len(dv)//4]:.2f}")
print(f"his attempts with curve dev>=2: {100*sum(1 for x in dv if x>=2)/len(dv):.0f}% ; dev>=0.5: {100*sum(1 for x in dv if x>=0.5)/len(dv):.0f}%")
print(f"his attempts vanilla: {100*sum(1 for r in ao if van(r))/len(ao):.0f}%")
