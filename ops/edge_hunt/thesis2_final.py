#!/usr/bin/env python3
"""THESIS 2 FINAL - race-free migration entry. Reserve-ratio paths are correct.
The seed price is unfillable; the first on-chain swap already reflects the pump. A RACE-FREE trader
enters some slots AFTER migration at the then-current price, then exits. Measure NET forward return."""
import json, statistics as st
d=json.load(open("/root/edge_hunt/thesis2_pools_v2.json"))
ok=[r for r in d if r.get("path") and len(r["path"])>=3]
FEE_PS=0.003; SLIP=0.002   # PumpSwap ~0.3%/leg + small slip (cheaper than curve; task floor is 1%/leg)
def net(g,leg=FEE_PS,slip=SLIP): return g*(1-leg-slip/2)/(1+leg+slip/2)-1
def realpath(r):
    # drop points equal to seed open (the canonical seed read), keep real swaps
    op=r["open_px"]
    pts=[(sl,px) for sl,px in r["path"] if abs(px/op-1.0)>1e-6 or sl>r["mig_slot"]+2]
    return pts if pts else r["path"]
def first_from(pts,t):
    for sl,px in pts:
        if sl>=t: return px
    return None
def spot_at(pts,t):
    v=None
    for sl,px in pts:
        if sl<=t: v=px
        else: break
    return v
def maxin(pts,a,b):
    xs=[px for sl,px in pts if a<=sl<=b]
    return max(xs) if xs else None

print(f"tokens with usable AMM path: {len(ok)} (of 29 graduated; of 1141 launches = {len(ok)/1141*100:.1f}%)")
print("fee model: PumpSwap 0.3pct per leg + 0.2pct slip (realistic). breakeven gross ~%.4f\n"%(1/((1-FEE_PS-SLIP/2)/(1+FEE_PS+SLIP/2))))

def summ(xs,pct=True):
    xs=sorted(x for x in xs if x==x)
    if not xs: return "n=0"
    n=len(xs); m=sum(xs)/n; f=(100 if pct else 1)
    win=sum(1 for x in xs if x>0)/n
    return f"n={n} mean={m*f:+.1f} med={xs[n//2]*f:+.1f} win={win*100:.0f}% p25={xs[n//4]*f:+.1f} p75={xs[int(n*.75)]*f:+.1f} min={xs[0]*f:+.1f} max={xs[-1]*f:+.1f}"

print("=== RACE-FREE ENTRY (enter LAG slots after migration at then-current price), exit at fixed horizon ===")
for lag in [1,5,25,75]:
    print(f"\n LAG={lag} slots (~{lag*0.4:.1f}s after migration):")
    for h,w in [("+30s",75),("+1m",150),("+5m",750)]:
        gs=[]
        for r in ok:
            pts=realpath(r); mig=r["mig_slot"]
            e=first_from(pts,mig+lag)
            x=spot_at(pts,mig+lag+w)
            if e and x and e>0: gs.append(net(x/e))
        print(f"   exit {h}: {summ(gs)}")

print("\n=== BEST-CASE upper bound (look-ahead): enter +25sl, sell at 5m MAX ===")
gs=[]
for r in ok:
    pts=realpath(r); mig=r["mig_slot"]
    e=first_from(pts,mig+25); mx=maxin(pts,mig+25,mig+750)
    if e and mx and e>0: gs.append(net(mx/e))
print("  ", summ(gs))

print("\n=== per-token race-free (enter +25sl, exit +1m spot), NET@0.3%/leg ===")
for r in ok:
    pts=realpath(r); mig=r["mig_slot"]
    e=first_from(pts,mig+25); x=spot_at(pts,mig+25+150)
    g=net(x/e) if (e and x and e>0) else float('nan')
    print(f"  {r['mint'][:8]} entry={e if e else 0:.2e} exit1m={x if x else 0:.2e} net={g*100:+.1f}%")
