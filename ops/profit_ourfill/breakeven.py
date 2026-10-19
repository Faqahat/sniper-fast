#!/usr/bin/env python3
import sys, os, json
sys.path.insert(0,"/root/profit_ourfill"); import ourfill as O
os.environ["SIZE"]="0.165"; O.SIZE=0.165
SHIP={"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}

# backtest window
ROWS=O.load_backtest(); BT=[]
for c in ROWS:
    if c["creator_fee_bps"]!=0: continue
    dev=c["dev_buy"]
    if c.get("dev_buy_wire",0)>=1e17: dev=max(dev,2.0)
    if dev<2.0: continue
    t=c["traj"]; e,slot,path=O.ourfill_entry(t)
    BT.append((e,slot,path))
# paper window
PW=[]
for r in json.load(open("/root/profit_ourfill/paper_traj.json")):
    if r["dev_buy_wire_lamports"]/1e9<2.0 or not r["n"] or not r.get("entry_px"): continue
    traj={"create_slot":r["create_slot"],"entry_px":r["entry_px"],"series":[(s,p) for s,p in r["series"]]}
    e,slot,path=O.ourfill_entry(traj)
    if e: PW.append((e,slot,path))

def meanR(data,pump):
    O.PUMP_FEE=pump; O.BASE_FEE=0.000005 if pump>0 else 0.0; O.IMPACT_K=1.0
    rs=[O.simulate(e,s,p,SHIP)[0] for e,s,p in data]
    return sum(rs)/len(rs)

print("per-leg pump fee sweep (shipped ladder, our-fill, 0.165 SOL, incl curve impact):")
print(f"{'pump/leg':>9s} {'~round-trip':>11s} {'backtest meanR':>15s} {'paper-win meanR':>16s}")
for pf in [0.0,0.0025,0.005,0.0075,0.01,0.0125]:
    print(f"{pf*100:>7.2f}% {pf*200:>9.1f}% {meanR(BT,pf):>+15.4f} {meanR(PW,pf):>+16.4f}")
print("\npump.fun current protocol fee = 1.00%/leg (~2% round-trip) -> both windows NEGATIVE.")
print("break-even is at ~0.35-0.75%/leg; pump's own fee alone exceeds it.")
