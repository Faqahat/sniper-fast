#!/usr/bin/env python3
"""QUIET3 step 4: score QUIET variants on all armed windows (fills AND unfilled tries) of the 24 runs, after the age-1 skip.
Value of a window v = realized P&L - its failed tries' fees. Skipping it gains -v. Pick on runs starting before 10-28 00:00 PKT,
test FROZEN on the later runs. Censoring: in QUIET-on runs the arms QUIET skipped have no outcome, so a rule is scored as an ADD-ON
(skip = current QUIET OR extra): its gain = sum(-v) over windows where extra is true and current QUIET is false (all runs).
Loosening (skipping fewer than current QUIET) is only measurable on the QUIET-off runs. Read-only."""
import json, collections, random, itertools, sys, datetime
D="/home/moiz/sniper-data/presend_quiet3"
J=json.load(open(f"{D}/windows_feats.json"))
rows={r['run']+r['reg']:r for r in json.load(open('/home/moiz/sniper-data/presend_losses/verify/fills.json'))['rows']}
fpa_all=[r['fees']/r['att_all'] for r in rows.values() if r['fees']]; FPA0=sum(fpa_all)/len(fpa_all)
SPLIT=1793127600*10**9   # 10-28 00:00 PKT
PKT=5*3600; SIZE=0.696
def pkt(ns): return datetime.datetime.utcfromtimestamp(ns/1e9+PKT)
H={}  # run hours
for k,r in rows.items(): H[k]=(r['t1']-r['t0'])/3.6e12
QON={k for k,m in J['meta'].items() if m['qcfg']}
W=[]
for x in J['windows']:
    if x['age'] is None or x['age']<2: continue          # age-1 skip ships next run
    key=x['run']+x['reg']; c=x['c']
    if not c.get('ok'): continue
    fpa=(rows[key]['fees']/rows[key]['att_all']) if rows[key]['fees'] else FPA0
    q=x.get('q')
    if q:   # engine's own values
        sig=dict(since_last=q['since_last'],coh_hold=q['coh_hold'],fb_n=q['fb_n'],wh_fol=q['wh_fol'],wh_dumps=q['wh_dumps'])
    else:
        sig=dict(since_last=c['since_last'],coh_hold=c['coh_hold'],fb_n=c['fb_n'],wh_fol=c['wf24'],wh_dumps=c['wd24'])
    pnl=x['pnl'] or 0.0; filled=x['pnl'] is not None
    nfail=max(x['att']-(1 if filled else 0),0)
    x.update(sig); x['key']=key; x['qon']=key in QON; x['test']=x['t']>=SPLIT
    x['fee']=nfail*fpa/1e9; x['v']=pnl-x['fee']; x['vs']=pnl*SIZE/x['size']-x['fee']   # vs: P&L scaled to 0.696 (INFERRED)
    x['isfill']=filled; x['night']=not(8<=pkt(x['t']).hour<20)
    W.append(x)
# whale's own past P&L (strictly earlier arms, realized long before: arm t + 60 s < this arm t), both regions
W.sort(key=lambda x:x['t']); hist=collections.defaultdict(list)
for x in W:
    h=[p for (t,p) in hist[x['whale']] if t+60e9<x['t']]
    x['wp_n']=len(h); x['wp_sum']=sum(h); x['wp_neg']=sum(1 for p in h if p<0)
    if x['isfill']: hist[x['whale']].append((x['t'],x['pnl']*SIZE/x['size']))
def cur(x,fol=2.24,fb=2,coh=0,sl=1,k=4):
    f=[x['since_last']>=sl, x['coh_hold']<=coh, x['fb_n']<fb, x['wh_fol']<fol]
    return sum(f)>=k
for x in W: x['cur']=cur(x)
def hours(sel): return sum(H[k] for k in {x['key'] for x in sel})
RUNS_P=sorted({x['key'] for x in W if not x['test']}); RUNS_T=sorted({x['key'] for x in W if x['test']})
HP=sum(H[k] for k in RUNS_P); HT=sum(H[k] for k in RUNS_T)
def score(ws,hrs,rule,val='vs',boot=True):
    sk=[x for x in ws if rule(x)]
    g=[-x[val] for x in sk]; G=sum(g)
    wl=sum(x[val] for x in sk if x['isfill'] and x['pnl']>0); ls=sum(-x[val] for x in sk if x['isfill'] and x['pnl']<=0)
    fees=sum(x['fee'] for x in sk if not x['isfill'])
    nf=sum(1 for x in sk if x['isfill']); nw=sum(1 for x in sk if x['isfill'] and x['pnl']>0)
    top=sorted(g,reverse=True); wo5=G-sum(top[:5])
    pr=collections.defaultdict(float)
    for x in sk: pr[x['key']]-=x[val]
    help_=sum(1 for v in pr.values() if v>0.0005); hurt=sum(1 for v in pr.values() if v<-0.0005)
    ci=(0,0)
    if boot and ws:
        random.seed(1); vals=[(-x[val] if rule(x) else 0.0) for x in ws]; B=[]
        n=len(vals)
        for _ in range(1000): B.append(sum(vals[random.randrange(n)] for _ in range(n)))
        B.sort(); ci=(B[50],B[949])
    nightG=sum(-x[val] for x in sk if x['night']); dayG=G-nightG
    return dict(n=len(sk),nf=nf,nw=nw,G=G,day=G/hrs*24,wl=wl,ls=ls,fees=fees,ci=ci,wo5=wo5,help=help_,hurt=hurt,night=nightG,dayg=dayG)
def fmt(name,s): return f"| {name} | {s['n']} | {s['nf']} ({s['nw']}W) | {s['ls']:+.3f} | {-s['wl']:+.3f} | {s['fees']:+.3f} | {s['G']:+.3f} | {s['day']:+.2f} | [{s['ci'][0]:+.2f},{s['ci'][1]:+.2f}] | {s['wo5']:+.3f} | {s['help']}/{s['hurt']} | {s['dayg']:+.3f}/{s['night']:+.3f} |"
HDR="| rule | skipped arms | of them fills (winners) | saved on losers | lost on winners | fees saved | net | /day @0.696 | CI90 net | w/o top5 | runs help/hurt | day/night net |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
P=[x for x in W if not x['test']]; T=[x for x in W if x['test']]
OFF=[x for x in P if not x['qon']]; HOFF=sum(H[k] for k in {x['key'] for x in OFF})
out=[]
def pr_(s): out.append(s); print(s)
pr_(f"windows after age-1 skip: pick {len(P)} ({sum(x['isfill'] for x in P)} fills, {HP:.1f} h, runs {len(RUNS_P)}), test {len(T)} ({sum(x['isfill'] for x in T)} fills, {HT:.1f} h, runs {len(RUNS_T)}); QUIET-off pick runs {sorted({x['key'] for x in OFF})} {HOFF:.1f} h; fee/try {FPA0:.0f} lamports avg")
pr_(f"baseline value (vs, 0.696): pick {sum(x['vs'] for x in P):+.3f} ({sum(x['vs'] for x in P)/HP*24:+.2f}/day), test {sum(x['vs'] for x in T):+.3f} ({sum(x['vs'] for x in T)/HT*24:+.2f}/day)")
# ---- 1. current QUIET on QUIET-off runs (what it does where it was not on)
pr_("\n## A. Current QUIET (all 4) on the QUIET-off runs (pick period only; no QUIET-off run in test)\n"+HDR)
pr_(fmt("current all-4 (2.24/2/0/1)",score(OFF,HOFF,lambda x:x['cur'])))
for nm,fn in [("since_last>=1 alone",lambda x:x['since_last']>=1),("coh_hold==0 alone",lambda x:x['coh_hold']==0),("fb_n<2 alone",lambda x:x['fb_n']<2),
              ("wh_fol<2.24 alone",lambda x:x['wh_fol']<2.24),("3-of-4",lambda x:cur(x,k=3)),("2-of-4",lambda x:cur(x,k=2))]+\
             [(f"all-4 fol<{f}",(lambda f: lambda x:cur(x,fol=f))(f)) for f in (1.0,1.5,2.0,2.5,3.0,3.5,4.0,5.0,99)]+\
             [(f"all-4 fb<{b}",(lambda b: lambda x:cur(x,fb=b))(b)) for b in (1,3,4)]+[("all-4 coh<=1",lambda x:cur(x,coh=1)),("all-4 since>=2",lambda x:cur(x,sl=2))]:
    pr_(fmt(nm,score(OFF,HOFF,fn)))
# ---- 2. ADD-ON candidates: extra skip when current QUIET false
def addon(fn): return lambda x: (not x['cur']) and fn(x)
C=[]
for k in (2,3):
    for f in (1.0,1.5,2.0,2.24,2.5,3.0,3.5,4.0,5.0,99):
        for b in (1,2,3,4):
            for co in (0,1):
                C.append((f"{k}-of-4 fol<{f} fb<{b} coh<={co}",(lambda k,f,b,co: lambda x:cur(x,fol=f,fb=b,coh=co,k=k))(k,f,b,co)))
for f in (2.5,3.0,3.5,4.0,5.0,99):
    for b in (2,3,4):
        for co in (0,1):
            C.append((f"all-4 fol<{f} fb<{b} coh<={co}",(lambda f,b,co: lambda x:cur(x,fol=f,fb=b,coh=co))(f,b,co)))
for f in (2.24,3.0,4.0,99):
    C.append((f"(b)(c)(d) fol<{f} (no since_last)",(lambda f: lambda x:x['coh_hold']==0 and x['fb_n']<2 and x['wh_fol']<f)(f)))
    C.append((f"(a)(c)(d) fol<{f} (no coh)",(lambda f: lambda x:x['since_last']>=1 and x['fb_n']<2 and x['wh_fol']<f)(f)))
    C.append((f"(a)(b)(d) fol<{f} (no fbots)",(lambda f: lambda x:x['since_last']>=1 and x['coh_hold']==0 and x['wh_fol']<f)(f)))
for f in (0.5,1.0,1.5,2.0):
    C.append((f"wh_fol<{f} & wh_dumps>=3 alone",(lambda f: lambda x:x['wh_dumps']>=3 and 0<=x['wh_fol']<f)(f)))
for n_ in (1,2,3,5):
    for th in (0.0,-0.02,-0.05,-0.1):
        C.append((f"whale past fills>={n_} & sum<{th}",(lambda n_,th: lambda x:x['wp_n']>=n_ and x['wp_sum']<th)(n_,th)))
    C.append((f"whale past fills>={n_} & all lost",(lambda n_: lambda x:x['wp_n']>=n_ and x['wp_neg']==x['wp_n'])(n_)))
# stop rule N:M tightening as add-on (blocks a fill at offset >= N when others through N-1 < M; unfilled: saves the later tries)
def stopgain(x,N,M,val='vs'):
    o=x['c']['oth']; ok=o[min(N-1,12)]>=M if N>=1 else True
    if ok: return 0.0
    if x['isfill']:
        fo=x['fill_off'] if x['fill_off'] is not None else 0
        return -x[val] if fo>=N else 0.0
    end=(x.get('dis_slot') or x['slot'])-x['slot']
    if end<=N or end<=0: return 0.0
    return x['fee']*(end-N)/end
def stop_score(ws,hrs,N,M,cn=6,cm=2,qon_only_tighten=True):
    g=[];pr=collections.defaultdict(float);nf=0;nw=0;wl=0;ls=0;fees=0
    for x in ws:
        a=stopgain(x,N,M)-stopgain(x,cn,cm) if x['qon'] else stopgain(x,N,M)-stopgain(x,cn,cm)
        g.append(a); pr[x['key']]+=a
    G=sum(g); top=sorted(g,reverse=True)
    random.seed(1); n=len(g); B=sorted(sum(g[random.randrange(n)] for _ in range(n)) for _ in range(1000))
    return dict(G=G,day=G/hrs*24,ci=(B[50],B[949]),wo5=G-sum(top[:5]),help=sum(1 for v in pr.values() if v>0.0005),hurt=sum(1 for v in pr.values() if v<-0.0005))
# stop parity: current 6:2 must not block observed fills in QUIET-on runs
bad=[x for x in W if x['qon'] and x['isfill'] and stopgain(x,6,2)!=0]
pr_(f"\nstop parity: fills in QUIET-on runs that 6:2 'would block' (should be ~0): {len(bad)} of {sum(1 for x in W if x['qon'] and x['isfill'])}")
pr_("\n## B. Add-on candidates, PICK runs (gain over current QUIET; skip = current OR rule)\n"+HDR)
res=[]
for nm,fn in C:
    s=score(P,HP,addon(fn),boot=False); res.append((s['G'],nm,fn,s))
res.sort(key=lambda r:-r[0])
for G,nm,fn,s in res[:25]: pr_(fmt(nm,score(P,HP,addon(fn))))
pr_("\n## C. Stop rule N:M (gain over 6:2; tighter only in QUIET-on runs is exact, looser is censored there)\n| N:M | pick net | pick /day | pick CI90 | test net | test /day | test CI90 | test w/o top5 | test runs help/hurt |\n|---|---|---|---|---|---|---|---|---|")
for N in (3,4,5,6,7,8):
    for M in (1,2,3,4):
        if (N,M)==(6,2): continue
        tight=(N<=6 and M>=2)
        p=stop_score(P,HP,N,M); t=stop_score(T,HT,N,M)
        pr_(f"| {N}:{M}{'' if tight else ' (looser: censored)'} | {p['G']:+.3f} | {p['day']:+.2f} | [{p['ci'][0]:+.2f},{p['ci'][1]:+.2f}] | {t['G']:+.3f} | {t['day']:+.2f} | [{t['ci'][0]:+.2f},{t['ci'][1]:+.2f}] | {t['wo5']:+.3f} | {t['help']}/{t['hurt']} |")
# ---- frozen picks: pre-registered = top 5 pick add-ons that pass pick w/o top5 > 0 and >= 15 skipped fills
pr_("\n## D. FROZEN test of the pick-period winners (top add-ons with pick w/o-top5 > 0 and >= 15 skipped fills)\n"+HDR.replace('| rule |','| rule (period) |'))
chosen=[]
for G,nm,fn,s in res:
    if s['wo5']>0 and s['nf']>=15: chosen.append((nm,fn))
    if len(chosen)==5: break
for nm,fn in chosen:
    pr_(fmt(nm+" (pick)",score(P,HP,addon(fn)))); pr_(fmt(nm+" (TEST)",score(T,HT,addon(fn))))
json.dump([nm for nm,_ in chosen],open(f"{D}/chosen.json","w"))
# per-run table for the best chosen
if chosen:
    nm,fn=chosen[0]; pr_(f"\nper run, {nm}: run | skipped fills W/L | net (0.696)")
    for k in sorted({x['key'] for x in W},key=lambda k:rows[k]['t0']):
        sk=[x for x in W if x['key']==k and addon(fn)(x)]
        pr_(f"| {k} | {'TEST' if sk and sk[0]['test'] else ''} | {sum(1 for x in sk if x['isfill'] and x['pnl']>0)}/{sum(1 for x in sk if x['isfill'] and x['pnl']<=0)} | {sum(-x['vs'] for x in sk):+.3f} |")
# current QUIET signal distribution: value by #quiet flags (all windows)
pr_("\n## E. Value by number of quiet flags true (all runs, vs @0.696; 4 = only QUIET-off runs)\n| flags true | arms | fills | win% | net | net/fill |\n|---|---|---|---|---|---|")
for k in range(5):
    s=[x for x in W if sum([x['since_last']>=1,x['coh_hold']==0,x['fb_n']<2,x['wh_fol']<2.24])==k]
    f=[x for x in s if x['isfill']]
    pr_(f"| {k} | {len(s)} | {len(f)} | {100*sum(1 for x in f if x['pnl']>0)/max(len(f),1):.0f} | {sum(x['vs'] for x in s):+.3f} | {sum(x['vs'] for x in f)/max(len(f),1):+.4f} |")
open(f"{D}/s3_out.md","w").write("\n".join(out))
