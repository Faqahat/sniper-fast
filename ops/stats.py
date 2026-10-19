import json
from collections import Counter

d = json.load(open("/root/roundtrips.json"))
rts = d["roundtrips"]

def perc(arr, p):
    a = sorted(x for x in arr if x is not None)
    if not a: return None
    if len(a) == 1: return a[0]
    k = (len(a)-1)*p/100.0
    f = int(k); c = min(f+1, len(a)-1)
    return a[f] + (a[c]-a[f])*(k-f)
def mean(arr):
    a = [x for x in arr if x is not None]
    return sum(a)/len(a) if a else None
def median(arr): return perc(arr,50)
def pct(arr):
    return {p: (round(perc(arr,p),4) if perc(arr,p) is not None else None) for p in (10,25,50,75,90)}, len([x for x in arr if x is not None])

print("=== SAMPLE ===")
print("full roundtrips:", len(rts), "| no_sell:", len(d["no_sell"]), "| no_buy_seen:", len(d["no_buy"]))

hs = [r["hold_s"] for r in rts]
hsl = [r["hold_slots"] for r in rts]
print("\n=== HOLD TIME (first buy -> first sell) ===")
print("seconds pcts:", pct(hs), "mean", round(mean(hs),2))
print("slots pcts:", pct(hsl), "mean", round(mean(hsl),2))
print("full-exit seconds (first buy->last sell):", pct([r["full_exit_s"] for r in rts]))

legcounts = [r["n_sells"] for r in rts]
c = Counter(legcounts); tot = len(legcounts)
print("\n=== SELL LEGS ===")
for k in sorted(c):
    print(f"  {k} legs: {c[k]} ({100*c[k]/tot:.1f}%)")
print("single:", round(100*c.get(1,0)/tot,1), "% | 2-leg:", round(100*c.get(2,0)/tot,1),
      "% | 3+:", round(100*sum(v for k,v in c.items() if k>=3)/tot,1), "%")
print("buys per token:", dict(Counter(r["n_buys"] for r in rts)))

mult = [r["mult"] for r in rts if r["mult"] is not None]
wins = [m for m in mult if m > 1]; losses = [m for m in mult if m <= 1]
print("\n=== EXIT MULTIPLE (net SOL out / SOL in, incl fees+tips) ===")
print("pcts:", pct(mult), "mean", round(mean(mult),3))
print(f"win rate (mult>1): {100*len(wins)/len(mult):.1f}% ({len(wins)}/{len(mult)})")
print("winner median:", round(median(wins),3), "mean:", round(mean(wins),3), "p90:", round(perc(wins,90),3), "max:", round(max(wins),2))
print("loser median:", round(median(losses),3), "mean:", round(mean(losses),3), "p10:", round(perc(losses,10),3), "min:", round(min(losses),3))

sf = [r["sold_frac"] for r in rts]
print("\n=== SOLD FRACTION ===")
print("pcts:", pct(sf), ">=99% sold:", sum(1 for x in sf if x and x>=0.99), "/", len(sf))

pnl = [(r["sol_out"]-r["sol_in"]) for r in rts]
print("\n=== PER-TOKEN NET PnL (SOL) ===")
print("total net SOL:", round(sum(pnl),2), "| pcts:", pct(pnl))
print("avg win SOL:", round(mean([p for p in pnl if p>0]),3), "| avg loss SOL:", round(mean([p for p in pnl if p<=0]),3))
print("sum wins:", round(sum(p for p in pnl if p>0),2), "| sum losses:", round(sum(p for p in pnl if p<=0),2))

print("\n=== HOLD TIME: WINNERS vs LOSERS (seconds) ===")
win_hold=[r["hold_s"] for r in rts if r["mult"] and r["mult"]>1]
los_hold=[r["hold_s"] for r in rts if r["mult"] and r["mult"]<=1]
print("winners:", pct(win_hold), "mean", round(mean(win_hold),2))
print("losers :", pct(los_hold), "mean", round(mean(los_hold),2))
print("winners slots:", pct([r["hold_slots"] for r in rts if r["mult"] and r["mult"]>1]))
print("losers  slots:", pct([r["hold_slots"] for r in rts if r["mult"] and r["mult"]<=1]))

print("\n=== SCALE-OUT SCHEDULE (multi-leg) ===")
for nlegs in [2,3,4,5]:
    grp=[r["legs"] for r in rts if r["n_sells"]==nlegs]
    if not grp: continue
    print(f"-- {nlegs}-leg (n={len(grp)}):")
    for i in range(nlegs):
        fr=[g[i] for g in grp if g[i] is not None]
        print(f"   leg{i+1}: median {100*median(fr):.0f}% mean {100*mean(fr):.0f}%")

print("\n=== LEGS vs OUTCOME ===")
for lab,cond in [("1-leg",lambda r:r["n_sells"]==1),("2-leg",lambda r:r["n_sells"]==2),("3+",lambda r:r["n_sells"]>=3)]:
    g=[r for r in rts if cond(r) and r["mult"] is not None]
    if not g: continue
    wr=100*sum(1 for r in g if r["mult"]>1)/len(g)
    print(f"  {lab}: n={len(g)} winrate={wr:.0f}% median_mult={median([r['mult'] for r in g]):.2f} median_hold={median([r['hold_s'] for r in g]):.0f}s")
