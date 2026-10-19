import json, math, sys, random
random.seed(7)

POS=json.load(open(sys.argv[1]))      # pos_feat.json
NEG=json.load(open(sys.argv[2]))      # neg_feat.json
POSFEED=json.load(open(sys.argv[3]))  # pos_feed.json (mint->{peak,...} or None)
NEGFEED=json.load(open(sys.argv[4]))  # neg_feed.json (mint->{peak,...})

FEATURES=["dev_buy_sol","n_cobundlers","cobundler_buys_same_slot","n_same_slot_sigs",
          "total_bundled_sol","buys_in_create_tx","total_sigs_pages",
          "creator_prior_sigs","creator_total_sigs","creator_age_slots"]

def ok(d): return d.get("status")=="ok" and d.get("create_slot")
pos=[d for d in POS.values() if ok(d)]
neg=[d for d in NEG.values() if ok(d)]
print(f"ok pos={len(pos)} ok neg={len(neg)}")

# active window from positives
pslots=sorted(d["create_slot"] for d in pos)
lo,hi=pslots[0],pslots[-1]
print(f"pos create_slot window: {lo}..{hi} span={hi-lo}")
neg_win=[d for d in neg if lo<=d["create_slot"]<=hi]
print(f"neg in window: {len(neg_win)} / {len(neg)}")
neg=neg_win

def peak_of(m):
    f=NEGFEED.get(m) or POSFEED.get(m)
    return (f or {}).get("peak")

def vals(rows,f):
    return [r[f] for r in rows if r.get(f) is not None]

def quant(xs,p):
    if not xs: return None
    xs=sorted(xs); i=min(len(xs)-1,int(round(p*(len(xs)-1)))); return xs[i]

def mw_u(a,b):
    # Mann-Whitney U with normal approx, tie correction. returns (AUC=P(pos>neg), z, p_two)
    n1,n2=len(a),len(b)
    if n1==0 or n2==0: return (None,None,None)
    allv=sorted([(v,0) for v in a]+[(v,1) for v in b])
    # rank with ties
    ranks=[0.0]*len(allv); i=0
    while i<len(allv):
        j=i
        while j+1<len(allv) and allv[j+1][0]==allv[i][0]: j+=1
        r=(i+j)/2.0+1
        for k in range(i,j+1): ranks[k]=r
        i=j+1
    R1=sum(ranks[k] for k in range(len(allv)) if allv[k][1]==0)
    U1=R1-n1*(n1+1)/2.0
    AUC=U1/(n1*n2)
    mu=n1*n2/2.0
    # tie correction
    from collections import Counter
    cnt=Counter(v for v,_ in allv); N=n1+n2
    tie=sum(t**3-t for t in cnt.values())
    sig=math.sqrt(n1*n2/12.0*((N+1)-tie/(N*(N-1))))
    if sig==0: return (AUC,0,1)
    z=(U1-mu)/sig
    p=2*(1-0.5*(1+math.erf(abs(z)/math.sqrt(2))))
    return (AUC,z,p)

print("\n=== FEATURE SEPARATION (pos vs neg, in-window) ===")
print(f"{'feature':22s}{'pos_med':>10s}{'neg_med':>10s}{'pos_p75':>10s}{'neg_p75':>10s}{'AUC':>7s}{'z':>8s}{'p':>10s}")
rows=[]
for f in FEATURES:
    a=vals(pos,f); b=vals(neg,f)
    if not a or not b:
        print(f"{f:22s}  (missing)"); continue
    AUC,z,p=mw_u(a,b)
    print(f"{f:22s}{quant(a,.5):>10.3f}{quant(b,.5):>10.3f}{quant(a,.75):>10.3f}{quant(b,.75):>10.3f}{AUC:>7.3f}{z:>8.2f}{p:>10.2e}")
    rows.append((f,AUC,z))

# --- threshold lift for top features ---
base=len(pos)/(len(pos)+len(neg))
print(f"\nbase rate (pos/opps in-window) = {base:.4f}  (pos={len(pos)} neg={len(neg)})")

def lift_rule(pred_pos_fn, name):
    tp=sum(1 for r in pos if pred_pos_fn(r))
    fp=sum(1 for r in neg if pred_pos_fn(r))
    sel=tp+fp
    if sel==0: print(f"  {name}: selects 0"); return
    prec=tp/sel; rec=tp/len(pos); lift=prec/base
    # runner enrichment among selected
    selmints=[r["mint"] for r in pos+neg if pred_pos_fn(r)]
    pks=[peak_of(m) for m in selmints]; pks=[x for x in pks if x is not None]
    run=sum(1 for x in pks if x>=2)/len(pks) if pks else None
    print(f"  {name}: sel={sel} prec={prec:.3f} lift={lift:.2f} recall={rec:.3f} runner_frac={run}")

print("\n=== SINGLE-FEATURE THRESHOLD RULES (in-sample, full window) ===")
for thr in [1,2,3]:
    lift_rule(lambda r,t=thr: (r.get("n_cobundlers") or 0)>=t, f"n_cobundlers>={thr}")
for thr in [2,3,5]:
    lift_rule(lambda r,t=thr: (r.get("cobundler_buys_same_slot") or 0)>=t, f"cobundler_buys_same_slot>={thr}")
for thr in [1,5,20]:
    lift_rule(lambda r,t=thr: (r.get("creator_prior_sigs") or 0)>=t, f"creator_prior_sigs>={thr}")
lift_rule(lambda r: 0.5<=(r.get("dev_buy_sol") or 0)<=2, "dev 0.5-2")
lift_rule(lambda r: 2<(r.get("dev_buy_sol") or 0)<=8, "dev 2-8")

# ---------- logistic regression (hand-rolled) with TIME split ----------
LRF=["dev_buy_sol","n_cobundlers","cobundler_buys_same_slot","total_bundled_sol",
     "creator_prior_sigs","creator_age_slots","buys_in_create_tx"]
def featvec(r):
    return [float(r.get(f) or 0.0) for f in LRF]

data=[(featvec(r),1,r["create_slot"],r["mint"]) for r in pos]+[(featvec(r),0,r["create_slot"],r["mint"]) for r in neg]
data.sort(key=lambda x:x[2])  # by slot (time)
cut=int(len(data)*0.7)
train=data[:cut]; test=data[cut:]
print(f"\n=== TIME-SPLIT: train={len(train)} (pos={sum(y for _,y,_,_ in train)}) test={len(test)} (pos={sum(y for _,y,_,_ in test)}) ===")

# standardize using train
import statistics as st
cols=list(zip(*[x[0] for x in train]))
mean=[st.mean(c) for c in cols]
sd=[(st.pstdev(c) or 1.0) for c in cols]
def norm(v): return [ (v[i]-mean[i])/sd[i] for i in range(len(v)) ]

def train_lr(train, l2=1.0, lr=0.1, epochs=4000):
    n=len(LRF); w=[0.0]*n; b=0.0
    X=[norm(x[0]) for x in train]; Y=[x[1] for x in train]
    npos=sum(Y); nneg=len(Y)-npos
    wpos=len(Y)/(2*npos); wneg=len(Y)/(2*nneg)  # class balance
    for ep in range(epochs):
        gw=[0.0]*n; gb=0.0
        for xi,yi in zip(X,Y):
            z=b+sum(w[j]*xi[j] for j in range(n))
            p=1/(1+math.exp(-max(-30,min(30,z))))
            cw=wpos if yi==1 else wneg
            d=(p-yi)*cw
            for j in range(n): gw[j]+=d*xi[j]
            gb+=d
        for j in range(n): w[j]-=lr*(gw[j]/len(X)+l2*w[j]/len(X))
        b-=lr*gb/len(X)
    return w,b
w,b=train_lr(train)
print("LR coefficients (standardized):")
for f,wi in sorted(zip(LRF,w),key=lambda t:-abs(t[1])):
    print(f"  {f:24s}{wi:+.3f}")

def prob(x):
    v=norm(x); z=b+sum(w[j]*v[j] for j in range(len(w)))
    return 1/(1+math.exp(-max(-30,min(30,z))))

# evaluate on test at several thresholds; also AUC
def auc(rows):
    ps=[(prob(x),y) for x,y,_,_ in rows]
    pos_s=[p for p,y in ps if y==1]; neg_s=[p for p,y in ps if y==0]
    AUC,z,pv=mw_u(pos_s,neg_s); return AUC
print(f"\ntest ROC-AUC = {auc(test):.3f}   train ROC-AUC = {auc(train):.3f}")
basetest=sum(y for _,y,_,_ in test)/len(test)
print(f"test base rate = {basetest:.4f}")
print("thr   sel  prec  recall  lift  runner_frac")
for thr in [0.3,0.4,0.5,0.6,0.7]:
    selr=[(x,y,m) for x,y,_,m in test if prob(x)>=thr]
    if not selr: print(f"{thr:.2f}  0"); continue
    tp=sum(y for _,y,_ in selr); prec=tp/len(selr); rec=tp/sum(y for _,y,_,_ in test)
    pks=[peak_of(m) for _,_,m in selr]; pks=[p for p in pks if p is not None]
    run=sum(1 for p in pks if p>=2)/len(pks) if pks else float("nan")
    print(f"{thr:.2f}  {len(selr):4d}  {prec:.3f}  {rec:.3f}  {prec/basetest:.2f}  {run:.3f}")
