from lib import *
import collections,datetime,sys
T=load()
ATT0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; ATT1=ATT0+40*60*10**9
def build(T,keyf,K,reset_run=False):
    h=collections.defaultdict(list)
    for t in T:
        T0=t['trig_t'] or t['t']; k=keyf(t)
        if reset_run: k=(t['run'],k) if k else None
        prev=[p for p in h.get(k,[]) if p['t']+3e9<T0][-K:] if k else []
        t['_n']=len(prev); t['_nf']=sum(p['nf'] for p in prev); t['_p']=sum(p['p'] for p in prev)
        if k: h[k].append(t)
    return [(t['_n'],t['_nf'],t['_p']) for t in T]
cre=lambda t:(t.get('ann') or {}).get('creator')
wh=lambda t:t['whale']
def show(name,blk):
    out=[]
    for sp,sel in [('DEV',lambda t:t['split']=='DEV'),('VAL',lambda t:t['split']=='VAL'),('VALnoatt',lambda t:t['split']=='VAL' and not ATT0<=t['t']<ATT1)]:
        B=[t for t,b in zip(T,blk) if b and sel(t)]
        out.append('%s blk %3d nf %3d win %3d save %+6.0f'%(sp,len(B),sum(t['nf'] for t in B),sum(t['p']>0 for t in B),-sum(t['p'] for t in B)))
    print('%-34s'%name,' | '.join(out))
for reset in (False,True):
  print('history reset per run' if reset else 'history across runs')
  for K in (1,2,3,5):
    C=build(T,cre,K,reset); W=build(T,wh,K,reset)
    show('creator last%d: all nf'%K,[n>0 and nf==n for n,nf,p in C])
    show('creator last%d: >=half nf'%K,[n>0 and nf*2>=n for n,nf,p in C])
    show('creator last%d: sum pnl<0'%K,[n>0 and p<0 for n,nf,p in C])
    show('whale last%d: all nf'%K,[n>0 and nf==n for n,nf,p in W])
    show('whale last%d: >=half nf'%K,[n>0 and nf*2>=n for n,nf,p in W])
    show('whale last%d: sum pnl<0'%K,[n>0 and p<0 for n,nf,p in W])
    show('cre or whale last%d all nf'%K,[(a[0]>0 and a[1]==a[0]) or (b[0]>0 and b[1]==b[0]) for a,b in zip(C,W)])
