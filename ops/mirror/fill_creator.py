#!/usr/bin/env python3
"""FILL match (last30 clean rank/fill) + CREATOR precision/recall vs backtest universe."""
import json, statistics as st
from collections import Counter
def pct(xs,p):
    xs=sorted(xs); return xs[min(len(xs)-1,int(round(p*(len(xs)-1))))]

print("="*70); print("FILL MATCH  (his actual fill-vs-floor + block rank, last30 clean n=30)"); print("="*70)
f2=json.load(open("/root/last30/fill2.json"))
fr=[r["fill_ratio_xslot"] for r in f2 if r.get("fill_ratio_xslot")]
rk=[r["his_rank_xslot"] for r in f2 if r.get("his_rank_xslot")]
bi=[r["his_blkidx"] for r in f2 if r.get("his_blkidx") is not None]
print(f"his fill_vs_floor: n={len(fr)} p25={pct(fr,.25):.3f} med={st.median(fr):.3f} p75={pct(fr,.75):.3f} max={max(fr):.3f}")
print(f"  at-floor(<=1.03): {sum(1 for x in fr if x<=1.03)}/{len(fr)}   ramp(>1.2): {sum(1 for x in fr if x>1.2)}/{len(fr)}")
print(f"his cross-slot rank among ext buyers: med={st.median(rk):.1f} rank1={sum(1 for x in rk if x==1)}/{len(rk)} rank<=3={sum(1 for x in rk if x<=3)}/{len(rk)}")
print(f"his block index (position in slot): med={st.median(bi):.0f} p25={pct(bi,.25):.0f} p75={pct(bi,.75):.0f}")
print("OUR modeled fill = floor*1.02 (3M priority, econ_102 probe). Comparison:")
print("  where he is at floor (rank<=3, ~{}%): our 1.02x ~= his fill -> PARITY (we are ~2% above floor, he ~0%)".format(round(100*sum(1 for x in fr if x<=1.03)/len(fr))))
print("  where he paid a ramp (contested): to beat it we must out-rank him; as a peer sniper we cannot -> our realistic fill ~= his fill, NOT better")
print("  => FILL is ~parity same-slot; it is not the source of the gap. (Only if we out-speed him do we gain; if slower we pay the ramp he avoided.)")

print("\n"+"="*70); print("CREATOR / DEV SELECTION  — does 'his creators' reproduce his picks & PnL?"); print("="*70)
tape=json.load(open("/root/mirror/his_tape.json"))
crc=Counter(t["creator"] for t in tape if t["creator"])
repeat={c for c,k in crc.items() if k>=2}
nwith=sum(1 for t in tape if t["creator"])
cov=sum(1 for t in tape if t["creator"] in repeat)
print(f"his 200 positions: {len(crc)} distinct creators; {len(repeat)} recur (>=2); recurrence covers {cov}/{nwith} = {100*cov/nwith:.0f}% of his picks")
print(f"  => RECALL CEILING of ANY creator-recurrence rule = {100*cov/nwith:.0f}% (the other {100-100*cov/nwith:.0f}% are one-shot devs, unknowable pre-buy)")

# attempt universe: his broader attempt set creators (landed+failed)
af=json.load(open("/root/attempt_filter/attempted_feat.json"))
afc=Counter(r["creator"] for r in af if r.get("creator"))
af_repeat={c for c,k in afc.items() if k>=2}
print(f"his ATTEMPT universe (190 mints, landed+failed): {len(afc)} creators, {len(af_repeat)} recur; "
      f"union of his recurring devs (positions ∪ attempts): {len(repeat|af_repeat)}")

# PRECISION on backtest universe: of launches by his favored creators in a market window, how many did he buy?
cre=json.load(open("/root/profit_backtest/creates.json"))
lo,hi=min(c["create_slot"] for c in cre),max(c["create_slot"] for c in cre)
his_mints=set(t["mint"] for t in tape)
his_in_win=set(t["mint"] for t in tape if lo<=t["buy_slot"]<=hi)
fav=repeat|af_repeat  # his favored dev set (defined from his own history)
uni_fav_launches=[c for c in cre if c.get("creator") in fav]
uni_fav_he_bought=[c for c in uni_fav_launches if c["mint"] in his_mints]
print(f"\nBacktest market universe: {len(cre)} launches by {len(set(c.get('creator') for c in cre))} creators, slots {lo}-{hi}")
print(f"  launches in universe BY his favored devs: {len(uni_fav_launches)}")
print(f"  of those, he actually bought: {len(uni_fav_he_bought)}  -> creator-rule PRECISION in-universe = {100*len(uni_fav_he_bought)/max(1,len(uni_fav_launches)):.0f}%")
print(f"  (i.e. his favored devs ALSO launch many tokens he skips -> creator identity alone is a weak selector)")

# PnL: repeat-dev vs one-shot-dev positions (does dev identity carry outcome alpha?)
rows={r["mint"]:r for r in json.load(open("/root/exit_study/rows2.json"))}
def grp(ts):
    r=[rows[t["mint"]]["realized"] for t in ts if t["mint"] in rows]
    pk=[t["peak_r"] for t in ts if t["peak_r"]]
    return f"n={len(r)} total={sum(r):+.2f} meanR_sol/pos={sum(r)/len(r):+.4f} win={sum(1 for x in r if x>0)/len(r):.2f} med_peak={st.median(pk):.3f} >=2x:{sum(1 for x in pk if x>=2)}"
print(f"\nDOES 'WHICH DEV' CARRY ALPHA?  his positions split by dev recurrence:")
print(f"  REPEAT-dev positions:   {grp([t for t in tape if t['creator'] in repeat])}")
print(f"  ONE-SHOT-dev positions: {grp([t for t in tape if t['creator'] and t['creator'] not in repeat])}")
print("  verdict: if repeat-dev lanes were his edge they'd show higher mean/peak; they do NOT -> his edge is NOT 'which devs'")
