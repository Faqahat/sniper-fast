from lib import *
import numpy as np, math, datetime, sys
T=[t for t in load() if t['kind']=='T2']
ATT0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; ATT1=ATT0+40*60*10**9
def x(t):
    whf=t['whf'] if t['whf'] is not None and t['whf']>=0 else 0.0
    return [math.log1p(t['n60']), math.log1p(t['nb50'] if t['nb50'] is not None else t['n60']), min(whf,10), 1.0 if (t['whd'] or 0)>0 else 0.0,
            math.log1p(t['whd'] or 0), min(t['coh'] or 0,5), 1.0 if (t['since_last'] or 0)>=1 else 0.0, t['pct'], math.log((t['trig_sol'] or 1e9)/1e9), math.log(t['vsol']/1e9), math.log1p(t['age_slots'] or 0)]
NAMES=['ln_n60','ln_nb50','whf','has_hist','ln_whd','coh','since1','pct','ln_trigsol','ln_vsol','ln_age']
sel=[int(a) for a in sys.argv[1].split(',')] if len(sys.argv)>1 else list(range(len(NAMES)))
X=np.array([[x(t)[i] for i in sel] for t in T]); y=np.array([1.0 if t['nf'] else 0.0 for t in T]); p=np.array([t['p'] for t in T])
dev=np.array([t['split']=='DEV' for t in T]); val=~dev; noatt=np.array([not ATT0<=t['t']<ATT1 for t in T])
def fit(Xa,ya,l2=1.0):
    mu=Xa.mean(0); sd=Xa.std(0)+1e-9; Z=(Xa-mu)/sd; Z=np.c_[np.ones(len(Z)),Z]; w=np.zeros(Z.shape[1])
    for it in range(200):
        q=1/(1+np.exp(-Z@w)); g=Z.T@(q-ya)+l2*np.r_[0,w[1:]]; H=(Z*(q*(1-q))[:,None]).T@Z+l2*np.diag(np.r_[0,np.ones(len(w)-1)])
        w-=np.linalg.solve(H,g)
    return lambda Xb: 1/(1+np.exp(-np.c_[np.ones(len(Xb)),(Xb-mu)/sd]@w)), w
def auc(s,yy):
    o=np.argsort(s); r=np.empty(len(s)); r[o]=np.arange(len(s)); n1=yy.sum(); n0=len(yy)-n1
    return (r[yy==1].sum()-n1*(n1-1)/2)/(n1*n0)
# chronological folds in DEV: train on earlier folds, score next (walk-forward)
idx=np.where(dev)[0]; k=len(idx)//4
oos=np.full(len(T),np.nan)
for f in range(1,4):
    tr=idx[:k*f]; te=idx[k*f:k*(f+1)] if f<3 else idx[k*f:]
    m,_=fit(X[tr],y[tr]); oos[te]=m(X[te])
m,w=fit(X[dev],y[dev]); s=m(X)
print('features',[NAMES[i] for i in sel]); print('coef',np.round(w,2))
print('AUC(nf) DEV in-sample %.3f  DEV walk-forward %.3f  VAL %.3f  VAL-noatt %.3f'%(auc(s[dev],y[dev]),auc(oos[~np.isnan(oos)],y[~np.isnan(oos)]),auc(s[val],y[val]),auc(s[val&noatt],y[val&noatt])))
# threshold chosen on DEV in-sample: maximize savings
best=None
for thr in np.arange(0.10,0.6,0.01):
    b=dev&(s>=thr); sv=-p[b].sum()
    if best is None or sv>best[0]: best=(sv,thr)
for thr in sorted(set([round(best[1],2),0.2,0.25,0.3,0.35,0.4])):
    out=[]
    for nm,msk in [('DEV',dev),('DEVwf',~np.isnan(oos)),('VAL',val),('VALnoatt',val&noatt)]:
        sc=oos if nm=='DEVwf' else s
        b=msk&(np.nan_to_num(sc,nan=-1)>=thr)
        out.append('%s blk %3d nf %3d win %3d save %+6.0f'%(nm,b.sum(),y[b].sum(),(p[b]>0).sum(),-p[b].sum()))
    print('thr %.2f%s | '%(thr,'*' if abs(thr-best[1])<1e-9 else ' ')+' | '.join(out))
