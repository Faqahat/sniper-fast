# ESTIMATE (shadow, calibrated as wide_report.py): QUIET skip OFF, QUIET3 A+B instead (QUIET stop kept).
import sys,json,collections,datetime
sys.path.insert(0,'/home/moiz/sniper/ops/strategies/presend/filters3/quiet3'); import quiet3_score as q
R='/home/moiz/sniper-data/filters3/runs/'; EX='/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_quiet3/ex/'
VAL=1793516400*10**9; A0=int((datetime.datetime(2026,11,2,8,0)-datetime.timedelta(hours=5)-datetime.datetime(1970,1,1)).total_seconds())*10**9; A1=A0+40*60*10**9
h=q.Hist(); ps=q.run([R+'r%d.presend.jsonl'%r for r in (37,38,39,40,41,42)],h,True)
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
    sc=lambda w: sh_net[w]*(0.696/sh_size[w]) if sh_size.get(w) else sh_net[w]
    pairs=[(sc(sh_w[s]),live_real.get(lw,0.0)) for lw,s in live_sig.items() if sh_w.get(s) in sh_net]
    gap=sum(b-a for a,b in pairs)/len(pairs) if pairs else 0.0
    for sig,sk in skip.items():
        if sk.get('why')!='quiet' or sh_w.get(sig) is None: continue
        w=sh_w[sig]; a=arm[w]
        p={'kind':'T2','n120':(sk.get('v2') or a.get('v2') or {}).get('n_120s'),'whd':(sk.get('quiet') or {}).get('wh_dumps'),'creator':(sk.get('ann') or {}).get('creator'),'t0':sk['trig']['t']}
        cat='A' if q.a_rule(p) else ('B' if h.b_rule(p) else 'released')
        sp='DEV' if p['t0']<VAL else ('VALatt' if A0<=p['t0']<A1 else 'VAL')
        x=res[(sp,cat)]; x['triggers']+=1
        if w in sh_net: x['fills']+=1; x['paper']+=sc(w); x['calibrated']+=sc(w)+gap; x['cal_wins']+=(sc(w)+gap)>0
    print('r%d calibration: %d pairs, gap %+.2f mSOL/window'%(r,len(pairs),gap*1e3))
for k in sorted(res): print(k,{a:round(b,3) for a,b in res[k].items()})
