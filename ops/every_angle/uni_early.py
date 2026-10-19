import json, statistics
T=json.load(open('/root/profit_backtest/trajectories.json'))
rows=[]
for x in T:
    s=x.get('series') or []; e=x.get('entry_px'); cs=x.get('create_slot')
    if not s or not e or cs is None: continue
    px=[p for p in s if isinstance(p,list) and len(p)>=2]
    if not px: continue
    peak=max(p[1] for p in px)/e
    # EARLY window: slots create..create+3
    early=[p for p in px if p[0]<=cs+3]
    n_early=len(early)
    early_ret=(early[-1][1]/e) if early else 1.0     # price move by end of early window (momentum, ~contemporaneous)
    # slots 4+ : later
    rows.append(dict(slot=cs,peak=peak,n_early=n_early,early_ret=early_ret))
rows.sort(key=lambda r:r['slot']); N=len(rows); h=N//2; IS=rows[:h]; OOS=rows[h:]
print(f"universe early-window rows: N={N}")
def runr(g,thr=1.5): return sum(1 for r in g if r['peak']>=thr)/len(g) if g else float('nan')
def mp(g): return statistics.mean([r['peak'] for r in g]) if g else float('nan')
INF=10**9
def band(title,key,bands):
    print(f"\n### {title} ###")
    print("  band    | OOS n | pump>=1.5 | pump>=2.0 | meanpeak | (IS n, IS pump>=1.5)")
    for lab,lo,hi in bands:
        o=[r for r in OOS if lo<=r[key]<hi]; i=[r for r in IS if lo<=r[key]<hi]
        print(f"  {lab:7s} | {len(o):4d}  |   {runr(o):.3f}   |   {runr(o,2.0):.3f}   |  {mp(o):.3f}  | ({len(i)}, {runr(i):.3f})")
band("EARLY TRADE COUNT (slots 0-3), pre/at-entry proxy", 'n_early',
     [("0-1",0,2),("2-4",2,5),("5-9",5,10),("10-20",10,21),("21+",21,INF)])
band("EARLY RETURN by slot+3 (px/entry) - momentum", 'early_ret',
     [("<1.0",0,1.0),("1.0-1.3",1.0,1.3),("1.3-2",1.3,2),("2+",2,INF)])
