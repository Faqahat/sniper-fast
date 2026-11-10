# BUNDLE skip replay on real live fills: holders (>=2%, ours excluded) that share the SAME first-buy slot (identical age) and have
# <= 1 hold on record; their summed holding = "bundle %". Skip when bundle% >= X (optionally only on young tokens). Fill-time data.
import json,collections,sys
D='/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/r42b'
def load(r):
    fa,real,arm={}, {}, {}
    for l in open(f'{D}/r{r}live.jsonl'):
        d=json.loads(l); e=d['ev']; m=d.get('mint') or (d.get('trig') or {}).get('mint'); k=(d.get('w'),m)
        if e=='presend_live_fill': fa.setdefault(k,d.get('ann') or {})
        elif e=='presend_live_realized': real[k]=real.get(k,0)+d['pnl']/1e9
        elif e=='presend_live_arm': arm[k]=d
    return fa,real,arm
def bundle(a):
    g=collections.defaultdict(float)
    for h in a.get('holders',[]):
        if (h.get('n') or 0)<=1: g[h.get('age')]+=h['pct']
    return max(g.values()) if g else 0.0
RUNS=[39,40,41,42,43,44,45,46]
data={r:load(r) for r in RUNS}
print("bundle% = max over same-age groups of fresh holders (<=1 hold) | blocked n, would-win, would-lose, net saved per run")
for X in (15,20,25,30,35):
    tot=0; parts=[]; allv=[]
    for r,(fa,real,arm) in data.items():
        v=[real[k] for k,a in fa.items() if k in real and a.get('holders') is not None and bundle(a)>=X]
        s=-sum(v); tot+=s; allv+=v
        parts.append(f"r{r}:{len(v)}/{s:+.2f}")
    allv.sort(); w=[x for x in allv if x>0]; lo=[x for x in allv if x<=0]
    print(f"X>={X}%: total saved {tot:+.3f} | blocked {len(allv)} (win {len(w)} {sum(w):+.2f}, lose {len(lo)} {sum(lo):+.2f}) | w/o top5 saves {-(sum(allv[5:])):+.3f} | "+" ".join(parts))
