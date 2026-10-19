#!/usr/bin/env python3
import json,statistics as st,random
rows=json.load(open("/root/regime_gate/timeline.json"))
MULT=1.2
for r in rows:
    r["pump"]=1 if r["peak12"]>=MULT else 0
# inter-launch slot gaps
gaps=[rows[i]["slot"]-rows[i-1]["slot"] for i in range(1,len(rows))]
gaps_s=sorted(gaps)
print("inter-launch slot gap: med=%d p90=%d max=%d (0.4s/slot => med %.1fs)"%(
    gaps_s[len(gaps_s)//2],gaps_s[int(.9*len(gaps_s))],gaps_s[-1],gaps_s[len(gaps_s)//2]*0.4))

def autocorr(x,lag):
    n=len(x)-lag
    if n<10: return None
    a=x[:-lag] if lag>0 else x; b=x[lag:]
    ma=sum(a)/len(a); mb=sum(b)/len(b)
    num=sum((a[i]-ma)*(b[i]-mb) for i in range(len(a)))
    da=sum((v-ma)**2 for v in a)**.5; db=sum((v-mb)**2 for v in b)**.5
    if da==0 or db==0: return 0.0
    return num/(da*db)

def report_block(label,sub):
    pump=[r["pump"] for r in sub]
    net=[r["net"] for r in sub]
    print("\n--- %s (n=%d, pumprate=%.1f%%, meanNet=%+.4f) ---"%(label,len(sub),100*sum(pump)/len(sub),st.mean(net)))
    print("  lag :  ac_pump   ac_net")
    for lag in (1,2,3,5,10,20,50):
        ap=autocorr(pump,lag); an=autocorr(net,lag)
        if ap is None: continue
        print("  %3d : %+8.3f %+8.3f"%(lag,ap,an))

# global and per-window
report_block("GLOBAL (all windows stitched)",rows)
for w in ("backtest","paper","fresh"):
    report_block("WITHIN %s"%w,[r for r in rows if r["window"]==w])
# continuous paper+fresh stretch (nearly contiguous)
report_block("WITHIN paper+fresh (contiguous quiet stretch)",[r for r in rows if r["window"] in ("paper","fresh")])

# Does causal rolling pump-rate predict the NEXT launch's pump & net? (the actionable gate signal)
print("\n=== Causal rolling-rate predictivity (signal uses K launches BEFORE current) ===")
def rolling_pred(sub,K):
    xs=[]; yp=[]; yn=[]
    for i in range(len(sub)):
        if i<K: continue
        pr=sum(sub[j]["pump"] for j in range(i-K,i))/K
        xs.append(pr); yp.append(sub[i]["pump"]); yn.append(sub[i]["net"])
    if len(xs)<20: return None
    # corr(signal, pump_i) and corr(signal, net_i)
    def corr(a,b):
        ma=sum(a)/len(a); mb=sum(b)/len(b)
        num=sum((a[i]-ma)*(b[i]-mb) for i in range(len(a)))
        da=sum((v-ma)**2 for v in a)**.5; db=sum((v-mb)**2 for v in b)**.5
        return num/(da*db) if da and db else 0.0
    return corr(xs,yp),corr(xs,yn),len(xs)
for label,sub in [("GLOBAL",rows),("paper+fresh",[r for r in rows if r["window"] in("paper","fresh")]),("backtest",[r for r in rows if r["window"]=="backtest"])]:
    print(" %s:"%label)
    for K in (20,50,100):
        res=rolling_pred(sub,K)
        if res: print("   K=%3d  corr(rate,next_pump)=%+.3f  corr(rate,next_net)=%+.3f  n=%d"%(K,res[0],res[1],res[2]))

# Runs / clustering test vs shuffle (global pump series)
print("\n=== Clustering test: observed vs shuffled (pump label) ===")
def nruns(x):
    return 1+sum(1 for i in range(1,len(x)) if x[i]!=x[i-1])
for label,sub in [("GLOBAL",rows),("paper+fresh",[r for r in rows if r["window"] in("paper","fresh")])]:
    p=[r["pump"] for r in sub]
    obs=nruns(p)
    sh=[]
    for _ in range(2000):
        q=p[:]; random.shuffle(q); sh.append(nruns(q))
    msh=sum(sh)/len(sh)
    # fewer runs than shuffle => clustering/persistence
    below=sum(1 for v in sh if v<=obs)/len(sh)
    print("  %s: observed_runs=%d  shuffled_mean=%.1f  (fewer runs => clustering) p(shuf<=obs)=%.3f"%(label,obs,msh,below))
