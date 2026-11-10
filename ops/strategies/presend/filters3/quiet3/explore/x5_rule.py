from lib import *
import sys,datetime
T=load()
for t in T:
    t['whf0']=t['whf'] if t['whf'] is not None and t['whf']>=0 else 0.0
ATT0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9
ATT1=ATT0+40*60*10**9
def rule_factory(spec):
    cs=[(a.split('<=')[0],float(a.split('<=')[1])) for a in spec.split('&')]
    return lambda t: t['kind']=='T2' and all(t.get(f) is not None and t[f]<=c for f,c in cs)
def report(spec):
    R=rule_factory(spec)
    print('RULE',spec)
    for name,sel in [('DEV',lambda t:t['split']=='DEV'),('VAL',lambda t:t['split']=='VAL'),('VAL-noattack',lambda t:t['split']=='VAL' and not ATT0<=t['t']<ATT1)]+[('r%d'%r,(lambda r: lambda t:t['run']==r and t['split']=='DEV')(r)) for r in (37,38,39,40,41,42)]:
        X=[t for t in T if sel(t)]; B=[t for t in X if R(t)]
        if not X: continue
        top5=sorted(B,key=lambda t:-t['p'])[:5]
        print('  %-13s all %4d %+7.0f | blocked %3d nf %3d win %3d sum %+6.0f -> saves %+6.0f | without top5 winners blocked: saves %+6.0f'%(name,len(X),sum(t['p'] for t in X),len(B),sum(t['nf'] for t in B),sum(t['p']>0 for t in B),sum(t['p'] for t in B),-sum(t['p'] for t in B),-sum(t['p'] for t in B if t not in top5)))
for s in sys.argv[1:]: report(s)
