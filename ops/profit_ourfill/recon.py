#!/usr/bin/env python3
"""Reconcile the paper (+0.0187 R) vs fillvalue observed-late (-0.079 R) sign disagreement.
Run on ONE common sample (profit_backtest, shipped filter) so period is NOT a confound.
Decompose the gap into: (entry basis) x (cost model)."""
import sys, os, json, statistics as st
sys.path.insert(0, "/root/profit_backtest")
import backtest as B

CRE = json.load(open("/root/profit_backtest/creates.json"))
TRAJ = {t["mint"]: t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
ROWS = []
for c in CRE:
    t = TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"):
        continue
    ROWS.append({**c, "traj": t})

EXIT = {"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}
DEV_MIN = 2.0
def passes_shipped(c):
    if c["creator_fee_bps"] != 0: return False
    dev = c["dev_buy"]
    if c.get("dev_buy_wire",0) >= 1e17: dev = max(dev, DEV_MIN)
    return dev >= DEV_MIN
SAMPLE = [c for c in ROWS if passes_shipped(c)]

def price_at(c,k):
    C=c["create_slot"]; px=c["traj"]["entry_px"]
    for s,p in c["traj"]["series"]:
        if s<=C+k: px=p
        else: break
    return px
def path_after(c,k):
    C=c["create_slot"]; return [(s,p) for s,p in c["traj"]["series"] if s>C+k]
def observed_late(c):
    C=c["create_slot"]
    for s,p in c["traj"]["series"]:
        if s>=C+1: return p, s, [(s2,p2) for s2,p2 in c["traj"]["series"] if s2>s]
    return c["traj"]["entry_px"], C+1, []

def run(entry_mode, slip, fee):
    B.SLIP=slip; B.FEE_LEG=fee; B.SIZE=2.0
    rs=[]
    for c in SAMPLE:
        t=c["traj"]
        if entry_mode=="floor":
            e=t["entry_px"]; slot=t["create_slot"]; path=[(s,p) for s,p in t["series"]]
        elif entry_mode=="ourfill":   # +1: last trade <= C+1 (post-create-slot-bundle), the paper 'first readable' proxy
            e=price_at(c,1); slot=t["create_slot"]+1; path=path_after(c,1)
        elif entry_mode=="obslate":   # fillvalue: first trade at slot>=C+1
            e,slot,path=observed_late(c)
        net,_,_=B.simulate(e,slot,path,EXIT)
        rs.append(net)
    return rs

def S(rs):
    n=len(rs); mean=sum(rs)/n; win=sum(1 for x in rs if x>0)/n
    return f"n={n} mean={mean:+.4f} med={st.median(rs):+.4f} win={win*100:4.1f}% tot={sum(rs):+7.2f}"

print("="*90)
print(f"COMMON SAMPLE: profit_backtest, shipped filter (dev>=2, fee==0) -> n={len(SAMPLE)}")
print(f"shipped ladder: {EXIT}")
print("="*90)
print("\n--- entry-basis comparison: how different are the entry prices? ---")
import statistics
floor_px=[c["traj"]["entry_px"] for c in SAMPLE]
ourfill_px=[price_at(c,1) for c in SAMPLE]
obslate_px=[observed_late(c)[0] for c in SAMPLE]
r_ourfill=[a/b for a,b in zip(ourfill_px,floor_px)]
r_obslate=[a/b for a,b in zip(obslate_px,floor_px)]
same=sum(1 for a,b in zip(ourfill_px,obslate_px) if abs(a-b)<1e-18)
print(f"  our-fill(+1)/floor  : median {statistics.median(r_ourfill):.3f}x mean {sum(r_ourfill)/len(r_ourfill):.3f}x")
print(f"  obs-late/floor      : median {statistics.median(r_obslate):.3f}x mean {sum(r_obslate)/len(r_obslate):.3f}x")
print(f"  our-fill == obs-late entry px on {same}/{len(SAMPLE)} launches")

print("\n--- THE 2x2 DECOMPOSITION: entry basis (rows) x cost model (cols) ---")
costs=[("ZERO (paper)",0.0,0.0),("fee-only",0.0,0.0008),("8%slip+fee (fillvalue)",0.08,0.0008)]
for em,label in [("floor","FLOOR (best case)"),("ourfill","OUR-FILL (+1, paper proxy)"),("obslate","OBS-LATE (fillvalue)")]:
    print(f"\n[{label}]")
    for cl,slip,fee in costs:
        print(f"   {cl:26s}: {S(run(em,slip,fee))}")

print("\n--- key reconciliation cells ---")
print(f"PAPER reproduced (ourfill + ZERO)      : {S(run('ourfill',0.0,0.0))}")
print(f"FILLVALUE reproduced (obslate + 8%+fee): {S(run('obslate',0.08,0.0008))}")
