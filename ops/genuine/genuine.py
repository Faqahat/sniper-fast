#!/usr/bin/env python3
"""genuine: entry filters that buy GENUINE pump.fun tokens and skip ~1s instant-dumps.
Reuses econ102 exit+cost engine. WINNER exit. Honest delayed-fill accounting. OOS chrono split.
Historical replay only. No live trading."""
import json, sys, statistics as st
sys.path.insert(0,"/root/econ_102")
import econ102 as E

WINNER = {"derisk_frac":0.0,"ride_mult":2.0,"trail_frac":0.90,"cut_r":0.0,"ladder_frac":0.0,"cap_slots":15}
FILL   = E.ENTRY_MULT          # 1.02 priority-fee fill premium, applied to whatever price we transact at
SIZES  = [0.1,0.5,2.0]
DUMP_THR = 0.8                 # instant-dump = drops below 0.8x floor ...
DUMP_AGE = 3                   # ... within first 3 slots

ROWS = E.load_backtest()       # filter-passing creates (dev>=2, fee==0) joined to trajectories

def build():
    F=[]
    for c in ROWS:
        if not E.passes_shipped(c): continue
        t=c["traj"]; floor=t["entry_px"]
        if not floor: continue
        series=[(int(s),float(p)) for s,p in t["series"]]
        # instant-dump label on objective early path
        early=[p for (s,p) in series if s-t["create_slot"]<=DUMP_AGE]
        if early:
            is_dump = (min(early) < DUMP_THR*floor)
            has_path=True
        else:
            is_dump=None; has_path=False   # no early data
        F.append({"slot":c["create_slot"],"create_slot":t["create_slot"],"floor":floor,
                  "series":series,"cosnip":t["cosnipers"],"is_dump":is_dump,"has_path":has_path})
    F.sort(key=lambda f:f["slot"])
    return F

FEAT=build()
split=FEAT[len(FEAT)//2]["slot"]
TRAIN=[f for f in FEAT if f["slot"]<split]
VAL  =[f for f in FEAT if f["slot"]>=split]

def entry_at_age(f,N):
    """first poll with age>=N: returns (entry_slot, observed_px, remaining_path_after)."""
    cs=f["create_slot"]
    for i,(s,p) in enumerate(f["series"]):
        if s-cs>=N:
            return s,p,f["series"][i+1:]
    return None

def net_R_baseline(f,size):
    # buy-all same-slot: entry floor*FILL at create_slot, full path
    return E.simulate(f["floor"]*FILL, f["create_slot"], f["series"], WINNER, size)[0]

def net_R_delayed(f,size,entry_slot,obs_px,rem):
    # delayed entry: our fill = observed slot price * FILL (we still pay the in-slot priority premium)
    return E.simulate(obs_px*FILL, entry_slot, rem, WINNER, size)[0]

def maxdd(pnls_chrono):
    peak=0.0; cum=0.0; dd=0.0
    for x in pnls_chrono:
        cum+=x; peak=max(peak,cum); dd=min(dd,cum-peak)
    return dd

def summarize(trades):
    # trades: list of (slot, netR, is_dump_label_of_bought_token)
    if not trades: return None
    trades=sorted(trades,key=lambda x:x[0])
    pnls=[t[1] for t in trades]
    n=len(pnls); win=sum(1 for p in pnls if p>0)/n
    dumps=[t[2] for t in trades if t[2] is not None]
    dumprate=(sum(1 for d in dumps if d)/len(dumps)) if dumps else float('nan')
    return {"n":n,"mean":sum(pnls)/n,"median":st.median(pnls),"win":win,
            "tot":sum(pnls),"dd":maxdd(pnls),"dumprate":dumprate}

# base denominators per split
def base_count(split_set):
    return len(split_set)                       # all filter-passing = what buy-all buys
def base_haspath(split_set):
    return len([f for f in split_set if f["has_path"]])
def base_dumprate(split_set):
    d=[f["is_dump"] for f in split_set if f["has_path"]]
    return sum(1 for x in d if x)/len(d) if d else float('nan')

def fate_breakdown(split_set):
    """Economic 'dump' reality vs the owner's 60-80% claim. Among has-path tokens, classify by peak r."""
    hp=[f for f in split_set if f["has_path"]]
    def peakr(f):
        ps=[p for (s,p) in f["series"]]
        return max(ps)/f["floor"] if ps else 1.0
    def minr3(f):
        e=[p for (s,p) in f["series"] if s-f["create_slot"]<=DUMP_AGE]
        return min(e)/f["floor"] if e else 1.0
    n=len(hp)
    hard=sum(1 for f in hp if minr3(f)<0.8)                 # hard instant-dump
    nopump=sum(1 for f in hp if peakr(f)<1.1)               # never pumps 10% (economic dud)
    bled=sum(1 for f in hp if minr3(f)<1.0)                 # dips below floor in first 3 slots
    pumped=sum(1 for f in hp if peakr(f)>=1.5)              # genuine runner (>=1.5x peak)
    return {"n":n,"hard_dump<0.8x_3slot":hard/n,"dips<floor_3slot":bled/n,
            "never_1.1x_peak":nopump/n,"ran>=1.5x_peak":pumped/n}

# ---------- strategy trade generators ----------
def gen_baseline(split_set,size):
    return [(f["slot"],net_R_baseline(f,size),f["is_dump"]) for f in split_set]

def gen_cosnipe(split_set,size,K):
    out=[]
    for f in split_set:
        if f["cosnip"]<K: continue
        e=entry_at_age(f,1)          # fire ~create+1, after seeing in-slot co-snipers
        if e is None: continue
        es,px,rem=e
        out.append((f["slot"],net_R_delayed(f,size,es,px,rem),f["is_dump"]))
    return out

def gen_survival(split_set,size,N,thr):
    out=[]
    for f in split_set:
        e=entry_at_age(f,N)
        if e is None: continue
        es,px,rem=e
        if px < thr*f["floor"]: continue   # already dumping -> skip
        out.append((f["slot"],net_R_delayed(f,size,es,px,rem),f["is_dump"]))
    return out

def gen_momentum(split_set,size,N,rthr):
    out=[]
    for f in split_set:
        e=entry_at_age(f,N)
        if e is None: continue
        es,px,rem=e
        if px/f["floor"] < rthr: continue  # require upward tick
        out.append((f["slot"],net_R_delayed(f,size,es,px,rem),f["is_dump"]))
    return out

def gen_cosnipe_floor(split_set,size,K):
    # DIAGNOSTIC: co-snipe tokens bought at FLOOR same-slot (not achievable late, but isolates the signal)
    out=[]
    for f in split_set:
        if f["cosnip"]<K: continue
        out.append((f["slot"],net_R_baseline(f,size),f["is_dump"]))
    return out

def gen_combined(split_set,size,K,N,thr):
    out=[]
    for f in split_set:
        if f["cosnip"]<K: continue
        e=entry_at_age(f,N)
        if e is None: continue
        es,px,rem=e
        if px < thr*f["floor"]: continue
        out.append((f["slot"],net_R_delayed(f,size,es,px,rem),f["is_dump"]))
    return out

if __name__=="__main__":
    print("="*118)
    print(f"GENUINE-TOKEN ENTRY FILTERS | WINNER exit {WINNER} | fill premium {FILL}x | instant-dump=<{DUMP_THR}x floor within {DUMP_AGE} slots")
    print(f"filter-passing sample n={len(FEAT)} (has early path {base_count(FEAT)}) | chrono split slot={split} | TRAIN {len(TRAIN)} VAL {len(VAL)}")
    print(f"INSTANT-DUMP (<0.8x in 3 slots) BASE RATE: all={base_dumprate(FEAT)*100:.1f}%  TRAIN={base_dumprate(TRAIN)*100:.1f}%  VAL={base_dumprate(VAL)*100:.1f}%")
    fb=fate_breakdown(FEAT)
    print(f"FATE BREAKDOWN (has-path n={fb['n']}): hard-dump<0.8x_3slot={fb['hard_dump<0.8x_3slot']*100:.1f}%  dips<floor_3slot={fb['dips<floor_3slot']*100:.1f}%  never-1.1x-peak={fb['never_1.1x_peak']*100:.1f}%  ran>=1.5x-peak={fb['ran>=1.5x_peak']*100:.1f}%")
    print("="*118)
    SZ=0.5
    bden_v=base_count(VAL); bden_a=base_count(FEAT)
    strategies=[("BASELINE buy-all@floor",gen_baseline,{}),
        ("DIAG co-snipe K2 @FLOOR",gen_cosnipe_floor,{"K":2}),
        ("co-snipe K>=1",gen_cosnipe,{"K":1}),("co-snipe K>=2",gen_cosnipe,{"K":2}),("co-snipe K>=3",gen_cosnipe,{"K":3}),
        ("surv N1 thr0.9",gen_survival,{"N":1,"thr":0.9}),("surv N1 thr1.0",gen_survival,{"N":1,"thr":1.0}),
        ("surv N2 thr0.9",gen_survival,{"N":2,"thr":0.9}),("surv N2 thr1.0",gen_survival,{"N":2,"thr":1.0}),
        ("surv N3 thr0.9",gen_survival,{"N":3,"thr":0.9}),("surv N3 thr1.0",gen_survival,{"N":3,"thr":1.0}),
        ("mom N1 r1.1",gen_momentum,{"N":1,"rthr":1.1}),("mom N1 r1.3",gen_momentum,{"N":1,"rthr":1.3}),
        ("mom N2 r1.1",gen_momentum,{"N":2,"rthr":1.1}),("mom N2 r1.3",gen_momentum,{"N":2,"rthr":1.3}),
        ("mom N3 r1.1",gen_momentum,{"N":3,"rthr":1.1}),("mom N3 r1.3",gen_momentum,{"N":3,"rthr":1.3}),
        ("combo K2+survN1t0.9",gen_combined,{"K":2,"N":1,"thr":0.9}),
        ("combo K2+survN2t1.0",gen_combined,{"K":2,"N":2,"thr":1.0}),
        ("combo K1+survN2t1.0",gen_combined,{"K":1,"N":2,"thr":1.0}),
    ]
    hdr=f"{'strategy':22} | {'buy%VAL':>7} | {'dumpVAL':>7} | {'meanR':>8} {'win%':>5} {'totR':>7} {'maxDD':>7}  ||  {'IS meanR':>8} {'IS win':>6}"
    print("\nSIZE=0.5 SOL  (dumpVAL=instant-dump rate among BOUGHT in VAL; lower=better avoidance)\n"+hdr)
    print("-"*len(hdr))
    results={}
    for name,gen,kw in strategies:
        v=summarize(gen(VAL,SZ,**kw)); a=summarize(gen(TRAIN,SZ,**kw))
        if v is None: continue
        buypct=100*v["n"]/bden_v
        results[name]={"val":v,"train":a,"buypct":buypct,"kw":kw}
        print(f"{name:22} | {buypct:6.1f}% | {v['dumprate']*100:6.1f}% | {v['mean']:+8.4f} {v['win']*100:4.0f}% {v['tot']:+7.2f} {v['dd']:+7.2f}  ||  {a['mean']:+8.4f} {a['win']*100:5.0f}%")
    # multi-size for baseline + best few
    print("\nSIZE SWEEP (VAL meanR) for key strategies:")
    keyn=["BASELINE buy-all@floor","co-snipe K>=2","surv N1 thr1.0","surv N2 thr1.0","mom N2 r1.1","combo K2+survN2t1.0"]
    for name in keyn:
        gen=dict((n,(g,k)) for n,g,k in strategies)[name]
        g,kw=gen
        row=" ".join(f"{sz}:{summarize(g(VAL,sz,**kw))['mean']:+.4f}" for sz in SIZES)
        print(f"  {name:22} {row}")
    json.dump({"base_dump_all":base_dumprate(FEAT),"base_dump_val":base_dumprate(VAL),
               "split":split,"n":len(FEAT),"results":results},
              open("/root/genuine/results.json","w"),indent=2,default=str)
    print("\nwrote /root/genuine/results.json")
