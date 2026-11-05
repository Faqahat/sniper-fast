import json,collections,datetime
D='/home/moiz/sniper-data/filters3/quiet3/'
T=[json.loads(l) for l in open(D+'trades.jsonl')]; T.sort(key=lambda t:t['t'])
def hour(t): return (datetime.datetime.utcfromtimestamp(t/1e9).hour+5)%24
# regime: followed rate of last K closed trades (buy t + 3s before this trigger)
for i,t in enumerate(T):
    tt=t['trig_t'] or t['t']
    prev=[p for p in T[max(0,i-60):i] if p['t']+3e9<tt]
    for K in (5,10,20):
        pk=prev[-K:]
        t['reg%d'%K]=sum(p['n_fol_hold']>0 for p in pk)/len(pk) if len(pk)==K else None
        t['regp%d'%K]=sum(p['pnl'] for p in pk)/1e6/len(pk) if len(pk)==K else None
    t['hour']=hour(tt)
def g(t,f):
    q=t.get('quiet') or {}; v=t.get('v2') or {}; a=t.get('ann') or {}
    return {'since_last':q.get('since_last'),'coh_hold':q.get('coh_hold'),'wh_fol':q.get('wh_fol'),'wh_dumps':q.get('wh_dumps'),
      'n60':v.get('n_tr_60s'),'n120':v.get('n_120s'),'athigh':v.get('at_120s_high'),'maxdd':v.get('maxdd_120s'),'ring_s':v.get('ring_s'),
      'nb50':a.get('nb50'),'cr_pct':a.get('cr_pct'),'pct':t['pct'],'trig_sol':(t['trig_sol'] or 0)/1e9,'age':t['age_slots'],'vsol':(t['vsol'] or 0)/1e9,
      'reg5':t['reg5'],'reg10':t['reg10'],'reg20':t['reg20'],'regp10':t['regp10'],'regp20':t['regp20'],'hour':t['hour'],'sat':t['sat'],'nhold':len(t.get('holders') or [])}[f]
import sys
feats=sys.argv[1].split(',') if len(sys.argv)>1 else ['since_last','coh_hold','wh_fol','wh_dumps','n60','n120','athigh','maxdd','ring_s','nb50','cr_pct','pct','trig_sol','age','vsol','reg5','reg10','reg20','regp10','regp20','hour','nhold']
kinds=sys.argv[2].split(',') if len(sys.argv)>2 else ['T2','rearm']
for f in feats:
    X=[t for t in T if t['kind'] in kinds and g(t,f) is not None]
    dv=sorted(g(t,f) for t in X if t['split']=='DEV')
    if not dv: continue
    qs=sorted(set(dv[int(len(dv)*k/5)] for k in range(1,5)))
    def b(v):
        return sum(v>=q for q in qs)
    print('==',f,'cuts',[round(q,3) if isinstance(q,float) else q for q in qs])
    for sp in ('DEV','VAL'):
        row=[]
        for k in range(len(qs)+1):
            y=[t for t in X if t['split']==sp and b(g(t,f))==k]
            if not y: row.append('   -   '); continue
            row.append('%4d %+5.1f nf%2d%%'%(len(y),sum(t['pnl'] for t in y)/1e6/len(y),100*sum(t['n_fol_hold']==0 for t in y)/len(y)))
        print(sp,' | '.join(row))
