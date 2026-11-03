#!/usr/bin/env python3
"""QUIET3 step 6: the frozen pick (fbots list empty + fol 4.0) and stop 5:2, alone and together: per run, per period, all runs."""
_src=open('s3_score.py').read()
exec(_src.split("out=[]")[0]); exec("def stopgain"+_src.split("def stopgain")[1].split("# stop parity")[0])
import random
R=lambda x: (not x['cur']) and x['since_last']>=1 and x['coh_hold']==0 and x['wh_fol']<4.0
def g_rule(x): return -x['vs'] if R(x) else 0.0
def g_stop(x): return 0.0 if R(x) else stopgain(x,5,2)-stopgain(x,6,2)
def summ(ws,h,f,name):
    g=[f(x) for x in ws]; G=sum(g); top=sorted(g,reverse=True)
    random.seed(1); n=len(g); B=sorted(sum(g[random.randrange(n)] for _ in range(n)) for _ in range(2000))
    pr=collections.defaultdict(float)
    for x,v in zip(ws,g): pr[x['key']]+=v
    nt=sum(v for x,v in zip(ws,g) if x['night'])
    print(f"| {name} | {G:+.3f} | {G/h*24:+.2f} | [{B[100]:+.2f},{B[1899]:+.2f}] | {G-sum(top[:5]):+.3f} | {sum(1 for v in pr.values() if v>0.0005)}/{sum(1 for v in pr.values() if v<-0.0005)} | {G-nt:+.3f}/{nt:+.3f} |")
print("| rule / period | net SOL @0.696 | /day | CI90 | w/o top5 | runs help/hurt | day/night |\n|---|---|---|---|---|---|---|")
for nm,f in (("fbots empty + fol 4.0",g_rule),("stop 5:2",g_stop),("both",lambda x:g_rule(x)+g_stop(x))):
    for per,ws,h in (("pick",P,HP),("TEST",T,HT),("all",W,HP+HT)): summ(ws,h,f,f"{nm} / {per}")
print("\nper run (both): run | period | skipped fills W/L | rule net | stop net")
for k in sorted({x['key'] for x in W},key=lambda k:rows[k]['t0']):
    ws=[x for x in W if x['key']==k]; sk=[x for x in ws if R(x) and x['isfill']]
    print(f"| {k} | {'test' if all(x['test'] for x in ws) else ('pick' if not any(x['test'] for x in ws) else 'split')} | {sum(1 for x in sk if x['pnl']>0)}/{sum(1 for x in sk if x['pnl']<=0)} | {sum(g_rule(x) for x in ws):+.3f} | {sum(g_stop(x) for x in ws):+.3f} |")
sk=[x for x in W if R(x) and x['isfill']]
print("\nskipped fills by fb_n:",collections.Counter(min(x['fb_n'],5) for x in sk),"by wh_fol bin:",collections.Counter(('none' if x['wh_fol']<0 else '<2.24' if x['wh_fol']<2.24 else '2.24-4') for x in sk))
