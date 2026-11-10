from lib import *
import datetime,collections
T=load()
ATT0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; ATT1=ATT0+40*60*10**9
def sim(K,H,kept_only,frac=0.5,useA=True):
    h=collections.defaultdict(list); blk=[]
    for t in T:
        T0=t['trig_t'] or t['t']; k=(t.get('ann') or {}).get('creator')
        A=useA and t['kind']=='T2' and t['n120'] is not None and t['n120']<=15 and (t['whd'] or 0)<=3
        prev=[p for p in h.get(k,[]) if p['t']+3e9<T0 and (H is None or p['t']>=T0-H*3600e9)][-K:] if k else []
        B=len(prev)>0 and sum(p['nf'] for p in prev)>=frac*len(prev)
        b=A or B; blk.append((A,B))
        if k and (not kept_only or not b): h[k].append(t)
    return blk
def s(name,blk):
    o=[]
    for sp,sel in [('DEV',lambda t:t['split']=='DEV'),('VAL',lambda t:t['split']=='VAL'),('VALnoatt',lambda t:t['split']=='VAL' and not ATT0<=t['t']<ATT1)]:
        b=[t for t,x in zip(T,blk) if (x[0] or x[1]) and sel(t)]; bb=[t for t,x in zip(T,blk) if x[1] and not x[0] and sel(t)]
        o.append('%s %3d %+6.0f (B-only %3d %+5.0f)'%(sp,len(b),-sum(t['p'] for t in b),len(bb),-sum(t['p'] for t in bb)))
    print('%-28s'%name,' | '.join(o))
for kept in (False,True):
    for K in (2,3,5):
        for H in (None,24,12,6):
            s('kept=%d K=%d H=%s'%(kept,K,H),sim(K,H,kept))
