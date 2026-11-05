# Reproduction check: rebuilt features (feat.pkl, CHECK window 465320000..465345000) vs frozen /home/moiz/sniper-vulture2x/data/cands.pkl
import sys,pickle,numpy as np,json,hashlib,collections
sys.dont_write_bytecode=True; sys.path.insert(0,'/home/moiz/sniper-vulture2x'); import gbm
B='/home/moiz/sniper-vulture2x/'; cfg=json.load(open(B+'VULTURE_v2.json'))
assert hashlib.sha256(open(B+'VULTURE_v2.json','rb').read()).hexdigest()=='b8d8c8311a5698dc9de081c623e6665a13046ccfc9c97fd878e471604a1492b0'
assert hashlib.sha256(open(B+cfg['model_file'],'rb').read()).hexdigest()==cfg['model_sha256']
M=pickle.load(open(B+cfg['model_file'],'rb')); THR=cfg['select']['score_thr']
def score(C):
    X=np.array([[float(c[f]) if c[f] is not None else -1 for f in M['F']] for c in C]);Bn=np.column_stack([np.searchsorted(M['E'][j],X[:,j]) for j in range(X.shape[1])])
    f=np.full(len(C),M['init'])
    for t in M['T']: f+=0.05*gbm.pred(t,Bn)
    return f
F=pickle.load(open('/home/moiz/sniper-data/vulture_probe_score/feat.pkl','rb'))['rows']
C=[c for c in pickle.load(open(B+'data/cands.pkl','rb')) if 465320000<=c['slot']<=465345000-12]
mine=[c for c in F if 465320000<=c['slot']<=465345000-12]
k=lambda c:(c['m'],c['slot'],c['idx'],round(c['sol'],6))
d={k(c):c for c in C}; e={k(c):c for c in mine}
both=sorted(set(d)&set(e)); print('frozen rows',len(C),'rebuilt',len(mine),'matched',len(both))
fa=score([d[x] for x in both]); fb=score([e[x] for x in both])
base=np.array([d[x]['sol']>=0.3 and d[x]['drop']>=3 for x in both])
pa=base&(fa>=THR); pb=base&(fb>=THR)
print('picks frozen',pa.sum(),'rebuilt',pb.sum(),'both',(pa&pb).sum(),'score corr',np.corrcoef(fa,fb)[0,1].round(4),'median |diff|',np.median(np.abs(fa-fb)))
diff=collections.Counter()
for x in both:
    for f in M['F']:
        a,b=d[x][f],e[x][f]
        if not (a==b or abs(float(a)-float(b))<1e-9*max(1,abs(float(b)))): diff[f]+=1
print('feature diffs on matched rows',dict(diff))
