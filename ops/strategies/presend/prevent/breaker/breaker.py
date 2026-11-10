# CIRCUIT BREAKER replay on real live fills: after N losses worse than -L SOL (by exit slot) within W slots, block new fills for P slots.
import json,sys,itertools
D='/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/r42b'
RUNS=[37,38,39,40,41,42,43,44,45,46]
def load(r):
    fill,close,real={}, {}, {}
    for l in open(f'{D}/r{r}live.jsonl'):
        d=json.loads(l); e=d['ev']; m=d.get('mint') or (d.get('trig') or {}).get('mint'); k=(d.get('w'),m)
        if e=='presend_live_fill': fill.setdefault(k,d['slot'])
        elif e=='presend_live_close': close[k]=d.get('exit_slot')
        elif e=='presend_live_realized': real[k]=real.get(k,0)+d['pnl']/1e9
    t=[(fill[k],close.get(k) or fill[k],p) for k,p in real.items() if k in fill]
    return sorted(t)
data={r:load(r) for r in RUNS}
def sim(tr,N,L,W,P):
    blocked=[]; losses=[]; until=-1
    for fs,es,p in tr:
        if fs<until: blocked.append(p); continue
        # losses known by now (closed before this fill)
        pass
    return blocked
def run(N,L,W,P):
    res={}
    for r,tr in data.items():
        until=-1; blocked=[]; done=[]  # (exit_slot,pnl) of taken trades
        for fs,es,p in tr:
            recent=[x for x in done if x[0]<=fs and x[0]>fs-W and x[1]<=-L]
            if len(recent)>=N and fs < max(x[0] for x in recent)+P: blocked.append(p); continue
            done.append((es,p))
        res[r]=(len(blocked), -sum(blocked))
    return res
print("rule: N losses <= -L within W min -> pause P min | saved per run (blocked n, net saved = -sum of blocked)")
SLOT=0.4
for N,L,W,P in [(2,0.25,10,30),(2,0.25,10,60),(2,0.2,10,30),(1,0.4,10,30),(2,0.3,15,60),(3,0.2,15,60)]:
    res=run(N,L,int(W*60/SLOT),int(P*60/SLOT))
    tot=sum(v[1] for v in res.values()); pos=sum(1 for v in res.values() if v[1]>0.0001); neg=sum(1 for v in res.values() if v[1]<-0.0001)
    print(f"N{N} L{L} W{W} P{P}: total {tot:+.3f} | runs +{pos}/-{neg} | "+" ".join(f"r{r}:{v[0]}/{v[1]:+.2f}" for r,v in res.items() if v[0]))
