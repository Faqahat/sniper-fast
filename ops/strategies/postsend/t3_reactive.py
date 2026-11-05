"""Reactive fires (FRA runs with fire+timing): which path copy landed, per leader client; decomposition
dump seen -> fire (engine) | fire -> seen (post-send). MEASURED (our feed clock + engine clock)."""
import json,glob,collections
B='/home/moiz/sniper-data/runs/'
files=sorted(glob.glob(B+'fra/runs/dip_r*.jsonl'))+[B+'fra_r29/dip_r29.jsonl']
def q(v,p):
    v=sorted(x for x in v if x is not None); return round(v[min(len(v)-1,int(p*len(v)))],1) if v else None
F=[]
for f in files:
    run=f.split('dip_')[-1].split('.')[0]
    fires={}; tim={}; polls={}
    for l in open(f):
        if '"ev":"fire"' in l or '"ev":"timing"' in l or '"ev":"land_poll"' in l:
            e=json.loads(l)
            if e['ev']=='fire': fires[e['buy_sig']]=e
            elif e['ev']=='timing' and e.get('kind','fire')=='fire': tim[e['buy_sig']]=e
            elif e['ev']=='land_poll': polls[e['sig']]=e
    for s,fe in fires.items():
        t=tim.get(s)
        if not t: continue
        seen=t.get('buy_sig_seen'); lp=None; path=None
        var=(fe.get('nonce') or {}).get('variants') or []
        for v in var:
            if v['sig']==seen: path='+'.join(v['paths'])
            if v['sig'] in polls: lp=polls[v['sig']]
        if path is None and seen: path=fe.get('route','?')+'(single)'
        lp=lp or polls.get(s) or polls.get(seen)
        c2=t.get('clock2') or {}; w=t.get('win') or {}
        F.append(dict(run=run,client=fe.get('client'),route=fe.get('route'),path=path,nvar=len(var),
            react=t.get('reaction_ms'),f2s=t.get('fire_to_seen_ms'),
            d2s=((t['buy_first_rx']-t['dump_first_rx'])/1e6 if t.get('buy_first_rx') and t.get('dump_first_rx') else None),
            dslot=(c2.get('buy_slot',0)-c2.get('dump_slot',0)) if c2.get('buy_slot') else None,
            dump_pos=c2.get('dump_pos'),buy_idx=c2.get('buy_idx'),left=w.get('left_ms_write'),dump_in_slot=w.get('in_slot_ms'),
            ok=(lp or {}).get('ok'),err=str((lp or {}).get('err'))[:60],acks={a['path']:a['ms'] for a in t.get('acks',[])}))
json.dump(F,open('/home/moiz/sniper-data/postsend/t3_fires.json','w'))
print('fires with timing',len(F),'with seen',sum(1 for x in F if x['f2s'] is not None))
print('\n## reactive fires: by leader client (all FRA runs)')
print('| client | n | seen | dump->fire p50 | fire->seen p50/p90 | dump->seen p50/p90 | same slot as dump | ok |'); print('|---|---|---|---|---|---|---|---|')
g=collections.defaultdict(list)
for x in F: g[x['client']].append(x)
for c,v in sorted(g.items(),key=lambda kv:-len(kv[1])):
    s=[x for x in v if x['f2s'] is not None]
    print(f"| {c} | {len(v)} | {len(s)} | {q([x['react'] for x in v],.5)} | {q([x['f2s'] for x in s],.5)}/{q([x['f2s'] for x in s],.9)} | {q([x['d2s'] for x in s],.5)}/{q([x['d2s'] for x in s],.9)} | {sum(1 for x in s if x['dslot']==0)}/{len(s)} | {sum(1 for x in v if x['ok'])} |")
print('\n## winning (landed) copy path x client: n, fire->seen p50')
g=collections.defaultdict(list)
for x in F:
    if x['f2s'] is not None: g[(x['path'],x['client'])].append(x['f2s'])
for k,v in sorted(g.items(),key=lambda kv:-len(kv[1])): print(k,len(v),q(v,.5),q(v,.9))
print('\n## same-slot (dump slot) by ms left in the slot at write (window clock left_ms_write)')
for lo,hi in ((-999,0),(0,20),(20,40),(40,80),(80,999)):
    v=[x for x in F if x['f2s'] is not None and x['left'] is not None and lo<=x['left']<hi]
    print(f'left {lo}..{hi}: n={len(v)} same-slot={sum(1 for x in v if x["dslot"]==0)} f2s p50={q([x["f2s"] for x in v],.5)}')
print('\n## ack ms per path (HTTP answer), p50/p90')
a=collections.defaultdict(list)
for x in F:
    for p,m in x['acks'].items(): a[p].append(m)
for p,v in sorted(a.items(),key=lambda kv:-len(kv[1])): print(p,len(v),q(v,.5),q(v,.9))
print('\nper run:',collections.Counter(x['run'] for x in F))
