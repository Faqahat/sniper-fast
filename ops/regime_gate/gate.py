#!/usr/bin/env python3
import json,statistics as st
rows=json.load(open("/root/regime_gate/timeline.json"))
for r in rows: r["pump"]=1 if r["peak12"]>=1.2 else 0

def gated(sub,K,thr,warmup_trade=False):
    # causal rolling pump-rate of last K launches BEFORE current; trade if rate>=thr
    nets=[];taken=0
    for i in range(len(sub)):
        if i<K:
            if warmup_trade: nets.append(sub[i]["net"]); taken+=1
            continue
        pr=sum(sub[j]["pump"] for j in range(i-K,i))/K
        if pr>=thr:
            nets.append(sub[i]["net"]); taken+=1
    N=len(sub)
    if not nets: return {"K":K,"thr":thr,"trades":0,"duty":0,"mean":0,"tot":0,"win":0}
    return {"K":K,"thr":thr,"trades":taken,"duty":taken/N,
            "mean":st.mean(nets),"tot":sum(nets),"win":sum(1 for n in nets if n>0)/len(nets)}

def ungated(sub):
    nets=[r["net"] for r in sub]
    return {"trades":len(nets),"duty":1.0,"mean":st.mean(nets),"tot":sum(nets),
            "win":sum(1 for n in nets if n>0)/len(nets)}

print("=== FULL TIMELINE ===")
u=ungated(rows)
print("UNGATED: trades=%d duty=1.00 mean=%+.4f tot=%+.2f win=%.1f%%"%(u["trades"],u["mean"],u["tot"],u["win"]*100))
print("GATED sweep (in-sample, full timeline):")
print(" K   thr  trades duty  meanNet  totNet  win%")
best=None
for K in (20,50,100,200):
    for thr in (0.20,0.25,0.30,0.35,0.40):
        g=gated(rows,K,thr)
        print(" %3d %.2f %5d  %.2f  %+.4f %+7.2f %5.1f"%(K,thr,g["trades"],g["duty"],g["mean"],g["tot"],g["win"]*100))

# ===== OOS 60/40 chronological =====
cut=int(0.6*len(rows))
train=rows[:cut]; valid=rows[cut:]
print("\n=== OOS SPLIT (chrono 60/40) ===")
print("train n=%d windows=%s"%(len(train),dict((w,sum(1 for r in train if r['window']==w)) for w in ('backtest','paper','fresh'))))
print("valid n=%d windows=%s"%(len(valid),dict((w,sum(1 for r in valid if r['window']==w)) for w in ('backtest','paper','fresh'))))
# tune on train: maximize total net with duty>=0.15 (need meaningful activity)
cand=[]
for K in (20,50,100,200):
    for thr in (0.20,0.25,0.30,0.35,0.40):
        g=gated(train,K,thr)
        if g["duty"]>=0.15: cand.append(g)
cand.sort(key=lambda g:g["tot"],reverse=True)
print("\nTRAIN best by totNet (duty>=0.15):")
for g in cand[:3]:
    print("  K=%d thr=%.2f trades=%d duty=%.2f mean=%+.4f tot=%+.2f win=%.1f%%"%(g["K"],g["thr"],g["trades"],g["duty"],g["mean"],g["tot"],g["win"]*100))
bestK=cand[0]["K"]; bestThr=cand[0]["thr"]
print("\n--- VALIDATION (last 40%%, tuned K=%d thr=%.2f) ---"%(bestK,bestThr))
uv=ungated(valid)
gv=gated(valid,bestK,bestThr)
print("UNGATED valid: trades=%d mean=%+.4f tot=%+.2f win=%.1f%%"%(uv["trades"],uv["mean"],uv["tot"],uv["win"]*100))
print("GATED   valid: trades=%d duty=%.2f mean=%+.4f tot=%+.2f win=%.1f%%"%(gv["trades"],gv["duty"],gv["mean"],gv["tot"],gv["win"]*100))

# fraction of quiet-window losses avoided by the tuned gate
quiet=[r for r in valid if r["window"] in ("paper","fresh")]
# simulate gate decision over full valid to know which quiet launches are traded
def decisions(sub,K,thr):
    dec=[]
    for i in range(len(sub)):
        if i<K: dec.append(False); continue
        pr=sum(sub[j]["pump"] for j in range(i-K,i))/K
        dec.append(pr>=thr)
    return dec
dec=decisions(valid,bestK,bestThr)
q_traded=[valid[i] for i in range(len(valid)) if valid[i]["window"] in("paper","fresh") and dec[i]]
q_all=[valid[i] for i in range(len(valid)) if valid[i]["window"] in("paper","fresh")]
q_loss_all=sum(r["net"] for r in q_all if r["net"]<0)
q_loss_traded=sum(r["net"] for r in q_traded if r["net"]<0)
print("\nQuiet-window (paper+fresh) in validation: n=%d, traded_by_gate=%d (duty=%.2f)"%(len(q_all),len(q_traded),len(q_traded)/len(q_all) if q_all else 0))
print("  total quiet losses = %+.2f ; losses still taken by gate = %+.2f ; avoided = %.1f%%"%(
    q_loss_all,q_loss_traded,100*(1-q_loss_traded/q_loss_all) if q_loss_all else 0))
