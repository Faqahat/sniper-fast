# ESTIMATE: what if today's QUIET skip were REMOVED and replaced by A (+B)? The QUIET-skipped triggers that A/B would not skip become
# extra trades; their value is the shadow row c net, scaled to live size and calibrated (wide_report.py method: per-run mean gap
# live realized - shadow row c on the same T2 triggers, per window).
import json,collections,datetime
from lib import *
EX='/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_quiet3/ex/'
T=load()
VAL_T=1793516400*10**9
ATT0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; ATT1=ATT0+40*60*10**9
# creator histories from live positions (for B on skipped triggers)
hist=collections.defaultdict(list)
for t in T:
    c=(t.get('ann') or {}).get('creator')
    if c: hist[c].append(t)
def B(cre,T0,K=3):
    prev=[p for p in hist.get(cre,[]) if p['t']+3e9<T0][-K:]
    return len(prev)>0 and 2*sum(p['nf'] for p in prev)>=len(prev)
res=collections.defaultdict(lambda:collections.defaultdict(float))
for r in (37,38,39,40,41,42):
    sh_w={}; sh_net={}; sh_size={}; arm={}; live_sig={}; live_real=collections.defaultdict(float); skip={}
    for l in open(EX+'r%d.jsonl'%r):
        d=json.loads(l); e=d['ev']
        if e=='presend_arm': sh_w[d['sig']]=d['w']; arm[d['w']]=d
        elif e=='presend_fill' and d.get('row')=='c': sh_size[d['w']]=d['entry']['sol_in']/1e9
        elif e=='presend_exit' and d.get('row')=='c': sh_net[d['w']]=d.get('net_cheap',d.get('pnl',0.0))
        elif e=='presend_live_arm' and (d.get('kind') or 'T2')=='T2': live_sig[d['w']]=d['trig']['sig']
        elif e=='presend_live_realized' and (d.get('kind') or 'T2')=='T2': live_real[d['w']]+=d['pnl']/1e9
        elif e=='presend_live_skip' and (d.get('kind') or 'T2')=='T2' and 'trig' in d: skip[d['trig']['sig']]=d
    LIVE=0.696
    sc=lambda w: sh_net[w]*(LIVE/sh_size[w]) if sh_size.get(w) else sh_net[w]
    pairs=[(sc(sh_w[s]),live_real.get(lw,0.0)) for lw,s in live_sig.items() if sh_w.get(s) in sh_net]
    gap=sum(b-a for a,b in pairs)/len(pairs) if pairs else 0.0
    for sig,sk in skip.items():
        if sk.get('why')!='quiet': continue
        w=sh_w.get(sig)
        if w is None: continue
        a=arm[w]; v=a.get('v2') or {}; q=a.get('quiet') or {}
        split='VAL' if a['t']>=VAL_T else 'DEV'
        if split=='VAL' and ATT0<=a['t']<ATT1: split2='att'
        else: split2=split
        A=v.get('n_120s') is not None and v['n_120s']<=15 and (q.get('wh_dumps') or 0)<=5
        b=B((sk.get('ann') or {}).get('creator'),a['t'])
        key=(split,'A' if A else ('B' if b else 'released'))
        res[key]['n']+=1
        if w in sh_net:
            res[key]['fills']+=1; res[key]['paper']+=sc(w); res[key]['cal']+=sc(w)+gap; res[key]['wins']+=(sc(w)+gap)>0
    print('r%d calibration pairs %d gap %+.2f mSOL/window'%(r,len(pairs),gap*1000))
for k in sorted(res): print(k,{a:round(b,3) for a,b in res[k].items()})
