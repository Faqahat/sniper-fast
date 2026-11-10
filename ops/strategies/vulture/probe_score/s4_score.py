# Step 4: score every probe envelope dump + every fill with the frozen VULTURE-2 model; join by (mint, slot, idx).
import sys,pickle,numpy as np,json,hashlib,collections
sys.dont_write_bytecode=True; sys.path.insert(0,'/home/it/sniper-studies/sniper-vulture2x'); import gbm
B='/home/it/sniper-studies/sniper-vulture2x/'; cfg=json.load(open(B+'VULTURE_v2.json'))
assert hashlib.sha256(open(B+'VULTURE_v2.json','rb').read()).hexdigest()=='b8d8c8311a5698dc9de081c623e6665a13046ccfc9c97fd878e471604a1492b0'
assert hashlib.sha256(open(B+cfg['model_file'],'rb').read()).hexdigest()==cfg['model_sha256']=='d8db5e116e131309613cc613a1239fe6bbe397b5357a0405810199f874d08eb3'
M=pickle.load(open(B+cfg['model_file'],'rb')); THR=cfg['select']['score_thr']; EDG=cfg['size']['edges']; SZ=cfg['size']['sizes']
def score(C):
    X=np.array([[float(c[f]) if c[f] is not None else -1 for f in M['F']] for c in C]);Bn=np.column_stack([np.searchsorted(M['E'][j],X[:,j]) for j in range(X.shape[1])])
    f=np.full(len(C),M['init'])
    for t in M['T']: f+=0.05*gbm.pred(t,Bn)
    return f
D='/home/it/sniper-data/vulture_probe_score/'
P=pickle.load(open(D+'probe.pkl','rb'))
out={}
for var in ('feat','feat_ex2g'):
    F=pickle.load(open(D+var+'.pkl','rb')); R=[c for c in F['rows'] if 465401500<=c['slot']<=465405100]
    f=score(R)
    for c,x in zip(R,f): c['score']=float(x); c['tier']=SZ[int(np.searchsorted(EDG,x))]
    idx=collections.defaultdict(list)
    for c in R: idx[(c['m'],c['slot'])].append(c)
    J={}
    for run in ('r30','r31'):
        for d in P[run]['dumps']:
            cand=idx.get((d['mint'],d['slot']),[])
            best=min(cand,key=lambda c:(abs(c['idx']-d['idx']),abs(c['sol']-d['sell'])),default=None)
            ok=best is not None and best['idx']==d['idx'] and abs(best['sol']-d['sell'])<0.002
            J[d['sig']]=dict(run=run,d=d,row=best if ok else None,near=best)
    out[var]=dict(rows=R,J=J,tape=F.get('tape'),maxi=F.get('maxi'),tape_lo=F['tape_lo'],s1=F['s1'])
    for run in ('r30','r31'):
        js=[v for v in J.values() if v['run']==run]; m=[v for v in js if v['row']]
        pk=[v for v in m if v['row']['score']>=THR]
        print(var,run,'dumps',len(js),'matched',len(m),'model picks (score>=thr)',len(pk),
              'unmatched reasons: no row same mint+slot',sum(1 for v in js if v['near'] is None),'idx/sol mismatch',sum(1 for v in js if v['near'] is not None and not v['row']))
    print(var,'all rows in window (any envelope dump in tape)',len(R),'picks',sum(c['score']>=THR and c['sol']>=0.3 and c['drop']>=3 for c in R))
pickle.dump(out,open(D+'scored.pkl','wb'),protocol=5)
