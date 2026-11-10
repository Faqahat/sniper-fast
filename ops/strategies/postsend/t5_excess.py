"""Excess over the leader's floor (MEASURED): s2f - floor(region,leader). floor = p10 same-slot send->seen of our pre-sends to that leader.
Pre-sends (cu_price 1000, 1 lane) vs FRA reactive fires (cu_price ~5M, 6-9 lane copies, winning copy)."""
import json,glob,collections,pickle
P=pickle.load(open('/home/it/sniper-data/postsend/leader_floor.pkl','rb'))
floor,lc=P['floor'],P['lc']
def q(v,p):
    v=sorted(x for x in v if x is not None); return round(v[min(len(v)-1,int(p*len(v)))],1) if v else None
# reactive FRA
B='/home/it/sniper-data/runs/'
F=json.load(open('/home/it/sniper-data/postsend/t3_fires.json'))
# need leader per fire: re-read fire events
lead={}
for f in sorted(glob.glob(B+'fra/runs/dip_r*.jsonl'))+[B+'fra_r29/dip_r29.jsonl']:
    run=f.split('dip_')[-1].split('.')[0]
    for l in open(f):
        if '"ev":"fire"' in l:
            e=json.loads(l); lead.setdefault(run,[]).append((e.get('leader') or '')[:8])
i=collections.Counter()
for x in F:
    x['leader']=lead[x['run']][i[x['run']]]; i[x['run']]+=1
    x['floor']=floor.get(('FRA',x['leader'])); x['cls']=lc.get(('FRA',x['leader']))
print('reactive fires with a FRA leader floor:',sum(1 for x in F if x['floor'] is not None),'of',len(F))
print('\n## reactive (FRA, high fee, multi-lane, winning copy): fire->seen minus leader floor, landed in fire/dump slot only')
print('| client | class | n | fire->seen p50 | floor p50 | excess p50/p90 |'); print('|---|---|---|---|---|---|')
for c in ['AgaveBam','JitoLabs','HarmonicAgave','HarmonicFiredancer','Firedancer','FireBAM']:
    for cl in ('near','mid','far'):
        v=[x for x in F if x['client']==c and x['cls']==cl and x['dslot']==0]
        if len(v)<5: continue
        print(f"| {c} | {cl} | {len(v)} | {q([x['f2s'] for x in v],.5)} | {q([x['floor'] for x in v],.5)} | {q([x['f2s']-x['floor'] for x in v],.5)}/{q([x['f2s']-x['floor'] for x in v],.9)} |")
# pre-sends: same-slot, sent early in slot (AMS r49-55 rows w/ slot clock) + all same-slot (both regions)
R=json.load(open('/home/it/sniper-data/postsend/t1b_rows.json'))
rows=[]
for reg,f in [('AMS',x) for x in sorted(glob.glob(B+'ams_r*/dip_ams_r*.jsonl')) if not x.endswith('obs.jsonl')]+[('FRA',x) for x in sorted(glob.glob(B+'fra/runs/dip_r2*.jsonl'))]:
    Ld={}
    for l in open(f):
        if '"presend_attempt' not in l: continue
        e=json.loads(l)
        if e['ev']=='presend_attempt': Ld[e['sig']]=e.get('leader')
        elif e.get('slots_after_send')==0 and e.get('ms_send_to_first_rx') is not None:
            ld=Ld.pop(e['sig'],None); fl=floor.get((reg,ld))
            if fl is not None: rows.append((reg,e['client'],e['path'],lc[(reg,ld)],e['ms_send_to_first_rx']-fl,e['ms_send_to_first_rx'],fl))
print('\n## pre-sends (cu_price 1000, single lane): same-slot landers, send->seen minus leader floor')
print('| region | client | path | class | n | send->seen p50 | excess p50/p90 |'); print('|---|---|---|---|---|---|---|')
g=collections.defaultdict(list)
for r in rows: g[(r[0],r[1],r[2],r[3])].append(r)
for k in sorted(g):
    v=g[k]
    if len(v)<200 or k[1] not in ('AgaveBam','JitoLabs','HarmonicAgave','HarmonicFiredancer','Firedancer','FireBAM'): continue
    print(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {len(v)} | {q([r[5] for r in v],.5)} | {q([r[4] for r in v],.5)}/{q([r[4] for r in v],.9)} |")
