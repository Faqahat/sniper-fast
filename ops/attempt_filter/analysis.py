import sys,json,statistics as st
sys.path.insert(0,"/root/econ_102"); import econ102 as E
sys.path.insert(0,"/root/profit_backtest")

TOTAL_CREATES=19365  # census count from harvest.log (full window create_v2 count)
raw=json.load(open("/root/attempt_filter/attempted_feat.json"))
att=[r for r in raw if r.get("create_found")]
pop=json.load(open("/root/profit_backtest/creates.json"))
attmints=set(r["mint"] for r in raw)
ign=[c for c in pop if c["mint"] not in attmints]
NATT=190; ATT_RATE=NATT/TOTAL_CREATES

def van(c): return (c.get("mayhem") or 0)==0 and (c.get("holder_reward") or 0)==0 and (c.get("cashback") or 0)==0
def q(xs):
    xs=sorted(xs); n=len(xs); return (xs[n//4],xs[n//2],xs[3*n//4]) if n else (0,0,0)
def rate(bs): return sum(1 for b in bs if b)/len(bs) if bs else 0

print("="*70)
print(f"ATTEMPT RATE: {NATT} attempted / {TOTAL_CREATES} creates = {100*ATT_RATE:.2f}%")
print(f"  attempted w/features: {len(att)}  ignored/pop sample: {len(ign)}")
print(f"  his buys: 1011 (115 landed / 896 failed) over 190 mints -> {1011/190:.1f} buys/mint spray")
print("="*70)

# ---------- SLOT-0 FEATURE SEPARATION ----------
print("\n### SLOT-0 FEATURE LIFT (attempted vs population) ###")
print(f"dev_buy SOL  attempted p25/med/p75: {[round(x,3) for x in q([c.get('dev_buy') or 0 for c in att])]}")
print(f"dev_buy SOL  population p25/med/p75: {[round(x,3) for x in q([c.get('dev_buy') or 0 for c in ign])]}")
print(f"\n{'feature':16}{'P(X|att)':>9}{'P(X|pop)':>9}{'lift':>7}{'P(att|X)':>10}")
def line(nm,pa,pp):
    lift=pa/pp if pp>0 else float('inf')
    print(f"{nm:16}{pa:9.3f}{pp:9.3f}{lift:7.2f}{100*ATT_RATE*lift:9.2f}%")
line("vanilla",rate([van(c) for c in att]),rate([van(c) for c in ign]))
line("creator_fee==0",rate([(c.get('creator_fee_bps') or 0)==0 for c in att]),rate([(c.get('creator_fee_bps') or 0)==0 for c in ign]))
line("create_cu>0",rate([(c.get('create_cu_price') or 0)>0 for c in att]),0.265)  # pop base from create_cu_reval (26.5% combined)
for t in [0.3,0.5,1.0,2.0,3.0]:
    line(f"dev_buy>={t}",rate([(c.get('dev_buy') or 0)>=t for c in att]),rate([(c.get('dev_buy') or 0)>=t for c in ign]))

# ---------- CREATOR CLUSTERING (PRIMARY LENS) ----------
print("\n"+"="*70)
print("### CREATOR / DEV CLUSTERING — PRIMARY LENS ###")
print("="*70)
from collections import Counter
att_sorted=sorted(att,key=lambda c:c.get("create_slot") or 0)
cre_count=Counter(c["creator"] for c in att if c.get("creator"))
ncre=len(cre_count); nmint=sum(cre_count.values())
print(f"\n{nmint} attempted mints map to {ncre} distinct creators")
rep_creators={c:n for c,n in cre_count.items() if n>1}
print(f"creators he hit >1 time: {len(rep_creators)}  (they account for {sum(rep_creators.values())}/{nmint} = {100*sum(rep_creators.values())/nmint:.0f}% of attempts)")
print(f"top creators by #attempted mints: {cre_count.most_common(12)}")
# HHI concentration
shares=[n/nmint for n in cre_count.values()]
hhi=sum(s*s for s in shares)
print(f"creator HHI={hhi:.4f} (1/n baseline={1/ncre:.4f}); top-1 share={max(shares)*100:.0f}%, top-5 share={100*sum(sorted(shares,reverse=True)[:5]):.0f}%")

# repeat fraction: for each attempt in slot order, had he attempted this creator earlier?
seen=set(); repeat=0
for c in att_sorted:
    cr=c.get("creator")
    if cr in seen: repeat+=1
    seen.add(cr)
print(f"\nREPEAT-CREATOR fraction (creator seen earlier in his OWN stream): {repeat}/{len(att_sorted)} = {100*repeat/len(att_sorted):.0f}%")
print(f"  => {100*(1-repeat/len(att_sorted)):.0f}% of attempts are the FIRST time he touches that creator in-window")

# how often does a given creator recur in the POPULATION sample? (frequency confound)
pop_cre=Counter(c["creator"] for c in pop)
print(f"\nDo his repeat creators just launch a lot? population-sample launch counts for his top repeat creators:")
for cr,n in cre_count.most_common(8):
    print(f"  {cr[:10]} his_attempts={n}  pop_sample_launches={pop_cre.get(cr,0)}  (sample is 1/{TOTAL_CREATES//len(pop)} of all creates)")

# ---------- DEPLOYER / fee-payer analysis ----------
import os
sys.path.insert(0,"/root/profit_backtest"); import common as C
print("\n### DEPLOYER (create-tx fee payer) vs creator arg ###")
payer_eq=0; payers=[]; got=0
dep_count=Counter()
for c in att:
    sig=c.get("create_sig")
    if not sig: continue
    tx=C.gettx(sig)
    if not tx: continue
    try:
        msg=tx["transaction"]["message"]
        keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
        payer=keys[0]
    except: continue
    got+=1; dep_count[payer]+=1
    if payer==c.get("creator"): payer_eq+=1
print(f"create-tx fee-payer == creator arg: {payer_eq}/{got}")
rep_dep={d:n for d,n in dep_count.items() if n>1}
print(f"distinct deployers(fee-payers): {len(dep_count)}; repeat deployers: {len(rep_dep)} covering {sum(rep_dep.values())}/{got}")
print(f"top deployers: {dep_count.most_common(8)}")

json.dump({"att_rate":ATT_RATE,"ncre":ncre,"nmint":nmint,"rep_creators":rep_creators,
           "repeat_frac":repeat/len(att_sorted),"hhi":hhi,
           "cre_count":dict(cre_count),"dep_count":dict(dep_count)},
          open("/root/attempt_filter/creator_stats.json","w"),indent=0)
print("\nwrote creator_stats.json")
