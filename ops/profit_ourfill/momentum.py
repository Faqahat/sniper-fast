#!/usr/bin/env python3
import sys, os, json, statistics as st
sys.path.insert(0,"/root/profit_ourfill"); import ourfill as O
os.environ["SIZE"]="0.165"; O.SIZE=0.165
ROWS=O.load_backtest()
DEV=2.0
FEAT=[]
for c in ROWS:
    if c["creator_fee_bps"]!=0: continue
    dev=c["dev_buy"]
    if c.get("dev_buy_wire",0)>=1e17: dev=max(dev,DEV)
    if dev<DEV: continue
    t=c["traj"]; e,slot,path=O.ourfill_entry(t)
    floor=t["entry_px"]
    peak=max([p for _,p in t["series"] if _> t["create_slot"]+1]+[e])
    FEAT.append({"f":c,"t":t,"e":e,"slot":slot,"path":path,"floor":floor,
        "vanilla":not(c["mayhem"] or c["holder_reward"] or c["cashback"]),
        "co":t["cosnipers"],"er":e/floor if floor else 1,
        "mom5":O.price_at(t,5)/e if e else 1,"rising2":O.price_at(t,2)>e,
        "peak_r":peak/e if e else 1})

def run(sub,E,pump,impact):
    O.PUMP_FEE=pump; O.BASE_FEE=0.000005 if pump>0 else 0.0; O.IMPACT_K=impact
    rs=[O.simulate(x["e"],x["slot"],x["path"],E)[0] for x in sub]
    return O.stats(rs)
def l(tag,S):
    if not S: print(f"  {tag:34s} n=0"); return
    print(f"  {tag:34s} n={S['n']:3d} grossORnet={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:3.0f}% drop2={S['mean_drop2']:+.4f}")

FLIP={"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}
HOLD={"derisk_frac":0.0,"ride_mult":1.1,"trail_frac":0.85,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":80}

subs=[("ALL",FEAT),("vanilla",[x for x in FEAT if x["vanilla"]]),
      ("co-sniped>=1",[x for x in FEAT if x["co"]>=1]),
      ("co-sniped>=3",[x for x in FEAT if x["co"]>=3]),
      ("rising@+2 (LOOKAHEAD)",[x for x in FEAT if x["rising2"]]),
      ("mom5>1.1 (LOOKAHEAD)",[x for x in FEAT if x["mom5"]>1.1])]

print("="*80)
print("GROSS (zero cost) ceiling by subset — shipped flip exit")
print("="*80)
for nm,sub in subs: l(nm, run(sub,FLIP,0.0,0.0))

print("\n"+"="*80)
print("NET (realistic: pump1%+base+impact, 0.165 SOL) — shipped flip exit")
print("="*80)
for nm,sub in subs: l(nm, run(sub,FLIP,0.01,1.0))

print("\n"+"="*80)
print("MOMENTUM-CONTINUATION: flip vs hold-for-2nd-leg, on rising subset (NET realistic)")
print("="*80)
rising=[x for x in FEAT if x["rising2"]]
print(" on rising@+2 subset (live-usable at fill):")
l("  flip (shipped)", run(rising,FLIP,0.01,1.0))
l("  hold (derisk0,ride1.1,cap80)", run(rising,HOLD,0.01,1.0))
mom=[x for x in FEAT if x["mom5"]>1.05]
print(" on mom5>1.05 subset (LOOKAHEAD, upper bound):")
l("  flip (shipped)", run(mom,FLIP,0.01,1.0))
l("  hold (derisk0,ride1.1,cap80)", run(mom,HOLD,0.01,1.0))

print("\n"+"="*80)
print("PEAK-r opportunity: perfect-exit gross (sell 100% at peak), by subset")
print("="*80)
for nm,sub in subs:
    if not sub: continue
    pr=[x["peak_r"]*(1-0.01)-(1+0.01) for x in sub]  # perfect exit minus 2% round-trip pump fee
    print(f"  {nm:34s} n={len(sub):3d} mean_peak_r={sum(x['peak_r'] for x in sub)/len(sub):.3f} perfect-exit_net(after2%)={sum(pr)/len(pr):+.4f} median={st.median(pr):+.4f}")

print("\n"+"="*80)
print("BREAK-EVEN pump fee: what per-leg pump fee makes ALL/vanilla flip break even? (gross=+0.0069 ALL)")
print("="*80)
for nm,sub in [("ALL",FEAT),("vanilla",[x for x in FEAT if x["vanilla"]])]:
    g=run(sub,FLIP,0.0,0.0)["mean"]
    print(f"  {nm}: zero-cost gross={g:+.4f}. Even at pump_fee=0 the net ceiling is this gross. Current pump=1%/leg.")
