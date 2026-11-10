from lib import *
import json,bisect,collections
T=load()
# backrun buyer events: (t, wallet8) for market activity
E=[]
for r in (37,38,39,40,41,42):
    for l in open('../obs/br%d.jsonl'%r):
        d=json.loads(l)
        for w in {x[0] for x in d['b']}: E.append((d['t'],w))
E.sort(); ET=[e[0] for e in E]
LAG=15e9
# our followers: wallets that bought inside our holds; known at our sell (+3 s)
FOL=[]
for t in T:
    for (ds,sol,u,inh) in t['fol']:
        if inh: FOL.append((t['t']+3e9,u))
FOL.sort(); FT=[f[0] for f in FOL]
for t in T:
    T0=t['trig_t'] or t['t']
    for H in (2,6):
        a=bisect.bisect_left(FT,T0-H*3600e9); b=bisect.bisect_right(FT,T0)
        cnt=collections.Counter(u for _,u in FOL[a:b])
        F={u for u,c in cnt.items() if c>=2}
        t['ourfol%d'%H]=len(F)
        for M in (5,15):
            lo=bisect.bisect_left(ET,T0-LAG-M*60e9); hi=bisect.bisect_right(ET,T0-LAG)
            act={w for _,w in E[lo:hi]}
            t['act%d_%d'%(H,M)]=len(F&act) if t['mk_cover'] else None
            t['actfr%d_%d'%(H,M)]=len(F&act)/len(F) if F and t['mk_cover'] else None
json.dump({(str(t['run'])+t['mint']+str(t['pid'])+str(t['t'])):{k:t[k] for k in t if k.startswith(('ourfol','act'))} for t in T},open('ourfol.json','w'))
for kind in ('T2','rearm'):
  for f in ['ourfol2','ourfol6','act2_5','act2_15','act6_5','act6_15','actfr6_15','actfr2_5']:
    X=[t for t in T if t['kind']==kind and t.get(f) is not None]
    dv=sorted(t[f] for t in X if t['split']=='DEV')
    qs=sorted(set(dv[int(len(dv)*k/5)] for k in range(1,5)))
    print(kind,'==',f,[round(q,2) for q in qs])
    for sp in ('DEV','VAL'):
        print(sp,' | '.join(summ([t for t in X if t['split']==sp and sum(t[f]>=q for q in qs)==k]) for k in range(len(qs)+1)))
