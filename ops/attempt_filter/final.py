import sys,json,statistics as st
from collections import Counter
sys.path.insert(0,"/root/econ_102"); import econ102 as E
import random; random.seed(1)

ext=json.load(open("/root/attempt_filter/ext_buys.json"))["buys"]
ao=json.load(open("/root/attempt_filter/att_outcomes.json"))
pop=json.load(open("/root/profit_backtest/creates.json"))
TRAJ={t["mint"]:t for t in json.load(open("/root/profit_backtest/trajectories.json"))}

def mean(xs): return sum(xs)/len(xs) if xs else float('nan')
def winr(xs): return sum(1 for x in xs if x>0)/len(xs) if xs else float('nan')
def boot_ci(xs,f,n=2000):
    if not xs: return (float('nan'),float('nan'))
    bs=sorted(f([random.choice(xs) for _ in xs]) for _ in range(n))
    return (bs[int(0.025*n)],bs[int(0.975*n)])

print("="*72)
print("CREATOR RECURRENCE OVER ~4 DAYS (his full buy history)")
print("="*72)
# distinct mints with creator
emints={}
for b in ext:
    if b.get("creator") and b.get("mint") not in emints:
        emints[b["mint"]]={"creator":b["creator"],"slot":b.get("create_slot") or b["slot"]}
rows=sorted(emints.values(),key=lambda r:r["slot"] or 0)
print(f"ext buys={len(ext)}  distinct mints w/creator={len(rows)}  slot span {rows[0]['slot']}..{rows[-1]['slot']}")
cc=Counter(r["creator"] for r in rows)
print(f"distinct creators={len(cc)}  mints/creator={len(rows)/len(cc):.2f}")
rep={c:n for c,n in cc.items() if n>1}
print(f"creators hit >1x: {len(rep)}  covering {sum(rep.values())}/{len(rows)} mints = {100*sum(rep.values())/len(rows):.0f}%")
# sequential repeat fraction
seen=set(); r1=0
for r in rows:
    if r["creator"] in seen: r1+=1
    seen.add(r["creator"])
print(f"REPEAT-creator fraction (seen earlier in his stream, 4d): {r1}/{len(rows)} = {100*r1/len(rows):.0f}%")
shares=sorted((n/len(rows) for n in cc.values()),reverse=True)
print(f"HHI={sum(s*s for s in shares):.4f} (uniform {1/len(cc):.4f}); top1={100*shares[0]:.0f}% top5={100*sum(shares[:5]):.0f}% top20={100*sum(shares[:20]):.0f}%")
print("top creators (4d):",[(c[:8],n) for c,n in cc.most_common(10)])

print("\n"+"="*72)
print("EV: REPEAT-CREATOR vs FIRST-TIME attempts (his 13h outcome set)")
print("="*72)
ao_s=sorted([r for r in ao if r.get("net_R") is not None],key=lambda r:r["create_slot"])
seen=set();
for r in ao_s:
    r["is_repeat"]=r["creator"] in seen
    seen.add(r["creator"])
rep_o=[r["net_R"] for r in ao_s if r["is_repeat"]]
new_o=[r["net_R"] for r in ao_s if not r["is_repeat"]]
rep_g=[r["gross_R"] for r in ao_s if r["is_repeat"]]
new_g=[r["gross_R"] for r in ao_s if not r["is_repeat"]]
print(f"ALL his attempts (n={len(ao_s)}): net_R mean={mean([r['net_R'] for r in ao_s]):+.4f} win={100*winr([r['net_R'] for r in ao_s]):.0f}% gross_win={100*winr([r['gross_R'] for r in ao_s]):.0f}%")
print(f"  REPEAT-creator (n={len(rep_o)}): net={mean(rep_o):+.4f} CI{tuple(round(x,3) for x in boot_ci(rep_o,mean))} win={100*winr(rep_o):.0f}% gross_win={100*winr(rep_g):.0f}%")
print(f"  FIRST-time    (n={len(new_o)}): net={mean(new_o):+.4f} CI{tuple(round(x,3) for x in boot_ci(new_o,mean))} win={100*winr(new_o):.0f}% gross_win={100*winr(new_g):.0f}%")

print("\n"+"="*72)
print("WHITELIST PERSISTENCE (train on EARLY history, test on 13h outcome window)")
print("="*72)
WIN_LO,WIN_HI=456604900,456820120  # the 13h outcome window
train=[r for r in rows if (r["slot"] or 0) < WIN_LO]
fav=Counter(r["creator"] for r in train)
fav2={c for c,n in fav.items() if n>=2}  # creators he hit >=2x BEFORE the window
print(f"train (pre-window) mints={len(train)}; favored creators (>=2x pre-window)={len(fav2)}")
# in test window: his attempts from favored vs not
test_fav=[r["net_R"] for r in ao_s if r["creator"] in fav2]
test_non=[r["net_R"] for r in ao_s if r["creator"] not in fav2]
test_fav_g=[r["gross_R"] for r in ao_s if r["creator"] in fav2]
test_non_g=[r["gross_R"] for r in ao_s if r["creator"] not in fav2]
print(f"his test-window attempts from PRE-FAVORED creators: {len(test_fav)}/{len(ao_s)} = {100*len(test_fav)/len(ao_s):.0f}% (does he return to them?)")
print(f"  FAVORED-creator test net={mean(test_fav):+.4f} CI{tuple(round(x,3) for x in boot_ci(test_fav,mean))} win={100*winr(test_fav):.0f}% gross_win={100*winr(test_fav_g):.0f}%  (n={len(test_fav)})")
print(f"  OTHER-creator   test net={mean(test_non):+.4f} CI{tuple(round(x,3) for x in boot_ci(test_non,mean))} win={100*winr(test_non):.0f}% gross_win={100*winr(test_non_g):.0f}%  (n={len(test_non)})")

print("\n"+"="*72)
print("EV CHECK vs OUR FILTER (population, econ102 shipped ladder, SIZE=0.5)")
print("="*72)
def outc(c):
    t=TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"): return None
    entry=t["entry_px"]*E.ENTRY_MULT
    series=[(s,p) for s,p in t["series"]]
    net,_,_=E.simulate(entry,t["create_slot"],series,E.SHIP,SIZE=0.5)
    g=E.gross_only(entry,t["create_slot"],series,E.SHIP)
    return (net,g)
def van(c): return (c.get("mayhem") or 0)==0 and (c.get("holder_reward") or 0)==0 and (c.get("cashback") or 0)==0
def bucket(name,sel):
    xs=[]; gs=[]
    for c in pop:
        if not sel(c): continue
        o=outc(c)
        if o: xs.append(o[0]); gs.append(o[1])
    print(f"  {name:34} n={len(xs):4d} net={mean(xs):+.4f} CI{tuple(round(x,3) for x in boot_ci(xs,mean))} win={100*winr(xs):.0f}% gross_win={100*winr(gs):.0f}%")
    return xs
bucket("ALL population",lambda c:True)
bucket("creator_fee==0 only",lambda c:(c.get('creator_fee_bps') or 0)==0)
bucket("OUR FILTER dev>=2 & fee0",lambda c:(c.get('dev_buy') or 0)>=2 and (c.get('creator_fee_bps') or 0)==0)
bucket("HIS-ATTEMPT-RULE dev>=0.5 & vanilla",lambda c:(c.get('dev_buy') or 0)>=0.5 and van(c))
bucket("dev>=1.0 & vanilla",lambda c:(c.get('dev_buy') or 0)>=1.0 and van(c))
# his actual attempts EV for reference
hn=[r["net_R"] for r in ao_s]; hg=[r["gross_R"] for r in ao_s]
print(f"  {'HIS ACTUAL ATTEMPTS (13h)':34} n={len(hn):4d} net={mean(hn):+.4f} CI{tuple(round(x,3) for x in boot_ci(hn,mean))} win={100*winr(hn):.0f}% gross_win={100*winr(hg):.0f}%")

print("\n"+"="*72)
print("CREATOR-WHITELIST COVERAGE vs DEV-BUY FILTER (reproduce his picks?)")
print("="*72)
# can a creator-whitelist reproduce his attempt set better than dev>=2?
# favored (pre-window >=2x) recall of his window attempts already shown. Also dev-buy recall:
aa=[r for r in ao if r.get("dev_buy") is not None]
print(f"his window attempts recovered: {len(aa)}")
print(f"  recall by dev>=0.5: {100*sum(1 for r in aa if (r['dev_buy'] or 0)>=0.5)/len(aa):.0f}%")
print(f"  recall by dev>=2.0 (our filter): {100*sum(1 for r in aa if (r['dev_buy'] or 0)>=2.0)/len(aa):.0f}%")
print(f"  recall by pre-window favored-creator whitelist: {100*len(test_fav_g)/len(ao_s):.0f}% (creators only)")
