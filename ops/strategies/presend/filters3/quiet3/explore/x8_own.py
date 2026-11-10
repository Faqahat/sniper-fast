from lib import *
import collections
T=load()
# own-history features (known before the trigger: earlier positions closed >= 3 s before the trigger time)
hist_w=collections.defaultdict(list); hist_c=collections.defaultdict(list); hist_m=collections.defaultdict(list)
for i,t in enumerate(T):
    T0=t['trig_t'] or t['t']
    cr=(t.get('ann') or {}).get('creator')
    for key,h,name in ((t['whale'],hist_w,'w'),(cr,hist_c,'c'),(t['mint'],hist_m,'m')):
        prev=[p for p in h.get(key,[]) if p['t']+3e9<T0] if key else []
        t[name+'_n']=len(prev)
        t[name+'_nf']=sum(p['nf'] for p in prev)/len(prev) if prev else None
        t[name+'_p']=sum(p['p'] for p in prev)/len(prev) if prev else None
        t[name+'_last_nf']=prev[-1]['nf'] if prev else None
    for key,h in ((t['whale'],hist_w),(cr,hist_c),(t['mint'],hist_m)):
        if key: h[key].append(t)
for f in ['w_n','c_n','m_n']:
    for kind in ('T2','rearm'):
        for sp in ('DEV','VAL'):
            X=[t for t in T if t['kind']==kind and t['split']==sp]
            print(kind,sp,f,' | '.join('%s: %s'%(lab,summ([t for t in X if fn(t[f])])) for lab,fn in [('0',lambda v:v==0),('1',lambda v:v==1),('2+',lambda v:v>=2)]))
for f in ['w_last_nf','c_last_nf','m_last_nf']:
    for kind in ('T2','rearm'):
        for sp in ('DEV','VAL'):
            X=[t for t in T if t['kind']==kind and t['split']==sp]
            print(kind,sp,f,' | '.join('%s: %s'%(lab,summ([t for t in X if t[f]==v])) for lab,v in [('prev followed',False),('prev NOT followed',True)]))
