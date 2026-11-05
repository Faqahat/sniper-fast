"""Leader proximity (MEASURED): per (region, leader) floor = p10 of send->seen over same-slot landers of our pre-sends.
Classify near (<= 25 ms floor), mid (25-45), far (>45). Re-tabulate Task 1 + Task 2 on near leaders."""
import json,glob,collections,pickle
B='/home/moiz/sniper-data/runs/'
FILES=[('AMS',f) for f in sorted(glob.glob(B+'ams/runs/dip_ams_r*.jsonl'))+sorted(glob.glob(B+'ams_r*/dip_ams_r*.jsonl')) if not f.endswith('obs.jsonl')]
FILES+=[('FRA',f) for f in sorted(glob.glob(B+'fra/runs/dip_r*.jsonl'))]
def q(v,p):
    v=sorted(x for x in v if x is not None); return round(v[min(len(v)-1,int(p*len(v)))],1) if v else None
L={}; rows=[]
for reg,f in FILES:
    for l in open(f):
        if '"presend_attempt' not in l: continue
        e=json.loads(l)
        if e['ev']=='presend_attempt': L[e['sig']]=e.get('leader')
        elif e['ev']=='presend_attempt_land' and e.get('ms_send_to_first_rx') is not None and e.get('slots_after_send') is not None:
            rows.append((reg,L.pop(e['sig'],None),e['client'],e['path'],e['ms_send_to_first_rx'],e['slots_after_send'],e['res'],e['sig'][:16]))
fl=collections.defaultdict(list)
for reg,ld,c,p,s,sas,res,sg in rows:
    if sas==0: fl[(reg,ld)].append(s)
floor={k:q(v,.1) for k,v in fl.items() if len(v)>=20}
def cls(x): return None if x is None else ('near' if x<=25 else 'mid' if x<=45 else 'far')
lc={k:cls(v) for k,v in floor.items()}
pickle.dump(dict(floor=floor,lc=lc,sig2leader={r[7]:(r[0],r[1]) for r in rows}),open('/home/moiz/sniper-data/postsend/leader_floor.pkl','wb'))
print('leaders with floor:',len(floor),collections.Counter((k[0],v) for k,v in lc.items()))
print('\n## leader floor distribution by region (p10 send->seen of same-slot landers, per leader), counts of attempts')
for reg in ('AMS','FRA'):
    c=collections.Counter(lc.get((r[0],r[1])) for r in rows if r[0]==reg); print(reg,c)
print('\n## Task-1 by proximity class x client (AMS+FRA, both pre-send paths): n, same-slot, send->seen p10/p50/p90')
print('| region | class | client | n | same-slot | send->seen p10/p50/p90 |'); print('|---|---|---|---|---|---|')
g=collections.defaultdict(list)
for r in rows: g[(r[0],lc.get((r[0],r[1])),r[2])].append(r)
for k in sorted(g,key=lambda k:(k[0],str(k[1]),-len(g[k]))):
    v=g[k]
    if len(v)<500: continue
    s=[x[4] for x in v]
    print(f"| {k[0]} | {k[1]} | {k[2]} | {len(v)} | {100*sum(1 for x in v if x[5]==0)/len(v):.0f}% | {q(s,.1)}/{q(s,.5)}/{q(s,.9)} |")
