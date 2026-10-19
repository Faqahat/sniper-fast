#!/usr/bin/env python3
"""STEPS 1-4 on the LAST-500 landed set. Builds his_500.json (tape+econ outcome),
selectivity decomposition (attempted vs passed-our-filter-but-ignored), OOS econ
(broad vs tight vs intermediate incl drawdown/variance), and the verdict/config.
Reuses econ102 engine + population trajectories. Writes JSON incrementally."""
import sys, json, math, statistics as st, random
from collections import Counter, defaultdict
sys.path.insert(0, "/root/econ_102"); import econ102 as E
random.seed(1)

FEAT = json.load(open("/root/last500/feat_500.json"))
POP  = json.load(open("/root/profit_backtest/creates.json"))
TRAJ = {t["mint"]: t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
EXT  = json.load(open("/root/attempt_filter/ext_buys.json"))["buys"]
AO   = [r for r in json.load(open("/root/attempt_filter/att_outcomes.json")) if r.get("net_R") is not None]

def mean(xs): return sum(xs)/len(xs) if xs else float('nan')
def winr(xs): return sum(1 for x in xs if x>0)/len(xs) if xs else float('nan')
def pct(xs,p):
    if not xs: return float('nan')
    s=sorted(xs); return s[min(len(s)-1,int(round(p*(len(s)-1))))]
def ci(xs,n=1500):
    if not xs: return (float('nan'),float('nan'))
    bs=sorted(mean([random.choice(xs) for _ in xs]) for _ in range(n)); return (bs[int(.025*n)],bs[int(.975*n)])
def van(c): return (c.get("mayhem") or 0)==0 and (c.get("holder_reward") or 0)==0 and (c.get("cashback") or 0)==0

# ---------- econ outcome for a feat row (his landed, from its own series) ----------
def econ_from_series(row, size=0.5):
    ser = row.get("series"); floor = row.get("floor_px")
    if not ser or not floor or floor<=0: return None
    entry = floor*E.ENTRY_MULT
    s=[(a,c) for (a,b,c) in ser] if (ser and len(ser[0])==3) else [(a,b) for (a,b) in ser]
    net,_,_ = E.simulate(entry, row["create_slot"], s, E.SHIP, size)
    g = E.gross_only(entry, row["create_slot"], s, E.SHIP)
    return net, g

OUT={}
# =========================================================================
# STEP 1 — his_500 tape
# =========================================================================
his=[]
for r in FEAT:
    if not r.get("create_found"): continue
    o = econ_from_series(r)
    rr = dict(r); rr.pop("series", None)
    rr["net_R"], rr["gross_R"] = (o if o else (None,None))
    his.append(rr)
json.dump(his, open("/root/last500/his_500.json","w"), default=str)

landed_mints = {r["mint"] for r in FEAT}
with_out=[r for r in his if r["net_R"] is not None]
devs=[r["dev_buy"] for r in his if r.get("dev_buy") is not None]
print("="*80); print("STEP 1 — HIS LAST-500 LANDED TAPE")
print("="*80)
print(f"landed mints base={len(FEAT)}  create_found={len(his)}  with econ outcome={len(with_out)}")
sl=[r["create_slot"] for r in his if r.get("create_slot")]
print(f"create-slot span {min(sl)}..{max(sl)}  (~{(max(sl)-min(sl))*0.4/3600:.1f}h at 0.4s/slot)")
print(f"curve dev_buy SOL: p25={pct(devs,.25):.2f} med={pct(devs,.5):.2f} p75={pct(devs,.75):.2f} mean={mean(devs):.2f}")
print(f"vanilla: {100*mean([r['vanilla'] for r in his if r.get('vanilla') is not None]):.0f}%")
print(f"creator_fee==0: {100*mean([1 if (r.get('creator_fee_bps') or 0)==0 else 0 for r in his]):.0f}%")
co=[r.get('cosnipers_slot0') for r in his if r.get('cosnipers_slot0') is not None]
print(f"co-snipers in create slot: med={pct(co,.5):.1f} mean={mean(co):.2f}  >=1: {100*mean([1 if x>=1 else 0 for x in co]):.0f}%")
bd=[r.get('buy_delta') for r in his if r.get('buy_delta') is not None]
print(f"his buy delta (buyslot-createslot): {dict(sorted(Counter(bd).items()))}")
spray=[r.get('spray') for r in his if r.get('spray')]
print(f"spray (buys/mint incl fails): med={pct(spray,.5):.0f} mean={mean(spray):.1f} p90={pct(spray,.9):.0f}")
soc=[r.get('has_image') for r in his if r.get('has_image') is not None]
print(f"metadata has image/uri: {100*mean([1 if x else 0 for x in soc]):.0f}% (n={len(soc)})")
tip=[r.get('jito_tip_create') for r in his if r.get('jito_tip_create') is not None]
print(f"jito-tip in CREATE tx: {100*mean([1 if (x or 0)>0 else 0 for x in tip]):.0f}% have one (dev's, not his)")
pk=[r['peak_r'] for r in his if r.get('peak_r')]
print(f"token peak_r: med={pct(pk,.5):.2f} >=2x:{sum(1 for x in pk if x>=2)}/{len(pk)}")
if with_out:
    nr=[r['net_R'] for r in with_out]; gr=[r['gross_R'] for r in with_out]
    print(f"econ outcome (floor*1.02, shipped ladder, 0.5SOL): net mean={mean(nr):+.4f} win={100*winr(nr):.0f}% gross_win={100*winr(gr):.0f}% totR={sum(nr):+.1f}")
# hour of day
bt=[r.get('blockTime') for r in his if r.get('blockTime')]
if bt:
    import datetime
    hrs=Counter(datetime.datetime.utcfromtimestamp(x).hour for x in bt)
    print("hour-of-day (UTC) launches:",dict(sorted(hrs.items())))
OUT["step1"]={"n_found":len(his),"n_out":len(with_out),"dev_med":pct(devs,.5),"vanilla_pct":mean([r['vanilla'] for r in his if r.get('vanilla') is not None]),
    "cosnipe_ge1":mean([1 if x>=1 else 0 for x in co]),"net_mean":mean([r['net_R'] for r in with_out]) if with_out else None,
    "win":winr([r['net_R'] for r in with_out]) if with_out else None}

# =========================================================================
# STEP 2 — SELECTIVITY DECOMPOSITION
# =========================================================================
print("\n"+"="*80); print("STEP 2 — SELECTIVITY: attempted vs passed-our-filter-but-ignored")
print("="*80)
# his full attempt set (any buy, landed or failed)
ATT_MINTS = {b["mint"] for b in EXT}
# population labeled
lo=min(c["create_slot"] for c in POP); hi=max(c["create_slot"] for c in POP)
pop_att=[c for c in POP if c["mint"] in ATT_MINTS]
pop_ign=[c for c in POP if c["mint"] not in ATT_MINTS]
print(f"population (unbiased 1/16 sample) n={len(POP)} slots {lo}..{hi}")
print(f"  attempted (in his buy set): {len(pop_att)}  => est attempt rate {100*len(pop_att)/len(POP):.1f}%")
def ourfilter(c): return (c.get('dev_buy') or 0)>=2 and van(c)
of=[c for c in POP if ourfilter(c)]
print(f"  OUR FILTER (curve dev>=2 & vanilla) fires on {len(of)}/{len(POP)} = {100*len(of)/len(POP):.0f}%")
of_att=[c for c in of if c["mint"] in ATT_MINTS]
print(f"  of our-filter-pass, he attempted {len(of_att)} ({100*len(of_att)/max(1,len(of)):.0f}%)")

def feats_of(c):
    t=TRAJ.get(c["mint"],{})
    return {"dev":c.get('dev_buy') or 0,"vanilla":1 if van(c) else 0,
            "cosnipe":t.get("cosnipers",0),"nflow":t.get("n",0) or 0,
            "cu":1 if False else 0}
# lift table: P(X|att) vs P(X|pop)  (att = enriched 186+our label; use population-labeled att here)
print("\n-- feature separation (within population): lift = P(X|attempted)/P(X|pop) --")
feat_defs=[
 ("dev>=3.0 SOL", lambda c:(c.get('dev_buy') or 0)>=3.0),
 ("dev>=2.0 SOL", lambda c:(c.get('dev_buy') or 0)>=2.0),
 ("dev>=1.0 SOL", lambda c:(c.get('dev_buy') or 0)>=1.0),
 ("dev>=0.5 SOL", lambda c:(c.get('dev_buy') or 0)>=0.5),
 ("vanilla", van),
 ("creator_fee==0", lambda c:(c.get('creator_fee_bps') or 0)==0),
 ("cosnipe>=1 (contemp)", lambda c:TRAJ.get(c["mint"],{}).get("cosnipers",0)>=1),
 ("cosnipe>=2 (contemp)", lambda c:TRAJ.get(c["mint"],{}).get("cosnipers",0)>=2),
 ("earlyflow n>=3 (contemp)", lambda c:(TRAJ.get(c["mint"],{}).get("n",0) or 0)>=3),
]
sep=[]
for name,fn in feat_defs:
    pa=mean([1 if fn(c) else 0 for c in pop_att])
    pp=mean([1 if fn(c) else 0 for c in POP])
    lift=pa/pp if pp>0 else float('inf')
    sep.append((name,pa,pp,lift))
    print(f"  {name:28} P(att)={pa:.2f} P(pop)={pp:.2f} lift={lift:.2f}")
OUT["step2_lift"]=[{"feat":n,"p_att":a,"p_pop":p,"lift":l} for n,a,p,l in sep]

# tightest pre-buy rule reproducing his ~1% attempt set (precision/recall vs population label)
print("\n-- candidate pre-buy rules: coverage + precision/recall for his attempt label --")
rules=[
 ("dev>=0.5 & vanilla", lambda c:(c.get('dev_buy') or 0)>=0.5 and van(c)),
 ("dev>=1.0 & vanilla", lambda c:(c.get('dev_buy') or 0)>=1.0 and van(c)),
 ("dev>=2.0 & vanilla", lambda c:(c.get('dev_buy') or 0)>=2.0 and van(c)),
 ("dev>=3.0 & vanilla", lambda c:(c.get('dev_buy') or 0)>=3.0 and van(c)),
 ("dev>=1.0 & vanilla & cosnipe>=1", lambda c:(c.get('dev_buy') or 0)>=1.0 and van(c) and TRAJ.get(c["mint"],{}).get("cosnipers",0)>=1),
 ("dev>=0.5 & vanilla & cosnipe>=1", lambda c:(c.get('dev_buy') or 0)>=0.5 and van(c) and TRAJ.get(c["mint"],{}).get("cosnipers",0)>=1),
 ("dev>=2.0 & vanilla & cosnipe>=1", lambda c:(c.get('dev_buy') or 0)>=2.0 and van(c) and TRAJ.get(c["mint"],{}).get("cosnipers",0)>=1),
]
rule_rows=[]
for name,fn in rules:
    fired=[c for c in POP if fn(c)]
    tp=[c for c in fired if c["mint"] in ATT_MINTS]
    cov=100*len(fired)/len(POP)
    prec=100*len(tp)/max(1,len(fired)); rec=100*len(tp)/max(1,len(pop_att))
    rule_rows.append({"rule":name,"coverage_pct":cov,"precision":prec,"recall":rec,"n_fire":len(fired)})
    print(f"  {name:36} cover={cov:4.1f}%  precision={prec:4.0f}%  recall={rec:4.0f}%  (n_fire={len(fired)})")
OUT["step2_rules"]=rule_rows

# simple logit (gradient descent) attempted~dev,vanilla,cosnipe on full population
def logit_fit(X,y,iters=4000,lr=0.1):
    import math
    nX=len(X[0]); w=[0.0]*nX; b=0.0
    # standardize
    mu=[mean([x[j] for x in X]) for j in range(nX)]
    sd=[st.pstdev([x[j] for x in X]) or 1 for j in range(nX)]
    Xs=[[(x[j]-mu[j])/sd[j] for j in range(nX)] for x in X]
    for _ in range(iters):
        gw=[0.0]*nX; gb=0.0
        for xi,yi in zip(Xs,y):
            z=b+sum(w[j]*xi[j] for j in range(nX)); p=1/(1+math.exp(-max(-30,min(30,z))))
            e=p-yi
            for j in range(nX): gw[j]+=e*xi[j]
            gb+=e
        for j in range(nX): w[j]-=lr*gw[j]/len(X)
        b-=lr*gb/len(X)
    return w,b,mu,sd
X=[[feats_of(c)["dev"],feats_of(c)["vanilla"],feats_of(c)["cosnipe"],feats_of(c)["nflow"]] for c in POP]
y=[1 if c["mint"] in ATT_MINTS else 0 for c in POP]
w,b,mu,sd=logit_fit(X,y)
print(f"\n-- logit attempted ~ [dev,vanilla,cosnipe,nflow] standardized weights --")
for nm,wj in zip(["dev_buy","vanilla","cosnipe","nflow"],w):
    print(f"  {nm:10} w={wj:+.3f}")
OUT["step2_logit"]={nm:wj for nm,wj in zip(["dev_buy","vanilla","cosnipe","nflow"],w)}
print("pre-buy knowable (create-tx): dev_buy, vanilla, creator_fee. contemporaneous (only after firing): cosnipe, earlyflow.")

# =========================================================================
# STEP 3 — DOES SELECTIVITY HELP?  OOS econ, drawdown/variance
# =========================================================================
print("\n"+"="*80); print("STEP 3 — OOS ECON: broad vs tight vs intermediate (drawdown/variance)")
print("="*80)
def outc(c,size=0.5):
    t=TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"): return None
    e=t["entry_px"]*E.ENTRY_MULT; s=[(a,bb) for a,bb in t["series"]]
    return (E.simulate(e,t["create_slot"],s,E.SHIP,size)[0], E.gross_only(e,t["create_slot"],s,E.SHIP), c["create_slot"])
def max_drawdown(seq):
    peak=0.0; cum=0.0; mdd=0.0
    for x in seq:
        cum+=x; peak=max(peak,cum); mdd=min(mdd,cum-peak)
    return mdd
SPAN_HR=(hi-lo)*0.4/3600
def evalrule(name,fn,size=0.5,split=True):
    rows=[outc(c,size) for c in POP if fn(c)]
    rows=[r for r in rows if r]
    rows.sort(key=lambda r:r[2])
    nets=[r[0] for r in rows]; gross=[r[1] for r in rows]
    res={"name":name,"n":len(nets),"mean":mean(nets),"win":winr(nets),"totR":sum(nets),
         "sd":st.pstdev(nets) if len(nets)>1 else 0,"mdd":max_drawdown(nets),
         "trades_per_hr":len(nets)/SPAN_HR if SPAN_HR else None,
         "gross_win":winr(gross)}
    if split and len(rows)>=20:
        mid=len(rows)//2; tr=nets[:mid]; vl=nets[mid:]
        res["val_mean"]=mean(vl); res["val_win"]=winr(vl); res["val_n"]=len(vl)
        res["train_mean"]=mean(tr)
    return res
cfgs=[
 ("BROAD dev>=2 & vanilla (~our tightest actionable)", lambda c:(c.get('dev_buy') or 0)>=2 and van(c)),
 ("dev>=0.5 & vanilla (his loose p25)", lambda c:(c.get('dev_buy') or 0)>=0.5 and van(c)),
 ("dev>=1.0 & vanilla (his median)", lambda c:(c.get('dev_buy') or 0)>=1 and van(c)),
 ("dev>=3.0 & vanilla", lambda c:(c.get('dev_buy') or 0)>=3 and van(c)),
 ("dev>=5.0 & vanilla (tight)", lambda c:(c.get('dev_buy') or 0)>=5 and van(c)),
 ("dev>=1 & vanilla & cosnipe>=1 (~his realized)", lambda c:(c.get('dev_buy') or 0)>=1 and van(c) and TRAJ.get(c["mint"],{}).get("cosnipers",0)>=1),
 ("dev>=3 & vanilla & cosnipe>=1 (tightest)", lambda c:(c.get('dev_buy') or 0)>=3 and van(c) and TRAJ.get(c["mint"],{}).get("cosnipers",0)>=1),
]
step3=[]
hdr=f"{'rule':52} {'n':>4} {'mean':>8} {'win':>5} {'totR':>7} {'sd':>6} {'mDD':>7} {'tr/hr':>6} {'VALmean':>8} {'VALwin':>6}"
print(hdr)
for name,fn in cfgs:
    r=evalrule(name,fn)
    step3.append(r)
    print(f"{name:52} {r['n']:4d} {r['mean']:+8.4f} {100*r['win']:4.0f}% {r['totR']:+7.2f} {r['sd']:6.3f} {r['mdd']:+7.2f} {r.get('trades_per_hr') or 0:6.2f} "
          f"{r.get('val_mean',float('nan')):+8.4f} {100*(r.get('val_win') or 0):5.0f}%")
OUT["step3"]=step3
# his actual attempts reference
hn=[r['net_R'] for r in AO]
print(f"\nHIS ACTUAL ATTEMPTS (13h, n={len(AO)}): mean={mean(hn):+.4f} win={100*winr(hn):.0f}% sd={st.pstdev(hn):.3f} totR={sum(hn):+.2f}")

json.dump(OUT, open("/root/last500/analysis.json","w"), indent=2, default=str)
print("\nwrote /root/last500/analysis.json , his_500.json")
