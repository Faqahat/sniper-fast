from lib import *
import itertools,math
T=[t for t in load() if t['kind']=='T2']
for t in T:
    t['whf0']=t['whf'] if t['whf'] is not None and t['whf']>=0 else 0.0   # no history -> 0
    t['sl1']=1 if (t['since_last'] or 0)>=1 else 0
    t['tsol']=(t['trig_sol'] or 0)/1e9
DEVT=[t for t in T if t['split']=='DEV']; VALT=[t for t in T if t['split']=='VAL']
q=sorted(t['t'] for t in DEVT); fcut=[q[int(len(q)*k/4)] for k in (1,2,3)]
def fold(t): return sum(t['t']>=c for c in fcut)
feats={'n60':[3,4,5,6,8,10,12,15,20],'n120':[4,6,8,10,12,15,20,25],'nb50':[2,3,4,5,6,7,8,10],'whf0':[1,1.5,2,2.5,3,3.5,4,5,6],
       'coh':[0,1],'whd':[0,1,2,3,5,9],'pct':[6.3,6.5,7,7.5],'tsol':[2.0,2.95,3.0,3.95],'maxdd':[0.0,0.02,0.05]}
def ev(rule,X):
    b=[t for t in X if rule(t)]
    return b
res=[]
names=list(feats)
cands=[]
for f in names:
    for c in feats[f]: cands.append(((f,c),))
for f1,f2 in itertools.combinations(names,2):
    for c1 in feats[f1]:
        for c2 in feats[f2]: cands.append(((f1,c1),(f2,c2)))
def mk(cs): return lambda t: all(t[f] is not None and t[f]<=c for f,c in cs)
for cs in cands:
    r=mk(cs); b=[t for t in DEVT if r(t)]
    if len(b)<20: continue
    sv=-sum(t['p'] for t in b)
    fs=[-sum(t['p'] for t in b if fold(t)==k) for k in range(4)]
    res.append((sv,cs,len(b),sum(t['nf'] for t in b),sum(t['p']>0 for t in b),fs))
res.sort(key=lambda x:-x[0])
print('DEV T2: %d trades, %.0f mSOL; nf %d'%(len(DEVT),sum(t['p'] for t in DEVT),sum(t['nf'] for t in DEVT)))
for sv,cs,n,nf,w,fs in res[:40]:
    b=[t for t in VALT if mk(cs)(t)]
    print('%-40s DEV blk %3d nf %3d win %3d save %+6.0f folds %s | VAL blk %3d nf %3d win %3d save %+6.0f'%(cs,n,nf,w,sv,[round(x) for x in fs],len(b),sum(t['nf'] for t in b),sum(t['p']>0 for t in b),-sum(t['p'] for t in b)))
