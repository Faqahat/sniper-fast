#!/usr/bin/env python3
import sys, os, json
sys.path.insert(0,"/root/profit_ourfill"); import ourfill as O

ROWS=O.load_backtest()
SHIP={"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}
DEV_MIN=2.0
def passes(c):
    if c["creator_fee_bps"]!=0: return False
    dev=c["dev_buy"]
    if c.get("dev_buy_wire",0)>=1e17: dev=max(dev,DEV_MIN)
    return dev>=DEV_MIN
SAMPLE=[c for c in ROWS if passes(c)]
print(f"shipped filter (dev>=2,fee==0): n={len(SAMPLE)} of {len(ROWS)}")

def runship(extra_slip=0.0):
    rs=[]
    for c in SAMPLE:
        e,slot,path=O.ourfill_entry(c["traj"])
        net,_,_=O.simulate(e,slot,path,SHIP,extra_slip=extra_slip)
        rs.append(net)
    return O.stats(rs)

def line(tag,S):
    print(f"  {tag:40s} n={S['n']} mean={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:4.1f}% tot={S['tot']:+7.2f} drop2={S['mean_drop2']:+.4f} top5sh={S['top5_share']*100:5.0f}%")

print("\n=== OUR-FILL (entry=create+1) baseline, shipped ladder, cost sweep (SIZE from env) ===")
for sz in ["0.01","0.165","2.0"]:
    os.environ["SIZE"]=sz
    # must re-eval module SIZE
    O.SIZE=float(sz)
    # cost variants via PUMP_FEE/IMPACT
    print(f"\n SIZE={sz} SOL:")
    # (a) zero cost (paper assumption)
    O.PUMP_FEE=0.0; O.BASE_FEE=0.0; O.IMPACT_K=0.0
    line("ZERO cost (=paper assumption)", runship())
    # (b) realistic: pump 1%/leg + base fee + mild curve impact
    O.PUMP_FEE=0.01; O.BASE_FEE=0.000005; O.IMPACT_K=1.0
    line("REALISTIC (pump1% + basefee + impact)", runship())
    # (c) conservative: pump 1% + 1% extra sell slip
    O.PUMP_FEE=0.01; O.BASE_FEE=0.000005; O.IMPACT_K=2.0
    line("CONSERVATIVE (+2x impact)", runship(extra_slip=0.005))
