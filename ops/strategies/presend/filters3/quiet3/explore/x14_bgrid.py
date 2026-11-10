import sys,collections,itertools,datetime
sys.path.insert(0,'/home/it/sniper/ops/strategies/presend/filters3/quiet3'); import quiet3_score as q
VAL=1793516400*10**9; A0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; A1=A0+40*60*10**9
runs={r:q.positions('r%d.presend.jsonl'%r) for r in (37,38,39,40,41,42)}
def sim(K,mn,frac,H,reset):
    out=[]; h=collections.defaultdict(list)
    for r in (37,38,39,40,41,42):
        if reset: h=collections.defaultdict(list)
        for p in runs[r]:
            A=q.a_rule(p); B=False
            if p['creator']:
                prev=sorted([x for x in h[p['creator']] if x['known']<p['t0'] and x['known']>=p['t0']-H*3600e9],key=lambda x:x['known'])[-K:]
                B=len(prev)>=mn and sum(not x['followed'] for x in prev)>=frac*len(prev)
            if not (A or B):
                if p['creator']: h[p['creator']].append(p)
            out.append((p,A,B))
    return out
def s(o,f): return -sum(p['pnl'] for p,A,B in o if B and not A and f(p))
rows=[]
for K,mn,frac,H in itertools.product((2,3,4,5),(1,2,3),(0.5,0.67,1.0),(2,6,24)):
    if mn>K: continue
    oc=sim(K,mn,frac,H,False); orr=sim(K,mn,frac,H,True)
    d1=s(oc,lambda p:p['t0']<VAL); d2=s(orr,lambda p:p['t0']<VAL); v=s(oc,lambda p:p['t0']>=VAL and not A0<=p['t0']<A1); v2=s(orr,lambda p:p['t0']>=VAL and not A0<=p['t0']<A1)
    nb=sum(1 for p,A,B in oc if B and not A and p['t0']<VAL)
    rows.append((min(d1,d2),K,mn,frac,H,d1,d2,v,v2,nb))
rows.sort(key=lambda x:-x[0])
print('K min_n frac H | DEV carry  DEV reset | VALnoatt carry VALnoatt reset | DEV blocks')
for r in rows[:25]: print('%d %d %.2f %2d | %+6.3f %+6.3f | %+6.3f %+6.3f | %d'%r[1:])
