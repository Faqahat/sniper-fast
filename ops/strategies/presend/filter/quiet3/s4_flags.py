#!/usr/bin/env python3
"""QUIET3 step 5: only what ENGINE FLAGS can change (--presend-live-quiet-fol F, --presend-live-quiet-hist-h H, --presend-live-quiet-stop N:M;
fb < 2, coh == 0, since_last >= 1 and all-4 are fixed in code) + the non-flag add-ons that looked best, scored pick vs FROZEN test."""
import sys; sys.argv=['x']
_src=open('s3_score.py').read()
exec(_src.split("out=[]")[0]); exec("def stopgain"+_src.split("def stopgain")[1].split("# stop parity")[0])
out=[]
def pr_(s): out.append(s); print(s)
def addon(fn): return lambda x: (not x['cur']) and fn(x)
def q4(x,fol,key='wh_fol'): return x['since_last']>=1 and x['coh_hold']==0 and x['fb_n']<2 and x[key]<fol
for x in W:
    c=x['c']; x['wf6']=c['wf6']; x['wf2']=c['wf2']
cands=[(f"fol {f}",(lambda f: lambda x:q4(x,f))(f)) for f in (2.5,3.0,3.5,4.0,5.0,99)]
cands+=[(f"hist-h 6 fol {f}",(lambda f: lambda x:q4(x,f,'wf6'))(f)) for f in (2.24,3.0,4.0)]
cands+=[(f"hist-h 2 fol {f}",(lambda f: lambda x:q4(x,f,'wf2'))(f)) for f in (2.24,3.0,4.0)]
cands+=[(f"[code] wh_fol<{f} & dumps>=3",(lambda f: lambda x:x['wh_dumps']>=3 and 0<=x['wh_fol']<f)(f)) for f in (0.5,1.0,1.5,2.0)]
cands+=[(f"[code] whale past fills>={n} & sum<0",(lambda n: lambda x:x['wp_n']>=n and x['wp_sum']<0)(n)) for n in (1,2,3)]
cands+=[("[code] (a)(b)(d) fol<4 (drop fbots)",lambda x:x['since_last']>=1 and x['coh_hold']==0 and x['wh_fol']<4)]
grid=[]
for fbk in ('frozen','empty'):
    for hk,key in (('24','wh_fol'),('6','wf6'),('2','wf2')):
        for f in (1.0,1.5,2.0,2.24,2.5,3.0,3.5,4.0,4.5,5.0,6.0,99):
            fn=(lambda fbk,key,f: lambda x: x['since_last']>=1 and x['coh_hold']==0 and (fbk=='empty' or x['fb_n']<2) and x[key]<f)(fbk,key,f)
            grid.append((f"fbots {fbk}, hist-h {hk}, fol {f}",fn))
G=[]
for nm,fn in grid:
    s_=score(P,HP,addon(fn),boot=False); G.append((s_['G'],s_['wo5'],nm,fn))
G.sort(key=lambda r:-r[0])
pr_("FLAG GRID on PICK (top 12 by net gain over current; add-on = current OR rule):")
for g,w5,nm,fn in G[:12]: pr_(f"  {nm}: pick net {g:+.3f} w/o5 {w5:+.3f}")
best=[r for r in G if r[1]>0][0]; pr_(f"PICKED (best pick net with w/o-top5 > 0): {best[2]}")
cands=[(best[2]+' [PICKED]',best[3])]+cands
pr_("| rule | period | skipped arms | fills (W) | losers saved | winners lost | fees saved | net | /day @0.696 | CI90 | w/o top5 | runs help/hurt | day/night |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for nm,fn in cands:
    for per,ws,h in (("pick",P,HP),("TEST",T,HT)):
        s=score(ws,h,addon(fn))
        pr_(f"| {nm} | {per} | {s['n']} | {s['nf']} ({s['nw']}) | {s['ls']:+.3f} | {-s['wl']:+.3f} | {s['fees']:+.3f} | {s['G']:+.3f} | {s['day']:+.2f} | [{s['ci'][0]:+.2f},{s['ci'][1]:+.2f}] | {s['wo5']:+.3f} | {s['help']}/{s['hurt']} | {s['dayg']:+.3f}/{s['night']:+.3f} |")
# stop detail for 5:2, 4:3, 5:3: composition on test
pr_("\nstop detail (gain over 6:2): fills blocked W/L, fill P&L saved, fees saved")
for N,M in ((5,2),(4,3),(5,3),(4,2),(3,2),(6,3)):
    for per,ws,h in (("pick",P,HP),("TEST",T,HT)):
        fw=fl=0;fp=0;fe=0
        for x in ws:
            g=stopgain(x,N,M)-stopgain(x,6,2)
            if x['isfill'] and g!=0:
                if x['pnl']>0: fw+=1
                else: fl+=1
                fp+=g
            elif g: fe+=g
        s=stop_score(ws,h,N,M)
        pr_(f"| {N}:{M} | {per} | blocked fills W{fw}/L{fl} | fills {fp:+.3f} | fees {fe:+.3f} | net {s['G']:+.3f} | /day {s['day']:+.2f} | CI [{s['ci'][0]:+.2f},{s['ci'][1]:+.2f}] | w/o5 {s['wo5']:+.3f} | runs {s['help']}/{s['hurt']} |")
# all-run per-day of 5:2 + per-run
pr_("\n5:2 per run (gain over 6:2, @0.696):")
for k in sorted({x['key'] for x in W},key=lambda k:rows[k]['t0']):
    g=sum(stopgain(x,5,2)-stopgain(x,6,2) for x in W if x['key']==k); pr_(f"{k}{' TEST' if k in RUNS_T else ''} {g:+.3f}")
open(f"{D}/s4_out.md","w").write("\n".join(out))
