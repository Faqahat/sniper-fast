import json, statistics
E=json.load(open('/root/every_angle/early_flow.json'))
# aggregate slots 0-3 (cumulative), pre-buy: he lands at create+1, so slot0 (create) is pre-buy-knowable;
# slots 0-1 ~ knowable at his entry; slots 0-3 is slightly contemporaneous/just-after (scale-in window).
rows=[]
for m,v in E.items():
    per=v['per']
    if per.get('0') is None and per.get(0) is None: continue
    def g(off,k):
        p=per.get(str(off)) or per.get(off)
        return (p or {}).get(k,0) if p else 0
    cum_buy=sum(g(o,'nbuy') for o in range(4))
    cum_dist=len(set())  # distinct across slots not stored; approx by sum of per-slot distinct (upper bound)
    cum_sol=sum(g(o,'sol') for o in range(4))
    cum_sell=sum(g(o,'nsell') for o in range(4))
    # pre-buy window = slot0 only (create slot, before his +1 entry)
    s0_buy=g(0,'nbuy'); s0_dist=g(0,'ndistinct'); s0_sol=g(0,'sol')
    # slots 0-1 (knowable right at/just before his fill)
    e1_buy=g(0,'nbuy')+g(1,'nbuy'); e1_sol=g(0,'sol')+g(1,'sol')
    rows.append(dict(slot=v['slot'],peak=v['peak'],rr=v['rr'],
        s0_buy=s0_buy,s0_sol=s0_sol,
        e1_buy=e1_buy,e1_sol=e1_sol,
        cum_buy=cum_buy,cum_sol=cum_sol,cum_sell=cum_sell))
rows.sort(key=lambda r:r['slot']); N=len(rows); h=N//2; OOS=rows[h:]; IS=rows[:h]
print(f"his early-flow rows: N={N}")
def runr(g,thr=1.5): return sum(1 for r in g if r['peak']>=thr)/len(g) if g else float('nan')
def mR(g): return statistics.mean([r['rr'] for r in g]) if g else float('nan')
INF=10**9
def band(title,key,bands):
    print(f"\n### {title} ###")
    print("  band    | OOS n | pump>=1.5 | pump>=2.0 | meanR    | (IS n, IS pump>=1.5)")
    for lab,lo,hi in bands:
        o=[r for r in OOS if lo<=r[key]<hi]; i=[r for r in IS if lo<=r[key]<hi]
        print(f"  {lab:7s} | {len(o):4d}  |   {runr(o):.3f}   |   {runr(o,2.0):.3f}   | {mR(o):+.4f} | ({len(i)}, {runr(i):.3f})")
print("\n-- PRE-BUY (create slot 0 only, before his +1 entry) --")
band("s0 #buys (create slot)", 's0_buy', [("0",0,1),("1-2",1,3),("3-5",3,6),("6+",6,INF)])
band("s0 net SOL (create slot)", 's0_sol', [("<0.5",0,0.5),("0.5-2",0.5,2),("2-5",2,5),("5+",5,INF)])
print("\n-- NEAR-ENTRY (slots 0-1) --")
band("s0-1 #buys", 'e1_buy', [("0-1",0,2),("2-4",2,5),("5-9",5,10),("10+",10,INF)])
band("s0-1 net SOL", 'e1_sol', [("<1",0,1),("1-3",1,3),("3-8",3,8),("8+",8,INF)])
print("\n-- SCALE-IN WINDOW (slots 0-3, contemporaneous/just-after) --")
band("s0-3 #buys", 'cum_buy', [("0-2",0,3),("3-6",3,7),("7-15",7,16),("16+",16,INF)])
band("s0-3 net SOL", 'cum_sol', [("<1",0,1),("1-4",1,4),("4-10",4,10),("10+",10,INF)])
band("s0-3 #sells", 'cum_sell', [("0",0,1),("1-2",1,3),("3+",3,INF)])
json.dump({'N':N},open('/root/every_angle/early_done.json','w'))
