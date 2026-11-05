import json
D='/home/moiz/sniper-data/filters3/quiet3/'
def load():
    T=[json.loads(l) for l in open(D+'trades.jsonl')]; F=[json.loads(l) for l in open(D+'trades_mk.jsonl')]
    for t,f in zip(T,F):
        t.update(f); q=t.get('quiet') or {}; v=t.get('v2') or {}; a=t.get('ann') or {}
        t.update(since_last=q.get('since_last'),coh=q.get('coh_hold'),whf=q.get('wh_fol'),whd=q.get('wh_dumps'),
                 n60=v.get('n_tr_60s'),n120=v.get('n_120s'),athigh=v.get('at_120s_high'),maxdd=v.get('maxdd_120s'),
                 nb50=a.get('nb50'),cr=a.get('cr_pct'),nf=t['n_fol_hold']==0, p=t['pnl']/1e6)
    T.sort(key=lambda t:t['t'])
    return T
def summ(x):
    n=len(x); s=sum(t['p'] for t in x)
    return '%4d %+7.0f (%+5.1f/tr) nf%3d win%3d'%(n,s,s/max(n,1),sum(t['nf'] for t in x),sum(t['p']>0 for t in x))
def load2():
    T=load()
    import json
    T0=[json.loads(l) for l in open(D+'trades.jsonl')]; P=[json.loads(l) for l in open(D+'trades_p2.jsonl')]
    m={(t['run'],t['mint'],t['pid'],t['t']):p for t,p in zip(T0,P)}
    for t in T: t.update(m[(t['run'],t['mint'],t['pid'],t['t'])])
    return T
