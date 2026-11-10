import json,sys
D='/home/it/sniper-data/filters3/quiet3/'
T=[json.loads(l) for l in open(D+'trades.jsonl')]; F=[json.loads(l) for l in open(D+'trades_mk.jsonl')]
for t,f in zip(T,F): t.update(f)
kinds=sys.argv[2].split(',')
feats=sys.argv[1].split(',')
for f in feats:
    X=[t for t in T if t['kind'] in kinds and t.get(f) is not None]
    dv=sorted(t[f] for t in X if t['split']=='DEV')
    if not dv: continue
    qs=sorted(set(dv[int(len(dv)*k/5)] for k in range(1,5)))
    b=lambda v: sum(v>=q for q in qs)
    print('==',f,'cuts',[round(q,3) for q in qs], 'missing', sum(1 for t in T if t['kind'] in kinds and t.get(f) is None))
    for sp in ('DEV','VAL'):
        row=[]
        for k in range(len(qs)+1):
            y=[t for t in X if t['split']==sp and b(t[f])==k]
            if not y: row.append('   -   '); continue
            row.append('%4d %+5.1f nf%2d%%'%(len(y),sum(t['pnl'] for t in y)/1e6/len(y),100*sum(t['n_fol_hold']==0 for t in y)/len(y)))
        print(sp,' | '.join(row))
