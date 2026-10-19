import json
from collections import defaultdict, Counter

parsed=json.load(open("/root/parsed_txs.json"))
rt={r["mint"]:r for r in json.load(open("/root/roundtrips.json"))["roundtrips"]}
leg=json.load(open("/root/leg_events.json"))

def perc(a,p):
    a=sorted(x for x in a if x is not None)
    if not a: return None
    if len(a)==1: return a[0]
    k=(len(a)-1)*p/100; f=int(k); c=min(f+1,len(a)-1); return a[f]+(a[c]-a[f])*(k-f)
def med(a): return perc(a,50)
def ps(a): return {p:(round(perc(a,p),3) if perc(a,p) is not None else None) for p in (10,25,50,75,90)}

# mint -> sigs
mint_sigs=defaultdict(set)
for sig,v in parsed.items():
    if v is None: continue
    for m,td in v["tokdeltas"].items():
        if td!=0: mint_sigs[m].add(sig)

# build per-mint decoded legs
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
import base64
def b58enc(b):
    n=int.from_bytes(b,"big"); s=""
    while n>0: n,r=divmod(n,58); s=B58[r]+s
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+s

mintdata={}
for m in rt:
    legs=[]
    for sig in mint_sigs[m]:
        e=leg.get(sig)
        if not e or not e["events"]: continue
        for ev in e["events"]:
            if b58enc(base64.b64decode(ev["mint"]))!=m: continue
            price=ev["sol"]/ev["tok"] if ev["tok"] else None
            legs.append({"slot":e["slot"],"bt":e["bt"],"is_buy":ev["is_buy"],
                         "sol":ev["sol"]/1e9,"tok":ev["tok"],"price":price})
    legs.sort(key=lambda x:(x["slot"],x["bt"]))
    buys=[l for l in legs if l["is_buy"]]
    sells=[l for l in legs if not l["is_buy"]]
    mintdata[m]={"buys":buys,"sells":sells}

# classify winners/losers by NET multiple (from roundtrips)
losers=[m for m in rt if rt[m]["mult"] is not None and rt[m]["mult"]<=1]
winners=[m for m in rt if rt[m]["mult"] is not None and rt[m]["mult"]>1]
print("losers:",len(losers),"winners:",len(winners))

# coverage: decoded buy/sell vs roundtrip counts
missing_sell_decode=0; dec_sell_tot=0; rt_sell_tot=0
for m in rt:
    d=mintdata[m]
    rt_sells=rt[m]["n_sells"]; dec_sells=len(d["sells"])
    rt_sell_tot+=rt_sells; dec_sell_tot+=dec_sells
    if dec_sells<rt_sells: missing_sell_decode+=1
print(f"sell legs: roundtrip-count={rt_sell_tot} pump-decoded={dec_sell_tot} | mints missing >=1 decoded sell (migrated/PumpSwap?): {missing_sell_decode}")

# ---- 1) LOSER cut timing ----
print("\n=== 1) LOSER CUT TIMING ===")
lt_first_s=[rt[m]["hold_s"] for m in losers]
lt_first_sl=[rt[m]["hold_slots"] for m in losers]
lt_full_s=[rt[m]["full_exit_s"] for m in losers]
print("time-to-first-sell  sec :", ps(lt_first_s))
print("time-to-first-sell  slot:", ps(lt_first_sl))
print("time-to-FULL-exit   sec :", ps(lt_full_s))
# full exit in slots
full_sl=[]
for m in losers:
    d=mintdata[m]
    if d["buys"] and d["sells"]:
        full_sl.append(d["sells"][-1]["slot"]-d["buys"][0]["slot"])
print("time-to-FULL-exit   slot:", ps(full_sl))
lc=Counter(rt[m]["n_sells"] for m in losers)
print("loser n_sells:", {k:lc[k] for k in sorted(lc)})
print("loser 1-leg:", round(100*lc.get(1,0)/len(losers),1),"% | 2-leg:",round(100*lc.get(2,0)/len(losers),1),"% | 3+:",round(100*sum(v for k,v in lc.items() if k>=3)/len(losers),1),"%")

# ---- 2) loss-size histogram (net mult) ----
print("\n=== 2) LOSER EXIT-MULTIPLE HISTOGRAM (net) ===")
buckets=[("0.95-1.0",0.95,1.0),("0.90-0.95",0.90,0.95),("0.80-0.90",0.80,0.90),("0.70-0.80",0.70,0.80),("0.50-0.70",0.50,0.70),("<0.50",0,0.50)]
lm=[rt[m]["mult"] for m in losers]
for lab,lo,hi in buckets:
    n=sum(1 for x in lm if (x>lo or (lo==0)) and x<=hi)
    print(f"  {lab}: {n} ({100*n/len(lm):.1f}%)")
# also gross mult for losers
def gross(m):
    d=mintdata[m]
    if not d["buys"]: return None
    bin_=d["buys"][0]["sol"]
    sout=sum(s["sol"] for s in d["sells"])
    return sout/bin_ if bin_ else None
print("loser net-mult median:",round(med(lm),3)," gross-mult median:",round(med([gross(m) for m in losers if gross(m)]),3))

# worst tail <0.5
print("\n=== WORST TAIL (<0.5x net) ===")
worst=sorted([m for m in losers if rt[m]["mult"]<0.5], key=lambda m:rt[m]["mult"])
print("count <0.5x:",len(worst))
for m in worst:
    d=mintdata[m]; r=rt[m]
    fsp=d["sells"][0]["price"]/d["buys"][0]["price"] if d["buys"] and d["sells"] else None
    print(f"  {m[:8]} net={r['mult']:.2f} gross={gross(m):.2f} legs={r['n_sells']} first_sell={r['hold_s']}s/{r['hold_slots']}sl full={r['full_exit_s']}s firstSellPxMult={fsp:.2f}" if fsp else f"  {m[:8]} net={r['mult']:.2f}")

# ---- 3) price at first sell vs entry (time vs stop-loss) ----
print("\n=== 3) PRICE AT FIRST SELL vs ENTRY (losers) ===")
fsp=[]
for m in losers:
    d=mintdata[m]
    if d["buys"] and d["sells"] and d["buys"][0]["price"]:
        fsp.append(d["sells"][0]["price"]/d["buys"][0]["price"])
print("first-sell price / entry price  pcts:", ps(fsp))
print("  share with first-sell price >= entry (sells while UP/flat):", round(100*sum(1 for x in fsp if x>=0.98)/len(fsp),1),"%")
print("  share first-sell price >=1.0 (strictly up):", round(100*sum(1 for x in fsp if x>=1.0)/len(fsp),1),"%")
print("  share first-sell price < 0.9 (waited for >10% drawdown):", round(100*sum(1 for x in fsp if x<0.9)/len(fsp),1),"%")
print("  share first-sell price < 0.8:", round(100*sum(1 for x in fsp if x<0.8)/len(fsp),1),"%")

# ---- 4) hold-a-loser: long hold + loss, recovery ----
print("\n=== 4) HELD LOSERS (did he ever hold hoping for recovery?) ===")
for thr in [5,10,30,60]:
    held=[m for m in losers if rt[m]["full_exit_s"] is not None and rt[m]["full_exit_s"]>=thr]
    print(f"  full-exit >= {thr}s: {len(held)} losers ({100*len(held)/len(losers):.1f}%)")
# of all trades held >10s, what fraction were winners (does holding pay)?
for thr in [5,10,30]:
    held_all=[m for m in rt if rt[m]["full_exit_s"] is not None and rt[m]["full_exit_s"]>=thr]
    wr=100*sum(1 for m in held_all if rt[m]["mult"]>1)/len(held_all) if held_all else 0
    print(f"  ALL trades held full-exit>={thr}s: n={len(held_all)} winrate={wr:.0f}% (base winrate 49.6%)")

# ---- 5) partial exit on losers ----
print("\n=== 5) PARTIAL-EXIT ON LOSERS ===")
print("loser 1-leg (single dump):", lc.get(1,0), f"({100*lc.get(1,0)/len(losers):.1f}%) | multi-leg: {len(losers)-lc.get(1,0)} ({100*(len(losers)-lc.get(1,0))/len(losers):.1f}%)")
# for multi-leg losers, first clip size
ml_first=[rt[m]["legs"][0] for m in losers if rt[m]["n_sells"]>=2 and rt[m]["legs"][0] is not None]
print("multi-leg losers first-clip % of position: median", round(100*med(ml_first),0) if ml_first else None)

# ---- 6) concrete runner ladders ----
print("\n=== 6) CONCRETE RUNNER LADDERS (per-leg slot, %pos, price x) ===")
runners=sorted(winners, key=lambda m:(rt[m]["sol_out"]-rt[m]["sol_in"]),reverse=True)
examples=[m for m in runners if rt[m]["n_sells"]>=3][:5]
for m in examples:
    d=mintdata[m]; r=rt[m]
    b=d["buys"][0]; tot=sum(s["tok"] for s in d["sells"])
    print(f"\n {m[:10]}  net={r['mult']:.2f} gross={gross(m):.2f} entry={b['sol']:.2f}SOL buy_slot={b['slot']} legs={len(d['sells'])}")
    for i,s in enumerate(d["sells"]):
        pxm=s["price"]/b["price"] if b["price"] else None
        print(f"   leg{i+1}: +{s['slot']-b['slot']}sl  {100*s['tok']/tot:.0f}%pos  {s['sol']:.2f}SOL  px={pxm:.2f}x")
