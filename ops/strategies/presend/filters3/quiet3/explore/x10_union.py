from lib import *
import collections,datetime,sys
T=load()
ATT0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; ATT1=ATT0+40*60*10**9
K=int(sys.argv[1]) if len(sys.argv)>1 else 3
h=collections.defaultdict(list)
for t in T:
    T0=t['trig_t'] or t['t']; k=(t.get('ann') or {}).get('creator')
    prev=[p for p in h.get(k,[]) if p['t']+3e9<T0][-K:] if k else []
    t['B']=len(prev)>0 and 2*sum(p['nf'] for p in prev)>=len(prev)
    if k: h[k].append(t)
    t['A']=t['kind']=='T2' and t['n120'] is not None and t['n120']<=15 and (t['whd'] or 0)<=5
cb=collections.defaultdict(lambda:[0,0.0])
for t in T:
    if t['B']: cb[((t.get('ann') or {}).get('creator')[:8],t['split'])][0]+=1; cb[((t.get('ann') or {}).get('creator')[:8],t['split'])][1]+=t['p']
print('B blocked by creator:',sorted([(k,v[0],round(v[1])) for k,v in cb.items()],key=lambda x:x[2])[:12])
print('distinct creators blocked', len({k[0] for k in cb}))
def rep(name,f):
    print('==',name)
    days={'DEV':None}
    for sp,sel in [('DEV',lambda t:t['split']=='DEV'),('VAL',lambda t:t['split']=='VAL'),('VALnoatt',lambda t:t['split']=='VAL' and not ATT0<=t['t']<ATT1)]+[('r%d'%r,(lambda r: lambda t:t['run']==r and t['split']=='DEV')(r)) for r in (37,38,39,40,41,42)]:
        X=[t for t in T if sel(t)]; B=[t for t in X if f(t)]
        top5=set(id(t) for t in sorted(X,key=lambda t:-t['p'])[:5])
        print('  %-9s n %4d net %+7.0f | blk %3d (T2 %3d) nf %3d win %3d lose %3d | saves %+6.0f | won lost %+6.0f lost saved %+6.0f | w/o top5 trades: saves %+6.0f'%(
            sp,len(X),sum(t['p'] for t in X),len(B),sum(t['kind']=='T2' for t in B),sum(t['nf'] for t in B),sum(t['p']>0 for t in B),sum(t['p']<=0 for t in B),-sum(t['p'] for t in B),
            sum(t['p'] for t in B if t['p']>0),-sum(t['p'] for t in B if t['p']<=0),-sum(t['p'] for t in B if id(t) not in top5)))
rep('A',lambda t:t['A']); rep('B (K=%d)'%K,lambda t:t['B']); rep('A or B',lambda t:t['A'] or t['B'])
